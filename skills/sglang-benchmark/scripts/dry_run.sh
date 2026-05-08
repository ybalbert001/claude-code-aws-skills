#!/usr/bin/env bash
# Validate spec.yaml.server.base_flags by starting the SGLang server once.
#
# Flow:
#   1. Build serve_cmd from spec.yaml via generate_plan.py --stage expand (tier=1 view)
#      (we reuse the same flag→CLI logic for consistency)
#   2. ssh_run_bg serve_cmd (nohup, remote log /tmp/sglang-dryrun.log)
#   3. wait_healthy until ready or benchmark.ready_check_timeout_sec
#   4. shutdown_server; verify port freed
#   5. On failure: tail log, exit 1
#
# Usage:
#   dry_run.sh --spec spec.yaml --ssh-host HOST --ssh-key KEY [--ssh-user ubuntu]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ssh_utils.sh
source "$SCRIPT_DIR/ssh_utils.sh"

SPEC=""
SSH_HOST="${SSH_HOST:-}"
SSH_KEY="${SSH_KEY:-}"
SSH_USER="${SSH_USER:-ubuntu}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec) SPEC="$2"; shift 2 ;;
    --ssh-host) SSH_HOST="$2"; shift 2 ;;
    --ssh-key) SSH_KEY="$2"; shift 2 ;;
    --ssh-user) SSH_USER="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

for v in SPEC SSH_HOST SSH_KEY; do
  if [[ -z "${!v}" ]]; then
    echo "missing required arg: --${v,,}" >&2
    exit 2
  fi
done
export SSH_HOST SSH_KEY SSH_USER

_read() { python3 "$SCRIPT_DIR/_spec_read.py" "$SPEC" "$1" "${2:-}"; }

PORT=$(_read server.port 30000)
TIMEOUT=$(_read benchmark.ready_check_timeout_sec 900)
CLEANUP_CMD=$(_read server.cleanup_cmd "")

# Build serve_cmd: prefer raw server.serve_cmd if set; else assemble from base_flags.
SERVE_CMD=$(PYTHONPATH="$SCRIPT_DIR" python3 - "$SPEC" <<'PY'
import sys, yaml
from pathlib import Path
import generate_plan as gp

spec = yaml.safe_load(Path(sys.argv[1]).read_text())
server = spec["server"]
raw = server.get("serve_cmd")
if raw:
    print(raw)
else:
    cmd = gp._build_serve_cmd(
        server_host=server.get("host", "127.0.0.1"),
        server_port=int(server.get("port", 30000)),
        env=server.get("env"),
        flags=server["base_flags"],
    )
    print(cmd)
PY
)

REMOTE_LOG="/tmp/sglang-dryrun-$$.log"
echo "[dry_run] starting server on $SSH_HOST (log: $REMOTE_LOG)"
echo "[dry_run] serve_cmd: $SERVE_CMD"

PID=$(ssh_run_bg "$SERVE_CMD" "$REMOTE_LOG")
echo "[dry_run] remote pid: $PID"

cleanup_done=0
cleanup() {
  (( cleanup_done )) && return
  cleanup_done=1
  if [[ -n "$CLEANUP_CMD" ]]; then
    echo "[dry_run] shutting down via cleanup_cmd (port=$PORT)..."
    shutdown_with_cmd "$CLEANUP_CMD" "$PORT" || echo "[dry_run] shutdown reported issue" >&2
  else
    echo "[dry_run] shutting down (pid=$PID, port=$PORT)..."
    shutdown_server "$PID" "$PORT" || echo "[dry_run] shutdown reported issue" >&2
  fi
}
trap cleanup EXIT

echo "[dry_run] waiting for /health on port $PORT (timeout ${TIMEOUT}s)..."
if wait_healthy "$PORT" "$TIMEOUT" 5; then
  echo "[dry_run] OK: server became healthy"
  STATUS=0
else
  echo "[dry_run] FAILED: server did not become healthy. Last 80 lines of remote log:" >&2
  tail_remote_log "$REMOTE_LOG" 80 >&2
  STATUS=1
fi

exit "$STATUS"
