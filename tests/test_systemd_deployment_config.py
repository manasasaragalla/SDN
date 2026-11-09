from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _unit(name: str) -> str:
    return (ROOT / "deploy" / "systemd" / name).read_text(encoding="utf-8")


def test_worker_and_api_units_share_evidence_paths_and_group_boundary():
    worker = _unit("intentflow-worker.service")
    api = _unit("intentflow-api.service")

    for unit in (worker, api):
        assert "INTENTFLOW_EVIDENCE_JSON_DIR=/var/lib/intentflow/results" in unit
        assert (
            "INTENTFLOW_EVIDENCE_MARKDOWN_DIR=/var/lib/intentflow/reports"
            in unit
        )

    assert "User=root" in worker
    assert "Group=intentflow-api" in worker
    assert "RuntimeDirectory=intentflow" in worker
    assert "RuntimeDirectoryMode=0750" in worker
    assert "EnvironmentFile=/etc/intentflow/worker.env" in worker
    assert "GID_PLACEHOLDER" not in worker
    assert "--allowed-gid GID_PLACEHOLDER" not in worker

    assert "User=intentflow-api" in api
    assert "Group=intentflow-api" in api
    assert "EnvironmentFile=/etc/intentflow/api.env" in api
    assert "Environment=INTENTFLOW_ENVIRONMENT=production" in api
    assert "Environment=INTENTFLOW_AUTH_DISABLED=false" in api
    assert "UnsetEnvironment=INTENTFLOW_AUTH_DISABLED" in api
    assert "ReadOnlyPaths=/opt/intentflow-sdn /var/lib/intentflow" in api
    assert "CapabilityBoundingSet=" in api


def test_deployment_guide_uses_real_authenticated_health_route():
    guide = (ROOT / "docs" / "systemd-deployment.md").read_text(
        encoding="utf-8"
    )
    assert "GET /api/v1/health" in guide
    assert "HTTP 401" in guide
    assert "/api/health" in guide
    assert "Runs as `root:intentflow-api`" in guide
    assert "Runs as `root:root`." not in guide
    assert "GID_PLACEHOLDER" not in guide
    assert "systemctl enable --now intentflow-worker.service" in guide
    assert "No deployment, service startup" in guide
    assert "unsets `INTENTFLOW_AUTH_DISABLED`" in guide


def test_worker_environment_example_does_not_supply_invalid_gid():
    example = _unit("intentflow-worker.env.example")
    assert re.search(r"^INTENTFLOW_API_GID=", example, flags=re.MULTILINE) is None
    assert "numeric group value" in example


def test_deployment_guide_refuses_existing_release_and_unit_files():
    guide = (ROOT / "docs" / "systemd-deployment.md").read_text(
        encoding="utf-8"
    )
    assert "This is a first-install procedure, not an in-place upgrade." in guide
    assert 'sudo test -e "$path" || sudo test -L "$path"' in guide
    assert "sudo mkdir -m 0750 -- \"$RELEASE_DIR\"" in guide
    assert "sudo mv -Tn -- /opt/intentflow-sdn \"$FAILED_RELEASE\"" in guide
    assert 'sudo test -e "$unit" || sudo test -L "$unit"' in guide
    assert "Preserving existing unit; stop and review" in guide


def test_api_adapter_keeps_development_and_protected_worker_startup_separate():
    guide = (ROOT / "docs" / "api-adapter.md").read_text(encoding="utf-8")
    assert "## Local API and frontend development" in guide
    assert "## Protected systemd deployment" in guide
    assert "Do **not** manually start the root worker from this checkout." in guide
    assert "INTENTFLOW_API_TOKEN" in guide
    assert "INTENTFLOW_EVIDENCE_JSON_DIR" in guide
    assert "INTENTFLOW_EVIDENCE_MARKDOWN_DIR" in guide
    assert "## First live end-to-end test" not in guide
    assert "INTENTFLOW_AUTH_DISABLED=true" in guide
    assert "INTENTFLOW_ENVIRONMENT=development" in guide
    assert "without credentials or cookies" in guide


def test_local_environment_example_enables_only_loopback_development_bypass():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "INTENTFLOW_ENVIRONMENT=development" in example
    assert "INTENTFLOW_AUTH_DISABLED=true" in example
    assert "INTENTFLOW_API_HOST=127.0.0.1" in example


def test_frontend_local_api_client_does_not_send_authentication():
    api_client = (
        ROOT / "frontend" / "src" / "lib" / "api-client.ts"
    ).read_text(encoding="utf-8")
    settings = (
        ROOT / "frontend" / "src" / "components" / "settings" / "settings-page.tsx"
    ).read_text(encoding="utf-8")
    assert 'credentials: AUTH_DISABLED ? "omit" : "include"' in api_client
    assert "AUTH_DISABLED ? " in api_client
    assert "AUTH_DISABLED &&" in settings
    assert "Authorization:" in settings
    assert "API access token" in settings
    assert "new WebSocket" not in (
        ROOT / "frontend" / "src" / "components" / "intents" / "intent-page.tsx"
    ).read_text(encoding="utf-8")
