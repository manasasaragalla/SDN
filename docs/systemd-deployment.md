# Protected systemd deployment on WSL2 Ubuntu

This is a deployment procedure for review, not a record that deployment has
occurred. No service, Mininet topology, Ryu controller, or flow should be
started until the operator explicitly performs the later deployment steps.

The development workspace `/mnt/e/SdnProject` is a Windows-mounted DrvFS
directory with permissive metadata in the current environment. It must not be
the working directory, Python path, release tree, or interpreter location for
the privileged worker. The intended release is a reviewed copy at
`/opt/intentflow-sdn`; persistent execution evidence is under
`/var/lib/intentflow`.

## What the code currently does

- `backend/orchestration/latency_evidence.py` writes generalized latency and
  generalized constraint JSON/Markdown evidence. Defaults remain
  `evaluation/results` and `docs/reports` relative to the application, but
  `INTENTFLOW_EVIDENCE_JSON_DIR` and
  `INTENTFLOW_EVIDENCE_MARKDOWN_DIR` override those directories.
- `backend/api/services/evidence.py` reads JSON from the configured JSON
  directory and checks for its paired Markdown file in the configured report
  directory.
- `backend/cli.py::_write_experiment_log` writes legacy `run_<integer>.json`
  files to the configured JSON directory. It now uses exclusive atomic
  publication instead of `write_text`, so it cannot replace an existing run.
- The evidence writer sets permissions on temporary files before publishing,
  uses no-replace hard-link publication, and removes only files it can confirm
  it published if the paired publication fails.
- Evidence directories must be real, non-symlink directories with owner/group
  and mode `root:intentflow-api 2750` in the protected worker. Files are
  `root:intentflow-api 0640`.
- The writer validates the final file and directory metadata. Its path checks
  still rely on the configured storage and every parent directory being
  protected from untrusted writes; keep `/var/lib/intentflow` and its ancestors
  root-owned and non-writable by group/other.
- No symlink is required in the release. Both units set the same two evidence
  path variables to `/var/lib/intentflow/results` and
  `/var/lib/intentflow/reports`.
- The evidence migration utility copies generalized execution JSON/Markdown
  and legacy `run_<integer>.json` files. It does not move or delete source
  evidence, does not overwrite destination names, and does not change existing
  destination directory permissions. Existing destination directories must
  already have the expected owner, group, and `2750` mode.
- `docs/reports/first_live_latency_demo.md` and the `evaluation/results/final/`
  research aggregates are retained in the reviewed release as historical
  project documentation/results. They are not API execution records and are
  not copied into the runtime evidence directories by the migration tool.

## WSL2 prerequisites and host validation

WSL2 systemd, Linux networking namespaces, Mininet, Open vSwitch, and the
target kernel must all work together. The following are not established by
source inspection:

1. `/etc/wsl.conf` enables systemd. After changing it, WSL must be restarted
   from Windows (for example `wsl.exe --shutdown`).
2. `systemd-analyze --version` supports all directives in the unit files.
3. Ubuntu's OVS package provides the `openvswitch-switch.service` unit named
   in `intentflow-worker.service`. Confirm its actual unit with
   `systemctl list-unit-files '*openvswitch*'` and adjust the dependency only
   after confirming the target host.
4. OVS starts and Mininet can create namespaces, veth pairs and bridges under
   the WSL2 kernel. This has not been live-tested as a systemd service.
5. The host provides Mininet Python modules and executables required by the
   application (`mnexec`, `ovs-vsctl`, `ip`, `ping`, `iperf3`, `ethtool`).
   The application virtual environment uses `--system-site-packages` for the
   host Mininet Python API; this is a deliberate host dependency boundary.
6. `/run/openvswitch` and `/run/netns` are available to the worker. `ProtectSystem=full`
   is used for the worker rather than `strict`, because Mininet/OVS create
   runtime state in `/run` and `/var`. `/opt/intentflow-sdn` remains explicitly
   read-only to the worker.
7. The worker's capability set (`CAP_CHOWN`, `CAP_DAC_OVERRIDE`, `CAP_KILL`,
   `CAP_NET_ADMIN`, `CAP_NET_RAW`, `CAP_SETGID`, `CAP_SETUID`, `CAP_SYS_ADMIN`,
   `CAP_SYS_CHROOT`) is sufficient. It is intentionally bounded but still
   powerful. Do not remove capabilities without tests on this exact host.
