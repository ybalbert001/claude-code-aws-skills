#!/usr/bin/env bash
# Run a single benchmark experiment. Invoked by subagent in Phase 3.
#
# Flow:
#   1. jq to locate row with --experiment-id in plan.json (JSON array)
#   2. If --resume and output_file already exists non-empty: skip (exit 0)
#   3. ssh_run_bg serve_cmd (log: /tmp/sglang-server-exp-N.log)
#   4. wait_healthy (timeout from spec benchmark.ready_check_timeout_sec, default 900)
#   5. ssh_run bench_cmd; bench writes remote jsonl (per plan row's bench_cmd --output-file)
#   6. scp remote bench jsonl back, wrap with meta into local output_file
#   7. shutdown_server; verify port freed
#
# Usage:
#   run_experiment.sh --plan plan.json --experiment-id N \
#       --ssh-host HOST --ssh-key KEY [--ssh-user ubuntu] \
#       [--spec spec.yaml] [--results-dir results] [--resume]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ssh_utils.sh
source "$SCRIPT_DIR/ssh_utils.sh"

PLAN=""
EXP_ID=""
SPEC=""
RESULTS_DIR="results"
RESUME=0
SSH_HOST="${SSH_HOST:-}"
SSH_KEY="${SSH_KEY:-}"
SSH_USER="${SSH_USER:-ubuntu}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan) PLAN="$2"; shift 2 ;;
    --experiment-id) EXP_ID="$2"; shift 2 ;;
    --spec) SPEC="$2"; shift 2 ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    --ssh-host) SSH_HOST="$2"; shift 2 ;;
    --ssh-key) SSH_KEY="$2"; shift 2 ;;
    --ssh-user) SSH_USER="$2"; shift 2 ;;
    --resume) RESUME=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

for v in PLAN EXP_ID SSH_HOST SSH_KEY; do
  if [[ -z "${!v}" ]]; then
    echo "missing required arg: --${v,,}" >&2
    exit 2
  fi
done
export SSH_HOST SSH_KEY SSH_USER

# Extract the plan row for this experiment_id.
ROW=$(jq -c --argjson id "$EXP_ID" '.experiment_list[] | select(.experiment_id == $id)' "$PLAN" | head -1)
if [[ -z "$ROW" ]]; then
  echo "experiment_id=$EXP_ID not found in $PLAN" >&2
  exit 1
fi

SERVE_CMD=$(jq -r '.serve_cmd' <<<"$ROW")
BENCH_CMD=$(jq -r '.bench_cmd' <<<"$ROW")
OUTPUT_FILE_REL=$(jq -r '.output_file' <<<"$ROW")
OUTPUT_FILE="$RESULTS_DIR/$(basename "$OUTPUT_FILE_REL")"
# Remote bench output path is encoded in bench_cmd via --output-file.
REMOTE_BENCH_OUT=$(sed -n 's/.*--output-file \([^ ]*\).*/\1/p' <<<"$BENCH_CMD")

mkdir -p "$RESULTS_DIR"

# Resume check.
if (( RESUME )) && [[ -s "$OUTPUT_FILE" ]]; then
  echo "[exp $EXP_ID] resume: $OUTPUT_FILE exists, skipping"
  exit 0
fi

# Determine port and timeout.
PORT=$(awk -v cmd="$SERVE_CMD" 'BEGIN{
  n=split(cmd, a, " "); for (i=1;i<=n;i++) if (a[i]=="--port") { print a[i+1]; exit }
}')
PORT=${PORT:-30000}

if [[ -n "$SPEC" ]]; then
  TIMEOUT=$(python3 "$SCRIPT_DIR/_spec_read.py" "$SPEC" benchmark.ready_check_timeout_sec 900)
else
  TIMEOUT=900
fi

REMOTE_SERVER_LOG="/tmp/sglang-server-exp-${EXP_ID}.log"

