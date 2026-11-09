# Local FastAPI adapter

The adapter exposes the deterministic backend to the dashboard. It accepts
validated declarative intents; it does not accept shell commands, OpenFlow
rules, arbitrary process arguments, or client-selected evidence paths. The
orchestration remains responsible for capability checks, enumeration,
measurement, compilation, deployment, verification, cleanup, and evidence.

## Security boundary

The API must run as an unprivileged user and bind only to loopback. It refuses
root startup and non-loopback binds. The privileged worker runs separately and
accepts only the `health`, `topology`, and validated `execute` operations over
a Unix socket. The socket is root-owned, grouped to `intentflow-api`, and
mode `0660`; membership in that group is privileged because it permits live
topology operations and execution requests. Do not expose the API or socket to
an untrusted network. Remote dashboard access requires an authenticated TLS
reverse proxy while the API remains loopback-bound.

The worker verifies that its application, interpreter, and Ryu executable are
under root-owned paths that are not writable by group or other users. Never
run the privileged worker from `/mnt/e/SdnProject` or another shared or
developer-writable location.

Production authentication requires an API token of at least 32 bytes of
high-entropy secret material. The browser exchanges it for an `HttpOnly`,
`SameSite=Strict` session cookie. Sessions are in-memory, expire after eight
hours, and are invalidated when the API restarts. Never put a production token
in a `NEXT_PUBLIC_*` setting, unit file, or command-line argument.

Local development may opt out of API authentication with
`INTENTFLOW_AUTH_DISABLED=true` only when `INTENTFLOW_ENVIRONMENT=development`
and `INTENTFLOW_API_HOST` is `127.0.0.1`, `localhost`, or `::1`. Authentication
remains enabled by default. The API refuses to start if the bypass is enabled
outside development or with a non-loopback bind. Never use this setting for a
protected or externally accessible deployment.

For local HTTP use `INTENTFLOW_COOKIE_SECURE=false`; set it to `true` behind
HTTPS. The browser URL, `NEXT_PUBLIC_API_BASE_URL`, CORS origin, and WebSocket
URL must consistently use either `localhost` or `127.0.0.1`. Mixing hostnames
can break cookies and origin validation.

## Local API and frontend development

This mode starts only FastAPI and the frontend as the current unprivileged
developer. It deliberately does **not** start the privileged worker, Ryu,
Mininet, or Open vSwitch. Health may report the worker as disconnected, and
live topology, preview, and execution flows requiring the worker are not
available. Use API tests for mocked worker interactions.

From the project checkout, load the development-only settings from the root
`.env.example` (or set the same values in the shell) and configure disposable
evidence directories. This mode does not need an API token, Bearer header, or
browser session:

```bash
cd /mnt/e/SdnProject
set -a
source .env.example
set +a
export INTENTFLOW_API_HOST=127.0.0.1
export INTENTFLOW_API_PORT=8000
export INTENTFLOW_CORS_ORIGINS=http://127.0.0.1:3000
DEV_EVIDENCE_ROOT="$(mktemp -d /tmp/intentflow-dev.XXXXXX)"
export INTENTFLOW_EVIDENCE_JSON_DIR="$DEV_EVIDENCE_ROOT/results"
export INTENTFLOW_EVIDENCE_MARKDOWN_DIR="$DEV_EVIDENCE_ROOT/reports"
export LLM_PROVIDER=mock
mkdir "$INTENTFLOW_EVIDENCE_JSON_DIR" "$INTENTFLOW_EVIDENCE_MARKDOWN_DIR"
chmod 2750 "$INTENTFLOW_EVIDENCE_JSON_DIR" "$INTENTFLOW_EVIDENCE_MARKDOWN_DIR"
python3 -m backend.api.main
```

In another terminal, run the dashboard with the same loopback hostname:

```bash
cd /mnt/e/SdnProject/frontend
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 \
NEXT_PUBLIC_INTENTFLOW_AUTH_DISABLED=true \
  npm run dev -- --hostname 127.0.0.1 --port 3000
```

The dashboard checks `GET /api/v1/health` directly and sends API requests
without credentials or cookies. `POST /api/v1/auth/session` remains compatible
in bypass mode but does not create a session or cookie. Stop the API and
frontend with Ctrl+C. Development evidence under `/tmp` is disposable and is
not persistent deployment evidence.