8. `NoNewPrivileges=yes`, `PrivateTmp=yes`, and namespace restrictions do not
   disrupt Mininet's `mnexec` and child processes.
9. systemd, OVS, and network operations work under the active WSL2 security
   policy. WSL2 behavior can differ from a full Ubuntu host.

The worker runs with `User=root` and `Group=intentflow-api`. systemd derives
the `RuntimeDirectory` ownership from those service credentials and creates
`/run/intentflow` as root, group `intentflow-api`, mode `0750`; the worker
verifies those attributes before binding its socket. This avoids
`RuntimeDirectoryGroup=`, which `systemd-analyze` on the current systemd 255
reports as an unknown key. The worker creates the socket as
`root:intentflow-api 0660` and the lock as `root:root 0600`.

## Preparation versus side effects

These are not interchangeable setup steps:

| Action | Effects |
|---|---|
| Inspect files, run dependency-lock validation, Python compilation, Pytest, TypeScript, ESLint, or `systemd-analyze verify` | Local/static validation only |
| `scripts/setup_system.sh` | Runs `apt-get update`, installs OS packages, starts OVS using `ovs-ctl`, and reads OVS state. It is a privileged system/network setup script, not a harmless preparation step. Its `ovs-ctl start || true` can mask the immediate start error; the following `ovs-vsctl show` is the actual script verification. |
| `scripts/setup_ryu_venv.sh --dependencies-only` | Downloads hash-locked Ryu dependencies/source, creates/updates a virtual environment and applies compatibility patches; skips Ryu controller startup. Run as an unprivileged build user. |
| `scripts/setup_ryu_venv.sh` without that flag | Performs the above, then starts a temporary Ryu process with loopback listeners on TCP 6653 and 8080, verifies ownership/connectivity, and terminates it. |
| Starting `intentflow-worker.service` | Starts a privileged worker; health/discovery/execution operations can start Ryu and Mininet. |
| Starting an execution | Creates a live Mininet topology, starts Ryu, programs OVS, measures traffic, and writes persistent evidence. |

Do not run `setup_system.sh`, the full Ryu setup command, either service, or
live execution as part of source review.

For a later host setup, review `scripts/setup_system.sh` first. Do not invoke
that script with `sudo` directly from `/mnt/e/SdnProject`. If the operator
approves its host effects, the package and OVS actions it currently performs
are equivalent to these individually visible commands:

```bash
sudo apt-get update
sudo apt-get install -y \
  iproute2 mininet openvswitch-switch openvswitch-testcontroller \
  iperf3 net-tools iputils-ping ethtool tcpdump
sudo /usr/share/openvswitch/scripts/ovs-ctl start
sudo ovs-vsctl show
systemctl list-unit-files '*openvswitch*'
```

The install changes the WSL Ubuntu package set. `ovs-ctl start` starts OVS
daemons and changes host networking state. Confirm the last command identifies
the OVS service unit required by the worker unit; if the service name differs,
review and edit the unit before installation. This preparation is separate
from running an IntentFlow worker or a Mininet topology.

## Review and build a protected release

Use the reviewed source only as input. Do not run a privileged command with
`/mnt/e/SdnProject` as its working directory or `PYTHONPATH`.

1. Review the exact source on `/mnt/e/SdnProject`. Confirm there are no
   unexpected symlinks, secrets, `.env` files, virtual environments, caches,
   or generated frontend directories to carry into the release.
2. Confirm WSL's Linux home and `/opt` are on the Linux filesystem, not a
   Windows-mounted path:

   ```bash
   findmnt -T "$HOME" -o TARGET,FSTYPE,OPTIONS
   findmnt -T /opt -o TARGET,FSTYPE,OPTIONS
   ```

