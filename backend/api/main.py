from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import APIAccessControl, SESSION_TTL_SECONDS
from backend.api.schemas import (
    ApiHealthResponse,
    ActiveTopologyResponse,
    Availability,
    ExecuteIntentRequest,
    ExecutionAcceptedResponse,
    ExecutionDetail,
    ExecutionStatusResponse,
    ExecutionSummary,
    IntentPreviewRequest,
    IntentPreviewResponse,
    TopologyHost,
    TopologyActivationRequest,
    TopologyCatalogResponse,
    TopologyDefinition,
    TopologyDefinitionInput,
    TopologyDuplicateRequest,
    TopologyExportResponse,
    TopologyLink,
    TopologyRenameRequest,
    TopologyResponse,
    TopologySwitch,
    TopologyUpdateRequest,
    TopologyVersionsResponse,
)
from backend.api.services.evidence import (
    EvidenceError,
    EvidenceNotFoundError,
    get_execution,
    list_executions,
)
from backend.api.services.execution_manager import ExecutionBusyError, ExecutionManager
from backend.api.services.preview_store import PreviewNotFoundError, PreviewStore
from backend.api.services.topology_catalog import (
    TopologyCatalog,
    TopologyCatalogError,
    TopologyNotFoundError,
    TopologyVersionConflictError,
)
from backend.api.services.worker_client import (
    WorkerProtocolError,
    WorkerUnavailableError,
    call_worker,
)
from backend.capabilities import ExecutionMode, resolve_capabilities
from backend.execution.models import TopologySnapshot
from backend.llm.base import (
    LLMClarificationRequiredError,
    LLMParseError,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)
from backend.llm.factory import get_llm_provider
from backend.models.canonical_intent import CanonicalIntent
from backend.models.intent import StructuredIntent
from backend.models.intent_normalization import normalize_intent
from backend.models.fingerprints import model_fingerprint
from backend.models.network import TopologyGraph
from backend.models.topology_definition import TopologyMode
from backend.planner.topology_planning import plan_on_topology

LOGGER = logging.getLogger("intentflow.api")
RYU_BASE_URL = os.environ.get("INTENTFLOW_RYU_BASE_URL", "http://127.0.0.1:8080")
SESSION_COOKIE_NAME = "intentflow_session"


def _cookie_secure_enabled() -> bool:
    value = os.environ.get("INTENTFLOW_COOKIE_SECURE", "").strip().lower()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(
        "INTENTFLOW_COOKIE_SECURE must be true/false, yes/no, on/off, or 1/0."
    )


def _auth_disabled_for_local_development() -> bool:
    value = os.environ.get("INTENTFLOW_AUTH_DISABLED", "false").strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError("INTENTFLOW_AUTH_DISABLED must be true or false.")
    if value != "true":
        return False

    environment = os.environ.get("INTENTFLOW_ENVIRONMENT", "production").strip().lower()
    host = os.environ.get("INTENTFLOW_API_HOST", "127.0.0.1")
    if environment != "development":
        raise RuntimeError(
            "INTENTFLOW_AUTH_DISABLED=true is permitted only when "
            "INTENTFLOW_ENVIRONMENT=development."
        )
    if not _is_loopback_host(host):
        raise RuntimeError(
            "INTENTFLOW_AUTH_DISABLED=true requires INTENTFLOW_API_HOST "
            "to be localhost, 127.0.0.1, or ::1."
        )
    return True


