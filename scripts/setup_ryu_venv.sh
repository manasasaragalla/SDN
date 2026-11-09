#!/usr/bin/env bash
# Creates an isolated virtual environment for Ryu 4.34.
# Includes compatibility patches for modern Python 3.12 and setuptools.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${INTENTFLOW_RYU_VENV_DIR:-$PROJECT_ROOT/.venv-ryu}"
RYU_VERSION="4.34"
RYU_SDIST_URL="https://files.pythonhosted.org/packages/25/30/1c1972b3f9bf52de32d2fdf7c5206ff7099e739bf69b6004f4a71bcbde18/ryu-4.34.tar.gz"
WORK_DIR=""
RYU_PID=""
DEPENDENCIES_ONLY=0

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--dependencies-only" ]; }; then
    echo "Usage: $0 [--dependencies-only]" >&2
    exit 2
fi
if [ "$#" -eq 1 ]; then
    DEPENDENCIES_ONLY=1
fi

if [ "$EUID" -eq 0 ]; then
    echo "ERROR: Run this setup as an unprivileged build user, not root." >&2
    exit 1
fi

for command_name in curl python3 sha256sum tar; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "ERROR: Required command is unavailable: $command_name" >&2
        exit 1
    fi
done

python3 "$PROJECT_ROOT/scripts/validate_dependency_locks.py"
WORK_DIR="$(mktemp -d)"

cleanup_ryu() {
    if [ -n "${RYU_PID:-}" ]; then
        if kill -0 "$RYU_PID" 2>/dev/null; then
            kill -TERM "$RYU_PID" 2>/dev/null || true
            for _ in {1..50}; do
                if ! kill -0 "$RYU_PID" 2>/dev/null; then
                    break
                fi
                sleep 0.1
            done
            if kill -0 "$RYU_PID" 2>/dev/null; then
                kill -KILL "$RYU_PID" 2>/dev/null || true
            fi
        fi
        wait "$RYU_PID" 2>/dev/null || true
        RYU_PID=""
    fi
}

trap 'cleanup_ryu; rm -rf "$WORK_DIR"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "==> Creating venv at $VENV_DIR"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "==> Installing hash-locked Ryu dependencies"

python -m pip install --force-reinstall --require-hashes --no-build-isolation \
    -r "$PROJECT_ROOT/scripts/ryu-requirements.txt"

echo "==> Downloading Ryu $RYU_VERSION source with SHA-256 verification"

read -r SDIST_SHA256 SDIST_FILENAME < "$PROJECT_ROOT/scripts/ryu-4.34.sha256"
if [ "$SDIST_FILENAME" != "ryu-$RYU_VERSION.tar.gz" ]; then
    echo "ERROR: Ryu source checksum filename does not match version $RYU_VERSION" >&2
    exit 1
fi
curl --proto '=https' --tlsv1.2 -fsSL \
    -o "$WORK_DIR/$SDIST_FILENAME" "$RYU_SDIST_URL"
printf '%s  %s\n' "$SDIST_SHA256" "$WORK_DIR/$SDIST_FILENAME" \
    | sha256sum --check -
tar xzf "$WORK_DIR/$SDIST_FILENAME" -C "$WORK_DIR"

SRC_DIR="$WORK_DIR/ryu-$RYU_VERSION"

echo "==> Patching Ryu hooks.py"

python3 - "$SRC_DIR/ryu/hooks.py" <<'PY'
import sys

path = sys.argv[1]

with open(path) as f:
    content = f.read()

old = """def save_orig():
    \"\"\"Save original easy_install.get_script_args.
    This is necessary because pbr's setup_hook is sometimes called
    before ours.\"\"\"
    _main_module()._orig_get_script_args = easy_install.get_script_args"""

new = """def save_orig():
    \"\"\"Save original easy_install.get_script_args when available.\"\"\"
    _main_module()._orig_get_script_args = getattr(
        easy_install, 'get_script_args', None
    )"""

if old in content:
    content = content.replace(old, new)
elif new not in content:
    raise SystemExit(
        "ERROR: Unexpected Ryu hooks.py; expected compatibility pattern is missing"
    )

old2 = """    packaging.override_get_script_args = my_get_script_args
    easy_install.get_script_args = my_get_script_args"""

new2 = """    if _main_module()._orig_get_script_args is not None:
        packaging.override_get_script_args = my_get_script_args
        easy_install.get_script_args = my_get_script_args"""

if old2 in content:
    content = content.replace(old2, new2)
elif new2 not in content:
    raise SystemExit(
        "ERROR: Unexpected Ryu hooks.py; setup hook pattern is missing"
    )

with open(path, "w") as f:
    f.write(content)

print("Ryu hooks.py patched")
PY

echo "==> Fixing Python 2 print statements"

sed -i \
  -e 's/print "BFD Session=%d is DOWN!" % ev.session.my_discr/print("BFD Session=%d is DOWN!" % ev.session.my_discr)/' \
  -e 's/print "BFD Session=%d is UP!" % ev.session.my_discr/print("BFD Session=%d is UP!" % ev.session.my_discr)/' \
  "$SRC_DIR/ryu/lib/bfdlib.py"

if grep -qE 'print "BFD Session=' "$SRC_DIR/ryu/lib/bfdlib.py"; then
    echo "ERROR: Python 2 print syntax remains in Ryu bfdlib.py" >&2
    exit 1
fi

echo "==> Compiling Ryu source"

python3 -m compileall -q "$SRC_DIR/ryu"

echo "==> Patching Ryu package discovery"

python - "$SRC_DIR/setup.py" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()

pattern = r"setuptools\.setup\s*\(\s*name\s*=\s*['\"]ryu['\"]"