3. This is a first-install procedure, not an in-place upgrade. Before creating
   anything, verify that the release path and both unit destinations are
   absent, including broken symlinks. If any already exists, stop and preserve
   it; review the existing installation and configuration separately. Do not
   extract over it, replace its units, or use recursive ownership changes on
   it. Use a separate source variable and do not `cd` to, or execute scripts
   from, the `/mnt/e` workspace:

   ```bash
   set -euo pipefail
   SOURCE_DIR=/mnt/e/SdnProject
   RELEASE_DIR=/opt/intentflow-sdn
   WORKER_UNIT=/etc/systemd/system/intentflow-worker.service
   API_UNIT=/etc/systemd/system/intentflow-api.service
   BUILD_USER="$(id -un)"
   BUILD_GROUP="$(id -gn)"
   for path in "$RELEASE_DIR" "$WORKER_UNIT" "$API_UNIT"; do
     if sudo test -e "$path" || sudo test -L "$path"; then
       printf 'Preserving existing path; stop and review: %s\n' "$path" >&2
       exit 1
     fi
   done
   sudo mkdir -m 0750 -- "$RELEASE_DIR"
   sudo chown "$BUILD_USER:$BUILD_GROUP" "$RELEASE_DIR"
   ```

   `mkdir` deliberately fails if the release path appears after the check.
   The extraction and all build commands must use this newly created release
   directory; never use `mkdir -p` or copy into an existing release.

   ```bash
   set -euo pipefail
   tar -C "$SOURCE_DIR" \
     --exclude='.git' --exclude='*/.git' \
     --exclude='.env*' --exclude='*/.env*' \
     --exclude='__pycache__' --exclude='*/__pycache__' \
     --exclude='*.pyc' --exclude='*.pyo' --exclude='*.pyd' \
     --exclude='.pytest_cache' --exclude='*/.pytest_cache' \
     --exclude='.venv*' --exclude='*/.venv*' \
     --exclude='node_modules' --exclude='*/node_modules' \
     --exclude='.next' --exclude='*/.next' \
     --exclude='tsconfig.tsbuildinfo' --exclude='*/tsconfig.tsbuildinfo' \
     --exclude='*.log' --exclude='*/logs/*' \
     -cf - backend testbed tests requirements.txt requirements.in \
       scripts/setup_ryu_venv.sh scripts/ryu-requirements.txt \
       scripts/ryu-requirements.in scripts/ryu-4.34.sha256 \
       scripts/validate_dependency_locks.py scripts/migrate_evidence.py \
       evaluation/results docs/reports deploy/systemd README.md \
     | tar -C "$RELEASE_DIR" -xf -
   ```

   The Windows-mounted source reports permissive `0777`-like modes. Normalize
   only the copied release before validation so unit files do not remain
   executable/world-writable:

   ```bash
   set -euo pipefail
   find "$RELEASE_DIR" -type f -exec chmod 0644 {} +
   find "$RELEASE_DIR/scripts" -maxdepth 1 -type f -name '*.sh' \
     -exec chmod 0755 {} +
   ```

   This copies only selected application/test/runtime inputs. It preserves
   historical source evidence; it does not migrate or remove it. Reject any
   unexpected symlinks in the copied tree before continuing:

   ```bash
   find "$RELEASE_DIR" -type l -printf '%p -> %l\n'
   ```

   The command must produce no project-source symlinks. Virtualenv
   interpreter links created later are expected and must resolve to
   root-owned system interpreters.
4. Inspect the copied source before running it. Run the tests and dependency
   lock validation from the `/opt` copy as the unprivileged build user.
5. Create `.venv-app` with host Mininet visibility and install only the
   application hash lock. Run Ryu setup as the build user with
   `--dependencies-only` to avoid starting a temporary controller during
   build preparation:

   ```bash
   set -euo pipefail
   cd /opt/intentflow-sdn
   python3 -m venv --system-site-packages .venv-app
   .venv-app/bin/python -m pip install --require-hashes \
     --only-binary=:all: -r requirements.txt
   bash scripts/setup_ryu_venv.sh --dependencies-only
   python3 scripts/validate_dependency_locks.py
   .venv-app/bin/python -m compileall -q backend scripts tests
   .venv-app/bin/python -m pytest -q
   ```

6. Inspect the exact staged tree and dependency environments. If any staging,
   build, or test step fails, do not install units or start services. Preserve
   the partial release for diagnosis. To retry, first review the precise
   contents and rename only this failed release to a unique sibling path;
   never delete it or move an unverified path. For example:

   ```bash
   set -euo pipefail
   FAILED_RELEASE="/opt/intentflow-sdn.failed.$(date +%Y%m%d%H%M%S)"
   sudo test ! -e "$FAILED_RELEASE" && sudo test ! -L "$FAILED_RELEASE"
   sudo mv -Tn -- /opt/intentflow-sdn "$FAILED_RELEASE"
   sudo test ! -e /opt/intentflow-sdn && sudo test ! -L /opt/intentflow-sdn
   ```

   Verify the move by inspecting both paths before proceeding. `mv -Tn`
   refuses to replace a destination if one appeared; if the source remains,
   stop and review rather than retrying blindly. Start a fresh first-install
   sequence only after confirming the final release and unit paths are absent.