def create_app(
    *,
    worker_call_fn: Callable = call_worker,
    enforce_unprivileged: bool = True,
    api_token: str | None = None,
    topology_catalog: TopologyCatalog | None = None,
) -> FastAPI:
    execution_manager = ExecutionManager(worker_call_fn)
    preview_store = PreviewStore()
    topology_catalog = topology_catalog or TopologyCatalog()
    auth_disabled = _auth_disabled_for_local_development()
    access_control = APIAccessControl(
        os.environ.get("INTENTFLOW_API_TOKEN") if api_token is None else api_token
    )
    cookie_secure = _cookie_secure_enabled()
    origins = [
        origin.strip()
        for origin in os.environ.get(
            "INTENTFLOW_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not auth_disabled:
            access_control.validate_configuration()
        if enforce_unprivileged and hasattr(os, "geteuid") and os.geteuid() == 0:
            raise RuntimeError(
                "The FastAPI process must run as an unprivileged user. "
                "Use the separate privileged worker for Mininet/Ryu operations."
            )
        host = os.environ.get("INTENTFLOW_API_HOST", "127.0.0.1")
        if not _is_loopback_host(host):
            raise RuntimeError(
                "The API only binds to loopback. Use an authenticated TLS reverse "
                "proxy for remote access."
            )
        yield
        execution_manager.close()

    app = FastAPI(
        title="IntentFlow SDN API",
        version="1.0.0",
        description=(
            "Typed, local API adapter for declarative SDN intents. "
            "It never accepts commands or OpenFlow rules from clients."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.execution_manager = execution_manager
    app.state.preview_store = preview_store
    app.state.topology_catalog = topology_catalog
    app.state.access_control = access_control
    app.state.auth_disabled = auth_disabled

    def require_api_access(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> None:
        if auth_disabled:
            return
        bearer = _bearer_token(authorization)
        if access_control.accepts_api_token(bearer):
            return
        cookie_session = _session_cookie(request)
        if access_control.accepts_session(cookie_session):
            if request.method not in {"GET", "HEAD", "OPTIONS"} and (
                request.headers.get("origin") not in origins
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Cookie-authenticated writes require an allowed Origin.",
                )
            return
        raise HTTPException(
            status_code=401,
            detail="API authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.post("/api/v1/auth/session")
    def create_session(
        request: Request,
        response: Response,
        authorization: str | None = Header(default=None),
    ) -> dict[str, int | bool]:
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            raise HTTPException(status_code=403, detail="Origin is not allowed.")
        if auth_disabled:
            return {"authenticated": False, "expires_in": 0}
        if not access_control.accepts_api_token(_bearer_token(authorization)):
            raise HTTPException(
                status_code=401,
                detail="API authentication is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        session_id = access_control.create_session()
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            secure=cookie_secure,
            samesite="strict",
            path="/api/v1",
        )
        return {"authenticated": True, "expires_in": SESSION_TTL_SECONDS}

    @app.delete(
        "/api/v1/auth/session",
        dependencies=[Depends(require_api_access)],
    )
    def delete_session(request: Request, response: Response) -> dict[str, bool]:
        access_control.revoke_session(_session_cookie(request))
        response.delete_cookie(
            SESSION_COOKIE_NAME,
            path="/api/v1",
            httponly=True,
            secure=cookie_secure,
            samesite="strict",
        )
        return {"authenticated": False}

    @app.get(
        "/api/v1/health",
        response_model=ApiHealthResponse,
        dependencies=[Depends(require_api_access)],
    )
    def health() -> ApiHealthResponse:
        try:
            worker_health = _check_worker_ready(worker_call_fn)
            worker_status = Availability.CONNECTED
        except (WorkerUnavailableError, WorkerProtocolError):
            worker_health = {}
            worker_status = Availability.DISCONNECTED

        ryu_status = _check_ryu_status()
        return ApiHealthResponse(
            backend_status=Availability.CONNECTED,
            ryu_status=ryu_status,
            mininet_status=Availability.UNKNOWN,
            current_execution_status=execution_manager.active_status,
            checked_at=datetime.now(timezone.utc),
            details={
                "worker": worker_status.value,
                "worker_operation": (
                    "BUSY"
                    if worker_health.get("operation_busy") is True
                    else "IDLE"
                    if worker_status == Availability.CONNECTED
                    else "UNKNOWN"
                ),
                "mininet": (
                    "No persistent Mininet network is assumed; live topology "
                    "availability is checked only when discovery or execution is requested."
                ),
                "ryu": None,
            },
        )

    @app.get(
        "/api/v1/topologies",
        response_model=TopologyCatalogResponse,
        dependencies=[Depends(require_api_access)],
    )
    def list_topologies() -> TopologyCatalogResponse:
        return TopologyCatalogResponse(topologies=topology_catalog.list())

    @app.post(
        "/api/v1/topologies",
        response_model=TopologyDefinition,
        status_code=201,
        dependencies=[Depends(require_api_access)],
    )
    def create_topology(body: TopologyDefinitionInput) -> TopologyDefinition:
        try:
            return topology_catalog.create(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except TopologyCatalogError as exc:
            LOGGER.exception("Could not save topology definition")
            raise HTTPException(
                status_code=500,
                detail="Topology could not be stored.",
            ) from exc

    @app.post(
        "/api/v1/topologies/import",
        response_model=TopologyDefinition,
        status_code=201,
        dependencies=[Depends(require_api_access)],
    )
    def import_topology(body: TopologyExportResponse) -> TopologyDefinition:
        try:
            return topology_catalog.create(body.topology)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/v1/topologies/active",
        response_model=ActiveTopologyResponse,
        dependencies=[Depends(require_api_access)],
    )
    def get_active_topology() -> ActiveTopologyResponse:
        topology = topology_catalog.active()
        return ActiveTopologyResponse(topology=topology, active=topology is not None)

    @app.delete(
        "/api/v1/topologies/active",
        response_model=ActiveTopologyResponse,
        dependencies=[Depends(require_api_access)],
    )
    def clear_active_topology() -> ActiveTopologyResponse:
        topology_catalog.deactivate()
        return ActiveTopologyResponse(topology=None, active=False)

    @app.post(
        "/api/v1/topologies/{topology_id}/activate",
        response_model=ActiveTopologyResponse,
        dependencies=[Depends(require_api_access)],
    )
    def activate_topology(
        topology_id: UUID,
        body: TopologyActivationRequest,
    ) -> ActiveTopologyResponse:
        try:
            topology = topology_catalog.activate(topology_id, body.version)
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ActiveTopologyResponse(topology=topology, active=True)

    @app.get(
        "/api/v1/topologies/{topology_id}/versions",
        response_model=TopologyVersionsResponse,
        dependencies=[Depends(require_api_access)],
    )
    def get_topology_versions(topology_id: UUID) -> TopologyVersionsResponse:
        try:
            return TopologyVersionsResponse(
                versions=topology_catalog.versions(topology_id)
            )
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/topologies/{topology_id}/duplicate",
        response_model=TopologyDefinition,
        status_code=201,
        dependencies=[Depends(require_api_access)],
    )
    def duplicate_topology(
        topology_id: UUID,
        body: TopologyDuplicateRequest,
    ) -> TopologyDefinition:
        try:
            return topology_catalog.duplicate(topology_id, body.name)
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/topologies/{topology_id}/export",
        response_model=TopologyExportResponse,
        dependencies=[Depends(require_api_access)],
    )
    def export_topology(topology_id: UUID) -> TopologyExportResponse:
        try:
            topology = topology_catalog.get(topology_id)
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return TopologyExportResponse(
            topology=TopologyDefinitionInput(
                name=topology.name,
                mode=topology.mode,
                graph=topology.graph,
                positions=topology.positions,
            )
        )

    @app.get(
        "/api/v1/topologies/{topology_id}",
        response_model=TopologyDefinition,
        dependencies=[Depends(require_api_access)],
    )
    def get_topology(
        topology_id: UUID,
        version: int | None = Query(default=None, ge=1),
    ) -> TopologyDefinition:
        try:
            return topology_catalog.get(topology_id, version)
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put(
        "/api/v1/topologies/{topology_id}",
        response_model=TopologyDefinition,
        dependencies=[Depends(require_api_access)],
    )
    def update_topology(
        topology_id: UUID,
        body: TopologyUpdateRequest,
    ) -> TopologyDefinition:
        try:
            return topology_catalog.update(
                topology_id,
                body.expected_version,
                TopologyDefinitionInput(
                    name=body.name,
                    mode=body.mode,
                    graph=body.graph,
                    positions=body.positions,
                ),
            )
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TopologyVersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/topologies/{topology_id}/rename",
        response_model=TopologyDefinition,
        dependencies=[Depends(require_api_access)],
    )
    def rename_topology(
        topology_id: UUID,
        body: TopologyRenameRequest,
    ) -> TopologyDefinition:
        try:
            return topology_catalog.rename(
                topology_id,
                body.expected_version,
                body.name,
            )
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TopologyVersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/topologies/{topology_id}",
        status_code=204,
        dependencies=[Depends(require_api_access)],
    )
    def delete_topology(topology_id: UUID) -> Response:
        try:
            topology_catalog.delete(topology_id)
        except TopologyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get(
        "/api/v1/topology",
        response_model=TopologyResponse,
        dependencies=[Depends(require_api_access)],
    )
    def topology() -> TopologyResponse:
        try:
            data = worker_call_fn("topology", timeout_s=120)
            return _topology_response(data)
        except (WorkerUnavailableError, WorkerProtocolError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Live topology is unavailable: {exc}",
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.exception("Invalid topology response from SDN worker")
            raise HTTPException(
                status_code=502,
                detail="The SDN worker returned an invalid topology snapshot.",
            ) from exc

    @app.post(
        "/api/v1/intents/preview",
        response_model=IntentPreviewResponse,
        dependencies=[Depends(require_api_access)],
    )
    def preview_intent(body: IntentPreviewRequest) -> IntentPreviewResponse:
        parser_name = "structured"
        parser_kind = "STRUCTURED"
        if isinstance(body.structured_intent, CanonicalIntent):
            canonical = body.structured_intent
        elif isinstance(body.structured_intent, StructuredIntent):
            try:
                canonical = normalize_intent(body.structured_intent).canonical
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Intent is invalid: {exc}",
                ) from exc
        else:
            try:
                provider = get_llm_provider()
            except ValueError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"LLM provider configuration is invalid: {exc}",
                ) from exc
            parser_name = provider.name
            parser_kind = "MOCK" if provider.name.lower().startswith("mock") else "PROVIDER"
            if body.natural_language is None:
                raise HTTPException(
                    status_code=422,
                    detail="Natural-language intent is required.",
                )
            try:
                parsed = provider.parse_intent(
                    body.natural_language,
                    source=body.source,
                    destination=body.destination,
                )
            except LLMClarificationRequiredError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Clarification required: {exc}",
                ) from exc
            except LLMProviderUnavailableError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"LLM provider is unavailable: {exc}",
                ) from exc
            except LLMProviderResponseError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"LLM provider rejected the request: {exc}",
                ) from exc
            except LLMParseError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Intent could not be parsed: {exc}",
                ) from exc
            try:
                canonical = normalize_intent(parsed).canonical
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Intent is invalid: {exc}",
                ) from exc

        if (
            canonical.scope.source != body.source
            or canonical.scope.destination != body.destination
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Parsed intent endpoints must match the selected source and "
                    "destination hosts."
                ),
            )

        topology_status = Availability.DISCONNECTED
        graph = None
        topology_identity: dict[str, object] | None = None
        topology_mode: TopologyMode | None = None
        explanation: list[str] = []
        active_design = topology_catalog.active()
        if active_design is not None:
            graph = active_design.graph
            topology_mode = TopologyMode.DESIGN
            topology_status = Availability.UNKNOWN
            topology_identity = {
                "id": str(active_design.id),
                "name": active_design.name,
                "version": active_design.version,
                "mode": TopologyMode.DESIGN.value,
                "fingerprint": model_fingerprint(graph),
            }
            explanation.append(
                f"Planning against active DESIGN topology "
                f"{active_design.name!r}, version {active_design.version}. "
                "This does not represent a running Mininet or LIVE network."
            )
        else:
            try:
                topology_data = worker_call_fn("topology", timeout_s=120)
                topology_snapshot = _topology_response(topology_data)
                topology_mode = TopologyMode.LIVE
                topology_identity = {
                    "id": None,
                    "name": "Worker-discovered topology",
                    "version": None,
                    "mode": TopologyMode.LIVE.value,
                    "fingerprint": topology_snapshot.topology_fingerprint,
                    "snapshot_timestamp": topology_snapshot.snapshot_timestamp,
                    "snapshot_status": topology_snapshot.snapshot_status,
                }
                if topology_snapshot.snapshot_status == "COMPLETE":
                    graph = TopologyGraph.model_validate(topology_data["graph"])
                    topology_status = Availability.CONNECTED
                else:
                    topology_status = Availability.UNKNOWN
                    explanation.append(
                        "The live topology snapshot is incomplete; it is not used "
                        "as verified planning input."
                    )
            except (WorkerUnavailableError, WorkerProtocolError) as exc:
                explanation.append(
                    f"Live topology discovery is unavailable: {exc}"
                )
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.exception("Invalid topology response while previewing intent")
                explanation.append(
                    "Live topology discovery returned an invalid response."
                )

        if graph is not None:
            for endpoint_role, endpoint in (
                ("Source", canonical.scope.source),
                ("Destination", canonical.scope.destination),
            ):
                if endpoint not in graph.hosts:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"{endpoint_role} host {endpoint!r} is not present in "
                            f"the active {topology_mode.value if topology_mode else 'selected'} "
                            "topology. Select a host from the topology host list or "
                            "activate a topology containing it."
                        ),
                    )

        resolution = resolve_capabilities(
            canonical,
            graph,
            execution_mode=ExecutionMode.GENERALIZED,
        )
        findings = _capability_findings(resolution)
        if parser_kind == "MOCK":
            explanation.append(
                "The deterministic mock parser was used; this was not an actual LLM call."
            )
        eligible = (
            topology_mode == TopologyMode.LIVE
            and topology_status == Availability.CONNECTED
            and resolution.capability_ready
            and not canonical.requested_actions
        )
        if canonical.requested_actions:
            findings.append(
                "Requested actions are not supported by this execution pipeline."
            )
        if not resolution.capability_ready:
            explanation.extend(resolution.reasons)

        planning_result = None
        if graph is not None:
            try:
                planning_result = plan_on_topology(canonical, graph)
                planning_result["topology_identity"] = topology_identity
                explanation.append(planning_result["provenance"])
                if planning_result["selection_reason"]:
                    explanation.append(planning_result["selection_reason"])
            except (ValueError, TypeError) as exc:
                LOGGER.exception("Could not plan candidates against selected topology")
                explanation.append(
                    f"Topology path planning could not be completed: {exc}"
                )
        elif active_design is None:
            explanation.append(
                "No active topology is available. Create or import a DESIGN "
                "topology and activate it, or make a complete LIVE discovery "
                "available before planning."
            )

        planning_eligible = None
        if planning_result is not None:
            if planning_result["status"] == "SELECTED":
                planning_eligible = True
            elif planning_result["status"] in {"NO_PATH", "NO_ELIGIBLE_PATH"}:
                planning_eligible = False

        if topology_mode == TopologyMode.DESIGN:
            explanation.append(
                "DESIGN planning cannot be executed on the network. Saving or "
                "activating a design never starts Mininet or installs flows."
            )
        execution_unavailable_reason = None
        if not eligible:
            if topology_mode == TopologyMode.DESIGN:
                execution_unavailable_reason = (
                    "DESIGN topologies support planning only and cannot be executed."
                )
            elif topology_mode != TopologyMode.LIVE or topology_status != Availability.CONNECTED:
                execution_unavailable_reason = (
                    "A complete, verified LIVE topology is required for execution."
                )
            elif canonical.requested_actions:
                execution_unavailable_reason = (
                    "Requested actions are not supported by this execution pipeline."
                )
            elif not resolution.capability_ready:
                execution_unavailable_reason = (
                    "One or more requested capabilities are not ready for execution."
                )

        preview_id = preview_store.save(canonical, eligible)
        return IntentPreviewResponse(
            preview_id=preview_id,
            parser=parser_name,
            parser_kind=parser_kind,
            interpretation_status="VALID",
            canonical_intent=canonical,
            capability_resolution=resolution.model_dump(mode="json"),
            planning_eligible=planning_eligible,
            execution_status="AVAILABLE" if eligible else "UNAVAILABLE",
            execution_unavailable_reason=execution_unavailable_reason,
            execution_eligible=eligible,
            topology_status=topology_status,
            topology_identity=topology_identity,
            planning_result=planning_result,
            unsupported_or_conditional=list(dict.fromkeys(findings)),
            explanation=list(dict.fromkeys(explanation)),
        )

    @app.post(
        "/api/v1/executions",
        response_model=ExecutionAcceptedResponse,
        status_code=202,
        dependencies=[Depends(require_api_access)],
    )
    def execute_intent(body: ExecuteIntentRequest) -> ExecutionAcceptedResponse:
        if execution_manager.is_busy():
            raise HTTPException(
                status_code=409,
                detail="Another live execution is already running.",
            )
        if body.preview_id is not None:
            try:
                intent, eligible = preview_store.get(body.preview_id)
            except PreviewNotFoundError as exc:
                raise HTTPException(
                    status_code=410,
                    detail="Intent preview is expired, unknown, or already used.",
                ) from exc
            if not eligible:
                raise HTTPException(
                    status_code=422,
                    detail="The intent preview is not eligible for execution.",
                )
        else:
            if body.canonical_intent is None:
                raise HTTPException(
                    status_code=422,
                    detail="A canonical intent or preview ID is required.",
                )
            intent = body.canonical_intent
            if intent.requested_actions:
                raise HTTPException(
                    status_code=422,
                    detail="Requested actions are not supported by this execution pipeline.",
                )
            try:
                topology_data = worker_call_fn("topology", timeout_s=120)
                topology_snapshot = _topology_response(topology_data)
                graph = TopologyGraph.model_validate(topology_data["graph"])
            except (WorkerUnavailableError, WorkerProtocolError) as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Live topology is unavailable: {exc}",
                ) from exc
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.exception("Invalid topology response for canonical execution")
                raise HTTPException(
                    status_code=502,
                    detail="The SDN worker returned an invalid topology snapshot.",
                ) from exc
            if topology_snapshot.snapshot_status != "COMPLETE":
                raise HTTPException(
                    status_code=422,
                    detail="Canonical intent cannot execute against an incomplete topology snapshot.",
                )
            resolution = resolve_capabilities(
                intent,
                graph,
                execution_mode=ExecutionMode.GENERALIZED,
            )
            if not resolution.capability_ready:
                reasons = "; ".join(resolution.reasons) or "Capability checks failed."
                raise HTTPException(
                    status_code=422,
                    detail=f"Canonical intent is not eligible for execution: {reasons}",
                )

        try:
            worker_health = _check_worker_ready(worker_call_fn)
        except (WorkerUnavailableError, WorkerProtocolError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Execution worker is unavailable: {exc}",
            ) from exc
        if worker_health.get("operation_busy") is True:
            raise HTTPException(
                status_code=409,
                detail="Another live topology or execution operation is active.",
            )

        if body.preview_id is not None:
            try:
                intent, eligible = preview_store.consume(body.preview_id)
            except PreviewNotFoundError as exc:
                raise HTTPException(
                    status_code=410,
                    detail="Intent preview is expired, unknown, or already used.",
                ) from exc
            if not eligible:
                raise HTTPException(
                    status_code=422,
                    detail="The intent preview is not eligible for execution.",
                )

        try:
            execution_uuid, accepted_at = execution_manager.submit(intent)
        except ExecutionBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ExecutionAcceptedResponse(
            execution_id=execution_uuid.hex,
            status="RUNNING",
            accepted_at=accepted_at,
            events_url=f"/api/v1/executions/{execution_uuid.hex}/events",
        )

    @app.get(
        "/api/v1/executions",
        response_model=list[ExecutionSummary],
        dependencies=[Depends(require_api_access)],
    )
    def executions(
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[ExecutionSummary]:
        try:
            persisted = list_executions(limit)
        except EvidenceError as exc:
            LOGGER.exception("Could not load persisted execution evidence")
            raise HTTPException(
                status_code=500,
                detail=f"Execution history could not be read: {exc}",
            ) from exc
        return sorted(
            persisted,
            key=lambda record: record.started_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:limit]

    @app.get(
        "/api/v1/executions/{execution_id}",
        response_model=ExecutionDetail,
        dependencies=[Depends(require_api_access)],
    )
    def execution_detail(execution_id: str) -> ExecutionDetail:
        if not _valid_execution_id(execution_id):
            raise HTTPException(status_code=404, detail="Execution not found.")
        try:
            return get_execution(execution_id)
        except EvidenceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EvidenceError as exc:
            LOGGER.exception("Could not read requested execution evidence")
            raise HTTPException(
                status_code=500,
                detail=f"Execution evidence could not be read: {exc}",
            ) from exc

    @app.get(
        "/api/v1/executions/{execution_id}/status",
        response_model=ExecutionStatusResponse,
        dependencies=[Depends(require_api_access)],
    )
    def execution_status(execution_id: str) -> ExecutionStatusResponse:
        if not _valid_execution_id(execution_id):
            raise HTTPException(status_code=404, detail="Execution not found.")
        status = execution_manager.execution_status(execution_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Execution not found.")
        current_status, events = status
        return ExecutionStatusResponse(
            execution_id=execution_id,
            status=current_status,
            events=events,
        )

    @app.websocket("/api/v1/executions/{execution_id}/events")
    async def execution_events(websocket: WebSocket, execution_id: str) -> None:
        origin = websocket.headers.get("origin")
        session_id = _session_cookie(websocket)
        if (
            origin not in origins
            or (
                not auth_disabled
                and not access_control.accepts_session(session_id)
            )
        ):
            await websocket.close(code=4401, reason="API authentication required.")
            return
        if not _valid_execution_id(execution_id):
            await websocket.close(code=4404, reason="Execution not found.")
            return
        await websocket.accept()
        try:
            async for event in execution_manager.stream_events(execution_id):
                await websocket.send_json(event.model_dump(mode="json"))
        except KeyError:
            await websocket.close(code=4404, reason="Execution not found.")
        except WebSocketDisconnect:
            return

    return app


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, credentials = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not credentials:
        return None
    return credentials


def _session_cookie(request: Request | WebSocket) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)


def _topology_response(data: dict) -> TopologyResponse:
    graph = TopologyGraph.model_validate(data["graph"])
    snapshot = TopologySnapshot.model_validate(data["snapshot"])
    if snapshot.configured_topology != graph:
        raise ValueError("Worker graph and topology snapshot inventory do not match.")
    if data.get("topology_fingerprint") != snapshot.topology_fingerprint:
        raise ValueError("Worker topology fingerprint does not match the snapshot.")
    snapshot_ports = {
        (port.dpid, port.port_no): port
        for port in snapshot.port_states
    }
    connected = set(snapshot.connected_switch_dpids)
    switches = [
        TopologySwitch(
            name=name,
            dpid=dpid,
            status=(
                Availability.CONNECTED
                if dpid in connected
                else Availability.DISCONNECTED
            ),
        )
        for name, dpid in sorted(graph.switches.items())
    ]
    hosts = [
        TopologyHost(
            name=host.name,
            ip=host.ip,
            mac=host.mac,
            switch=host.switch,
            switch_port=host.switch_port,
            attachment_capacity_mbps=host.attachment_capacity_mbps,
            attachment_delay_ms=host.attachment_delay_ms,
            attachment_packet_loss_percent=host.attachment_packet_loss_percent,
            attachment_admin_up=host.attachment_admin_up,
        )
        for _, host in sorted(graph.hosts.items())
    ]
    links: list[TopologyLink] = []
    for host in graph.hosts.values():
        port = snapshot_ports.get(
            (graph.switches[host.switch], host.switch_port)
        )
        links.append(
            TopologyLink(
                node_a=host.name,
                port_a=None,
                node_b=host.switch,
                port_b=host.switch_port,
                capacity_mbps=host.attachment_capacity_mbps,
                delay_ms=host.attachment_delay_ms,
                packet_loss_percent=host.attachment_packet_loss_percent,
                admin_up=host.attachment_admin_up,
                status=_port_status(port),
            )
        )
    for link in graph.links:
        port_a = snapshot_ports.get((graph.switches[link.node_a], link.port_a))
        port_b = snapshot_ports.get((graph.switches[link.node_b], link.port_b))
        status_a, status_b = _port_status(port_a), _port_status(port_b)
        status = (
            Availability.CONNECTED
            if status_a == status_b == Availability.CONNECTED
            else Availability.DISCONNECTED
            if Availability.DISCONNECTED in {status_a, status_b}
            else Availability.UNKNOWN
        )
        links.append(
            TopologyLink(
                node_a=link.node_a,
                port_a=link.port_a,
                node_b=link.node_b,
                port_b=link.port_b,
                capacity_mbps=link.bw_mbps,
                delay_ms=link.delay_ms,
                packet_loss_percent=link.packet_loss_percent,
                admin_up=link.admin_up,
                status=status,
            )
        )
    return TopologyResponse(
        switches=switches,
        hosts=hosts,
        links=links,
        topology_fingerprint=data["topology_fingerprint"],
        snapshot_timestamp=snapshot.captured_at,
        snapshot_status=snapshot.status.value,
        source=(
            "Mininet configured inventory and Ryu datapath/port-description "
            "snapshot; no fabricated topology values."
        ),
    )


def _port_status(port) -> Availability:
    if port is None or port.present is not True:
        return Availability.UNKNOWN
    if port.admin_up is False or port.link_up is False:
        return Availability.DISCONNECTED
    if port.admin_up is True and port.link_up is True:
        return Availability.CONNECTED
    return Availability.UNKNOWN


def _capability_findings(resolution) -> list[str]:
    findings: list[str] = []
    requirements = (
        resolution.constraints
        + ([resolution.optimization] if resolution.optimization is not None else [])
        + resolution.actions
    )
    for requirement in requirements:
        for field in (
            "recognized",
            "validated",
            "measurable",
            "plannable",
            "executable",
            "generalized_objective_ranking",
        ):
            check = getattr(requirement, field, None)
            if check is None or check.status.value == "SUPPORTED":
                continue
            findings.extend(check.reasons)
            findings.extend(check.missing_conditions)
    if resolution.scope.status.value != "SUPPORTED":
        findings.extend(resolution.scope.reasons)
        findings.extend(resolution.scope.missing_conditions)
    if resolution.topology.status.value != "SUPPORTED":
        findings.extend(resolution.topology.reasons)
        findings.extend(resolution.topology.missing_conditions)
    return findings


def _check_ryu_status() -> Availability:
    parsed = urlparse(RYU_BASE_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        LOGGER.error("Ignoring non-loopback Ryu URL in API health configuration.")
        return Availability.UNKNOWN
    try:
        with urlopen(f"{RYU_BASE_URL.rstrip('/')}/stats/switches", timeout=0.5) as response:
            if response.status != 200:
                return Availability.DISCONNECTED
            payload = json.load(response)
            if not isinstance(payload, list) or any(
                type(dpid) is not int or dpid <= 0 for dpid in payload
            ):
                return Availability.UNKNOWN
            return Availability.CONNECTED
    except (OSError, URLError, TimeoutError, ValueError):
        return Availability.DISCONNECTED


def _check_worker_ready(worker_call_fn: Callable) -> dict:
    result = worker_call_fn("health", timeout_s=1)
    if not isinstance(result, dict) or result.get("ready") is not True:
        raise WorkerProtocolError("The SDN worker did not report ready.")
    return result


def _is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _valid_execution_id(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"(?:[0-9a-f]{32}|[0-9]+)", value))


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("INTENTFLOW_API_HOST", "127.0.0.1")
    if not _is_loopback_host(host):
        raise RuntimeError("INTENTFLOW_API_HOST must be loopback.")
    uvicorn.run(
        "backend.api.main:app",
        host=host,
        port=int(os.environ.get("INTENTFLOW_API_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