Do **not** manually start the root worker from this checkout. Running the
worker requires a protected installation, prepared socket directory, numeric
API GID configuration, and the target Mininet/OVS environment. Follow only
the protected systemd procedure below for live worker operation.

## Protected systemd deployment

Protected deployment uses two separate systemd services:

- `intentflow-worker.service`: root process with primary group
  `intentflow-api`; owns `/run/intentflow/worker.sock` and writes evidence.
- `intentflow-api.service`: unprivileged `intentflow-api` account; loopback
  API, read-only release and evidence access, and token loaded from
  `/etc/intentflow/api.env`.

Both services must use the same persistent evidence paths:
`INTENTFLOW_EVIDENCE_JSON_DIR=/var/lib/intentflow/results` and
`INTENTFLOW_EVIDENCE_MARKDOWN_DIR=/var/lib/intentflow/reports`. The evidence
directories must be root-owned, group `intentflow-api`, mode `2750`; evidence
files must be root-owned, group `intentflow-api`, mode `0640`. The API group
can traverse/read but cannot write these directories or files.

The API environment file must set `INTENTFLOW_API_TOKEN` to a real secret of
at least 32 bytes, `INTENTFLOW_API_HOST=127.0.0.1`, and the selected cookie,
CORS, and evidence settings. The worker environment must supply the numeric
`INTENTFLOW_API_GID` for the group created on the target. Do not copy example
environment files unchanged or store real secrets in the repository.
The API unit explicitly forces `INTENTFLOW_ENVIRONMENT=production` and
`INTENTFLOW_AUTH_DISABLED=false` after loading its environment file and unsets
the bypass variable for the service process. A development bypass setting
therefore cannot be enabled through that file.
For a protected frontend build, leave
`NEXT_PUBLIC_INTENTFLOW_AUTH_DISABLED` unset or set it to `false`; the
production token-to-session flow remains available in Settings.

Use the reviewed, first-install-only staging and no-overwrite safeguards in
[systemd-deployment.md](./systemd-deployment.md). That guide covers release
staging, prerequisites, accounts, evidence migration, unit installation,
verification, startup, and rollback. Do not combine a manually started worker
with the systemd worker; the worker's lock intentionally rejects a second
instance.

The evidence permission helper and unit tests validate metadata and API
retrieval within the test process. They do not prove access under distinct
Linux worker/API identities. Verify root/API-group ownership and actual
read-only API access on the target before treating deployment as ready.

## API surface

- `POST /api/v1/auth/session` exchanges a bearer token for an in-memory
  session; `DELETE /api/v1/auth/session` revokes it.
- `GET /api/v1/health` reports API, worker, Ryu, and execution availability.
  It does not start Mininet.
- `GET /api/v1/topology` requests live configured-topology and Ryu port state
  through the worker.
- `POST /api/v1/intents/preview` accepts natural language or structured
  intent, validates selectors, and returns canonical intent and capability
  results. Natural-language parsing uses the configured provider; mock parsing
  is explicitly labeled and is not an actual LLM call. The selected source and
  destination fields are explicit scope input when the request text omits
  endpoints; endpoints explicitly named in the request must match those
  selections.
- `POST /api/v1/executions` accepts one eligible, single-use preview or a
  canonical intent that is freshly checked against topology and capabilities.
  It returns `202 Accepted`; only one topology/execution worker operation runs
  at a time.
- `GET /api/v1/executions` and `GET /api/v1/executions/{id}` read persisted
  evidence only.
- `GET /api/v1/executions/{id}/status` returns the in-memory status and event
  history for frontend polling; it is not persisted across API restarts.
- `WS /api/v1/executions/{id}/events` reports acceptance, running, and
  terminal events for clients that use WebSockets. The browser dashboard uses
  credential-free status polling and fetches `GET /api/v1/executions/{id}`
  after a terminal status to show the persisted summary and evidence.

The mock provider's parsing coverage is narrower than the backend capability
registry; a mock parse failure does not show that the backend cannot represent
an intent. The current worker uses the configured diamond topology and
generalized constraint pipeline, not a general-purpose command runner.

## Deployment and live-verification status

The protected service definitions and instructions are preparation materials.
No target installation, service startup, Ryu/Mininet operation, topology
discovery, or flow deployment is implied by this document. WSL2 systemd,
Open vSwitch, Mininet namespaces, worker capabilities, listener behavior, and
separate-user evidence access still require target-host verification.