7. After successful tests and explicit approval, make the release root-owned
   and non-writable by group/others. These recursive commands are scoped only
   to this newly staged release; never apply them to `/var/lib/intentflow`,
   another release, or source evidence:

   ```bash
   sudo chown -R root:root /opt/intentflow-sdn
   sudo chmod -R go-w /opt/intentflow-sdn
   ```

   Verify the final tree is root-owned, has no group/other writable paths,
   and contains no secret-bearing `.env` files, developer venvs, or
   `node_modules`. The worker rejects untrusted release/interpreter/Ryu paths.
   Do not run a worker/API service from a partial or build-user-owned release.

The source workspace on `/mnt/e` is never the systemd `WorkingDirectory`,
`PYTHONPATH`, Python interpreter, or Ryu path.

## Accounts, directories, evidence import, and configuration

The following are proposed commands for a human operator to review and run on
the target only after validating the prerequisites. They were not executed
here.

Create the dedicated service group/account if they do not already exist:

```bash
getent group intentflow-api >/dev/null || sudo groupadd --system intentflow-api
getent passwd intentflow-api >/dev/null || \
  sudo useradd --system --no-create-home --shell /usr/sbin/nologin \
    --gid intentflow-api intentflow-api
API_GID="$(getent group intentflow-api | cut -d: -f3)"
printf 'intentflow-api GID: %s\n' "$API_GID"
```

Create only the persistent parent directory. Let the migration utility create
the `results` and `reports` leaves as `root:intentflow-api 2750`, or create
them explicitly with those exact modes. Do not recursively change any
pre-existing evidence ownership or permissions:

```bash
sudo install -d -o root -g intentflow-api -m 2750 /var/lib/intentflow
sudo install -d -o intentflow-api -g intentflow-api -m 0750 \
  /var/lib/intentflow/topologies
```

Migration copies allowlisted historical execution records. It never removes or
changes the source. It imports generalized execution JSON/Markdown files and
legacy `run_<integer>.json` records; conflicting names exit with status 1 and
must be reviewed manually. A partial failure reports imports already
published; keep them and inspect the destination before retrying.

```bash
sudo python3 /opt/intentflow-sdn/scripts/migrate_evidence.py \
  /mnt/e/SdnProject/evaluation/results \
  /var/lib/intentflow/results --gid "$API_GID"
sudo python3 /opt/intentflow-sdn/scripts/migrate_evidence.py \
  /mnt/e/SdnProject/docs/reports \
  /var/lib/intentflow/reports --gid "$API_GID"
```

The migration source may be on DrvFS; the migration program itself must be
invoked from the root-owned protected release. Existing destination leaves
must already be real directories owned by root, group `intentflow-api`, mode
`2750`; if not, stop for manual review rather than changing them automatically.
Files are copied through directory file descriptors, source symlinks are
skipped, destination symlinks are rejected, and source-file metadata is checked
before and after copying so detected concurrent edits fail closed. This
metadata check is not a filesystem snapshot: stop evidence writers or migrate
from a reviewed, stable source copy. Publication uses exclusive hard links
within the destination directory so existing files are not replaced. The copy
itself works across filesystems; ordinary failed copies clean up their
temporary file and leave the source untouched. A forced termination or power
loss can leave a hidden temporary file or only one member of a JSON/Markdown
pair published. Preserve and inspect such files manually; do not blindly
remove or overwrite them on retry. The writer cleans up its own partial
publication on ordinary exceptions, but the JSON/Markdown pair is not a
single filesystem transaction.

Validate without changing permissions:

```bash
sudo find /var/lib/intentflow -maxdepth 2 -printf '%u:%g %m %p\n' | sort
sudo find /var/lib/intentflow -maxdepth 2 -type f -exec sha256sum {} +
namei -l /var/lib/intentflow/results
namei -l /var/lib/intentflow/reports
```

Create protected service configuration. `/etc/intentflow/worker.env` must
contain a numeric `INTENTFLOW_API_GID` (not a textual placeholder); generate
that value from `getent` above. Keep this file `root:root 0600`. The API
environment must be `root:intentflow-api 0640`; put the high-entropy API token
there, not in the unit or an `ExecStart` argument. Generate the token with
`openssl rand -hex 32`, then enter it using a protected editor. Do not place it
in a `NEXT_PUBLIC_*` setting.