if not re.search(pattern, text):
    raise SystemExit("ERROR: Could not locate setuptools.setup(name='ryu')")

replacement = (
    "setuptools.setup("
    "name='ryu', "
    "packages=setuptools.find_packages(include=['ryu', 'ryu.*'])"
)

text = re.sub(pattern, replacement, text, count=1)

path.write_text(text)

print("Ryu package discovery patched")
PY

echo "==> Installing patched Ryu"

python -m pip install --no-deps --no-build-isolation "$SRC_DIR"

SITE_PACKAGES="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"

echo "==> Creating Oslo compatibility shim"

mkdir -p "$SITE_PACKAGES/oslo/config"

cat > "$SITE_PACKAGES/oslo/__init__.py" <<'EOF'
# Legacy Oslo namespace compatibility for Ryu 4.x.
EOF

cat > "$SITE_PACKAGES/oslo/config/__init__.py" <<'EOF'
from oslo_config import cfg
EOF

echo "==> Patching Ryu WSGI compatibility"

python3 - "$SITE_PACKAGES/ryu/app/wsgi.py" <<'PY'
import sys

path = sys.argv[1]

with open(path) as f:
    content = f.read()

old = """class _AlreadyHandledResponse(Response):
    # XXX: Eventlet API should not be used directly.
    from eventlet.wsgi import ALREADY_HANDLED
    _ALREADY_HANDLED = ALREADY_HANDLED
"""

new = """class _AlreadyHandledResponse(Response):
    # XXX: Eventlet API should not be used directly.
    try:
        from eventlet.wsgi import ALREADY_HANDLED
        _ALREADY_HANDLED = ALREADY_HANDLED
    except ImportError:
        _ALREADY_HANDLED = object()
"""

if old in content:
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)

    print("Ryu WSGI compatibility patched")
elif new not in content:
    raise SystemExit(
        "ERROR: Unexpected Ryu WSGI source; compatibility pattern is missing"
    )
PY

echo "==> Creating ryu-manager executable"

cat > "$VENV_DIR/bin/ryu-manager" <<EOF
#!/bin/sh
SCRIPT_DIR=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)
exec "\$SCRIPT_DIR/python" -c 'from ryu.cmd.manager import main; main()' "\$@"

EOF

chmod +x "$VENV_DIR/bin/ryu-manager"

echo "==> Verifying Ryu installation"

"$VENV_DIR/bin/python" -c "
import ryu
from oslo.config import cfg
import ryu.app.wsgi
import ryu.app.ofctl_rest
print('Ryu import: OK')
"

if [ "$DEPENDENCIES_ONLY" -eq 1 ]; then
    echo "==> Dependency and compatibility-patch installation verified; controller startup skipped"
    exit 0
fi

"$VENV_DIR/bin/ryu-manager" --version

echo "==> Starting Ryu REST controller verification"

"$VENV_DIR/bin/ryu-manager" \
    ryu.app.ofctl_rest \
    --ofp-listen-host 127.0.0.1 \
    --ofp-tcp-listen-port 6653 \
    --wsapi-host 127.0.0.1 \
    --wsapi-port 8080 \
    < /dev/null > "$WORK_DIR/ryu_verify.log" 2>&1 &

RYU_PID=$!

sleep 3

if ! kill -0 "$RYU_PID" 2>/dev/null; then
    echo "ERROR: Ryu controller exited unexpectedly"
    cat "$WORK_DIR/ryu_verify.log"
    exit 1
fi

echo "==> Verifying process-owned loopback listeners and checking ports"

"$VENV_DIR/bin/python" - "$RYU_PID" 6653 8080 <<'PY'
import os
from pathlib import Path
import socket
import sys

pid = int(sys.argv[1])
ports = {int(value) for value in sys.argv[2:]}
owned_inodes = set()
for descriptor in Path(f"/proc/{pid}/fd").iterdir():
    try:
        target = os.readlink(descriptor)
    except OSError:
        continue
    if target.startswith("socket:[") and target.endswith("]"):
        owned_inodes.add(target[8:-1])

entries = []
for family in ("tcp", "tcp6"):
    table = Path(f"/proc/{pid}/net/{family}")
    try:
        rows = table.read_text(encoding="ascii").splitlines()[1:]
    except OSError as exc:
        raise SystemExit(f"Cannot inspect {family} listener table: {exc}")
    for row in rows:
        fields = row.split()
        if len(fields) < 10 or fields[3] != "0A":
            continue
        local_address, local_port = fields[1].split(":")
        port = int(local_port, 16)
        if port not in ports:
            continue
        if family != "tcp" or local_address.upper() != "0100007F":
            raise SystemExit(f"Unexpected non-loopback listener: {family} {row}")
        if fields[9] not in owned_inodes:
            raise SystemExit(f"Listener is not owned by Ryu PID {pid}: {row}")
        entries.append(port)

if len(entries) != len(ports) or set(entries) != ports:
    raise SystemExit(f"Expected one process-owned listener on each port; got {entries}")

failed = []

for port in sorted(ports):
    sock = socket.socket()
    sock.settimeout(3)

    try:
        sock.connect(("127.0.0.1", port))
        print(f"OK: Port {port} is accepting connections")
    except OSError as exc:
        print(f"ERROR: Port {port} is unavailable: {exc}")
        failed.append(port)
    finally:
        sock.close()

if failed:
    sys.exit(1)
PY

echo "==> Stopping verification controller"

cleanup_ryu
RYU_PID=""

echo "==> Ryu setup completed successfully"
echo "Ryu manager: $VENV_DIR/bin/ryu-manager"