echo "[exp $EXP_ID] serve_cmd: $SERVE_CMD"
echo "[exp $EXP_ID] bench_cmd: $BENCH_CMD"
echo "[exp $EXP_ID] starting server (log: $REMOTE_SERVER_LOG, port: $PORT)"

PID=$(ssh_run_bg "$SERVE_CMD" "$REMOTE_SERVER_LOG")
echo "[exp $EXP_ID] server pid: $PID"

cleanup_done=0
EXIT_STATUS=1
cleanup() {
  (( cleanup_done )) && return
  cleanup_done=1
  echo "[exp $EXP_ID] shutting down (pid=$PID, port=$PORT)"
  shutdown_server "$PID" "$PORT" || echo "[exp $EXP_ID] shutdown issue" >&2
}
trap cleanup EXIT

echo "[exp $EXP_ID] waiting for health on port $PORT (timeout ${TIMEOUT}s)..."
if ! wait_healthy "$PORT" "$TIMEOUT" 5; then
  echo "[exp $EXP_ID] server did not become healthy. Tail of log:" >&2
  tail_remote_log "$REMOTE_SERVER_LOG" 80 >&2
  exit 1
fi
echo "[exp $EXP_ID] server ready, running bench..."

# bench_serving appends to --output-file; clear any stale file first.
if [[ -n "$REMOTE_BENCH_OUT" ]]; then
  ssh_run "rm -f $REMOTE_BENCH_OUT" || true
fi

# Run bench_cmd. bench_serving handles its own output to --output-file.
BENCH_STDOUT_TMP=$(mktemp)
if ! ssh_run "$BENCH_CMD" > "$BENCH_STDOUT_TMP" 2>&1; then
  echo "[exp $EXP_ID] bench_cmd failed. Tail of server log:" >&2
  tail_remote_log "$REMOTE_SERVER_LOG" 80 >&2
  echo "--- bench stdout/stderr: ---" >&2
  tail -n 80 "$BENCH_STDOUT_TMP" >&2
  rm -f "$BENCH_STDOUT_TMP"
  exit 1
fi

# Pull remote bench output back.
LOCAL_BENCH_RAW="$RESULTS_DIR/exp_${EXP_ID}.raw.jsonl"
if [[ -z "$REMOTE_BENCH_OUT" ]]; then
  echo "[exp $EXP_ID] bench_cmd has no --output-file; capturing stdout as raw" >&2
  cp "$BENCH_STDOUT_TMP" "$LOCAL_BENCH_RAW"
else
  scp_from_remote "$REMOTE_BENCH_OUT" "$LOCAL_BENCH_RAW"
fi

# Wrap raw + meta into final OUTPUT_FILE.
python3 - "$ROW" "$LOCAL_BENCH_RAW" "$OUTPUT_FILE" "$BENCH_STDOUT_TMP" <<'PY'
import json, sys, pathlib

row = json.loads(sys.argv[1])
raw_path = pathlib.Path(sys.argv[2])
out_path = pathlib.Path(sys.argv[3])
stdout_path = pathlib.Path(sys.argv[4])

raw_lines = [l for l in raw_path.read_text().splitlines() if l.strip()]
raw = []
for line in raw_lines:
    try:
        raw.append(json.loads(line))
    except json.JSONDecodeError:
        # Not JSON lines (e.g., captured stdout); store verbatim.
        raw = {"stdout": raw_path.read_text()}
        break

bundle = {
    "experiment_id": row["experiment_id"],
    "meta": row["meta"],
    "serve_cmd": row["serve_cmd"],
    "bench_cmd": row["bench_cmd"],
    "raw": raw,
    "bench_stdout_tail": stdout_path.read_text()[-4000:],
}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
print(f"[exp {row['experiment_id']}] wrote {out_path}")
PY

rm -f "$BENCH_STDOUT_TMP"
EXIT_STATUS=0
exit 0