```bash
set -euo pipefail
if sudo test -L /etc/intentflow; then
  echo "Refusing symlinked /etc/intentflow; review it manually." >&2
  exit 1
fi
if ! sudo test -d /etc/intentflow; then
  sudo install -d -o root -g root -m 0755 /etc/intentflow
fi
if sudo test -e /etc/intentflow/worker.env || \
   sudo test -L /etc/intentflow/worker.env; then
  echo "Existing worker.env preserved; inspect it manually." >&2
  exit 1
fi
sudo install -o root -g root -m 0600 \
  /opt/intentflow-sdn/deploy/systemd/intentflow-worker.env.example \
  /etc/intentflow/worker.env
printf 'INTENTFLOW_API_GID=%s\nLLM_PROVIDER=mock\n' "$API_GID" \
  | sudo tee /etc/intentflow/worker.env >/dev/null
sudoedit /etc/intentflow/worker.env
sudo chown root:root /etc/intentflow/worker.env
sudo chmod 0600 /etc/intentflow/worker.env

if sudo test -e /etc/intentflow/api.env || \
   sudo test -L /etc/intentflow/api.env; then
  echo "Existing api.env preserved; inspect it manually." >&2
  exit 1
fi
sudo install -o root -g intentflow-api -m 0640 \
  /opt/intentflow-sdn/deploy/systemd/intentflow-api.env.example \
  /etc/intentflow/api.env
sudoedit /etc/intentflow/api.env
sudo chown root:intentflow-api /etc/intentflow/api.env
sudo chmod 0640 /etc/intentflow/api.env
```

The worker environment file should include:

```dotenv
INTENTFLOW_API_GID=<numeric GID from getent group intentflow-api>
LLM_PROVIDER=mock
```

The API environment file must have a real token of at least 32 bytes and
consistent local origin configuration. The sample token is deliberately
invalid and must be replaced.

## Unit review and installation

The worker unit:

- Runs as `root:intentflow-api`; the worker process is root while its primary
  group matches the socket peer-GID authorization group.
- Requires and follows `openvswitch-switch.service` (verify the name on WSL
  before installation).
- Uses `Group=intentflow-api` so systemd's runtime directory group matches
  the numeric peer-GID read from `/etc/intentflow/worker.env`.
- Reads evidence paths from the same `/var/lib/intentflow` locations as the
  API.
- Stores topology catalog versions in
  `/var/lib/intentflow/topologies/catalog.sqlite3`. This directory is owned by
  the unprivileged API account and is the only persistent data path writable by
  the API; evidence directories remain read-only.
- Uses `ProtectSystem=full`, `ProtectHome=true`, `PrivateTmp=true`,
  `NoNewPrivileges=yes`, a bounded capability set, and only the release as
  `ReadOnlyPaths`. `ProtectSystem=strict` was avoided because it would require
  a target-specific complete writable-path inventory for Mininet/OVS runtime
  directories.

The API unit:

- Runs as `intentflow-api:intentflow-api`.
- Requires and follows the worker.
- Binds only `127.0.0.1:8000`.
- Has no Linux capabilities, `NoNewPrivileges=yes`,
  `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, and
  `PrivateDevices=true`.
- Reads `/opt` and evidence as read-only. It does not write evidence.
- Writes only its topology catalog under
  `/var/lib/intentflow/topologies` via the explicit `ReadWritePaths` exception.

Both units use `KillMode=mixed` so initial SIGTERM reaches the service main
process without simultaneously terminating Ryu/Mininet child processes; the
worker can run its `finally` cleanup while shutting down. `TimeoutStopSec=20min`
allows more than the API's 900-second worker call timeout and time for cleanup.
This is not a hard upper bound on the worker's total Mininet execution time:
if systemd reaches the timeout, it sends SIGKILL and cleanup is not guaranteed.
After such a forced stop, inspect worker logs and host Mininet/OVS state before
restarting. Do not automatically run `mn -c` as a service restart hook because
it can affect unrelated Mininet state on the host.

Before installation, run `systemd-analyze verify` against both unit files on
the target system, verify that `openvswitch-switch.service` exists, and inspect
the final source of both service files and environment files:

```bash
systemd-analyze verify \
  /opt/intentflow-sdn/deploy/systemd/intentflow-worker.service \
  /opt/intentflow-sdn/deploy/systemd/intentflow-api.service
