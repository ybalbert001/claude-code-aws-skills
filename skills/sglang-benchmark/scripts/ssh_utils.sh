#!/usr/bin/env bash
# Shared SSH helpers. Sourced by dry_run.sh / run_experiment.sh.
#
# Required env vars (set by caller before sourcing or before calling functions):
#   SSH_HOST   - remote host / IP
#   SSH_KEY    - path to SSH private key
#   SSH_USER   - remote username (default: ubuntu)
#
# All functions assume StrictHostKeyChecking=no for convenience in benchmark context.

: "${SSH_USER:=ubuntu}"

_ssh_opts=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o LogLevel=ERROR
  -o ServerAliveInterval=30
)

# ssh_run "<cmd>"  -> runs cmd on remote, stdout/stderr inherited, returns cmd's exit code
ssh_run() {
  local cmd="$1"
  ssh "${_ssh_opts[@]}" -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" -- "$cmd"
}

# ssh_run_capture "<cmd>"  -> prints stdout, returns cmd's exit code
ssh_run_capture() {
  local cmd="$1"
  ssh "${_ssh_opts[@]}" -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" -- "$cmd"
}

# ssh_run_bg "<cmd>" "<log_path>"
#   Launches cmd via nohup on remote, redirecting stdout+stderr to log_path.
#   Prints the remote PID to stdout. Returns 0 if we got a PID.
ssh_run_bg() {
  local cmd="$1"
  local log="$2"
  # Wrap so we can echo $! reliably from the remote shell.
  local wrapped="nohup bash -c '$cmd' > $log 2>&1 < /dev/null & echo \$!"
  local pid
  pid=$(ssh "${_ssh_opts[@]}" -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" -- "$wrapped" | tr -d '[:space:]')
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
    echo "ssh_run_bg: failed to capture remote pid (got: '$pid')" >&2
    return 1
  fi
  echo "$pid"
}

# wait_healthy "<port>" "<timeout_sec>" [interval_sec=5]
#   Polls /health via SSH (curl on the remote host against 127.0.0.1:port).
#   Avoids requiring the inference port to be publicly reachable.
#   Returns 0 when /health returns 200, 1 on timeout.
wait_healthy() {
  local port="$1"
  local timeout="$2"
  local interval="${3:-5}"
  local deadline=$(( $(date +%s) + timeout ))

  while (( $(date +%s) < deadline )); do
    if ssh_run "curl -fsS -m 3 http://127.0.0.1:$port/health > /dev/null 2>&1"; then
      return 0
    fi
    sleep "$interval"
  done

  echo "wait_healthy: timeout after ${timeout}s waiting for http://127.0.0.1:$port/health (via SSH)" >&2
  return 1
}

# shutdown_server "<pid>" "<port>"
#   Kills the remote pid, waits briefly, then force-kills anything still bound to port.
shutdown_server() {
  local pid="$1"
  local port="$2"

  # Graceful kill first.
  ssh_run "kill $pid 2>/dev/null || true"
  sleep 3
  # Force kill process tree + anything on the port.
  ssh_run "kill -9 $pid 2>/dev/null || true; \
           pids=\$(lsof -ti:$port 2>/dev/null || true); \
           if [ -n \"\$pids\" ]; then kill -9 \$pids 2>/dev/null || true; fi"
  # Verify port freed.
  sleep 2
  if ssh_run_capture "lsof -ti:$port 2>/dev/null" | grep -q .; then
    echo "shutdown_server: port $port still in use after kill" >&2
    return 1
  fi
  return 0
}

# tail_remote_log "<log_path>" [lines=100]
tail_remote_log() {
  local log="$1"
  local lines="${2:-100}"
  ssh_run_capture "tail -n $lines $log 2>/dev/null || echo '(log not found: $log)'"
}

# scp_from_remote "<remote_path>" "<local_path>"
scp_from_remote() {
  local remote="$1"
  local local_p="$2"
  scp "${_ssh_opts[@]}" -i "$SSH_KEY" "$SSH_USER@$SSH_HOST:$remote" "$local_p"
}