```

Install the reviewed units only after completing the previous checks:

```bash
set -euo pipefail
for unit in \
  /etc/systemd/system/intentflow-worker.service \
  /etc/systemd/system/intentflow-api.service; do
  if sudo test -e "$unit" || sudo test -L "$unit"; then
    printf 'Preserving existing unit; stop and review: %s\n' "$unit" >&2
    exit 1
  fi
done
sudo install -o root -g root -m 0644 \
  /opt/intentflow-sdn/deploy/systemd/intentflow-worker.service \
  /etc/systemd/system/intentflow-worker.service
sudo install -o root -g root -m 0644 \
  /opt/intentflow-sdn/deploy/systemd/intentflow-api.service \
  /etc/systemd/system/intentflow-api.service
sudo systemd-analyze verify \
  /etc/systemd/system/intentflow-worker.service \
  /etc/systemd/system/intentflow-api.service
sudo systemctl daemon-reload
```

Service startup is intentionally a separate approval step. It starts the
privileged worker and can later cause topology discovery or execution to start
Ryu/Mininet. Do not use `enable --now` until the service and target-host
compatibility review has passed.

## Later startup and operational checks

Only after explicit approval and target-host tests:

```bash
sudo systemctl enable --now intentflow-worker.service
sudo systemctl enable --now intentflow-api.service
systemctl status intentflow-worker.service intentflow-api.service
systemctl show intentflow-worker.service -p User -p Group -p MainPID -p ActiveState
systemctl show intentflow-api.service -p User -p Group -p MainPID -p ActiveState
sudo journalctl -u intentflow-worker.service -u intentflow-api.service --since today
sudo find /run/intentflow -maxdepth 1 -printf '%u:%g %m %p\n' | sort
sudo find /var/lib/intentflow -maxdepth 2 -printf '%u:%g %m %p\n' | sort
ss -ltnp '( sport = :6653 or sport = :8080 or sport = :8000 )'
```

The correct API health route is `GET /api/v1/health`, not `/api/health`.
Production health is authenticated; an unauthenticated request should receive
HTTP 401. The systemd API unit explicitly sets
`INTENTFLOW_ENVIRONMENT=production` and `INTENTFLOW_AUTH_DISABLED=false`.
The unit also unsets `INTENTFLOW_AUTH_DISABLED` from the final service
environment. Development-only authentication bypass is not used for protected
deployment.
Use the configured frontend to authenticate and inspect health. Do not put the
API bearer token directly in a `curl -H` command because command arguments can
be visible to other local processes.

Ryu is normally started only during a worker topology or execution request.
After such an approved request, confirm its listeners are loopback-only and
owned by the worker's Ryu child; confirm the API listener remains
`127.0.0.1:8000`. Check worker journal output for socket and evidence failures.

## Stop and rollback

```bash
sudo systemctl stop intentflow-api.service
sudo systemctl stop intentflow-worker.service
sudo systemctl disable intentflow-api.service intentflow-worker.service
systemctl status intentflow-api.service intentflow-worker.service
```

Do not remove `/run/intentflow/worker.lock` while a worker might be alive.
Never delete `/var/lib/intentflow` during rollback. Restore a previously
reviewed `/opt/intentflow-sdn` release only after both services are stopped.
The deployment uses environment overrides rather than evidence-directory
symlinks, so release rollback does not alter persistent evidence paths.

## Remaining deployment prerequisites

- Enable and verify systemd in WSL2.
- Install and verify OS-managed Mininet, OVS, iproute2, ping, iperf3, and
  ethtool prerequisites.
- Confirm actual OVS systemd unit name and target unit health.
- Build and review the release on Linux storage, not under `/mnt/e`.
- Install locked app/Ryu dependencies and verify host Mininet imports.
- Create the dedicated account/group and generate numeric GID configuration.
- Create persistent evidence storage without modifying existing files or
  directories; resolve any migration conflict manually.
- Generate and install the API token securely.
- Verify systemd hardening, WSL2 namespaces/capabilities, Ryu listeners, API
  auth, socket permissions, evidence readability, and topology behavior on the
  target host.

No deployment, service startup, package installation, evidence migration,
Ryu/Mininet execution, or flow deployment has been performed as part of this
documentation and code preparation.
