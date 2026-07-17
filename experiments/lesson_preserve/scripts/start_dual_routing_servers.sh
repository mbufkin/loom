#!/usr/bin/env bash
# Dual local servers for LP routing cascade (GB10 / unified memory).
#
# Pass2  Nano 9B  → http://127.0.0.1:8081
# Pass3  Nano 30B → http://127.0.0.1:8080
#
# WHY BOTH FIT: the current 30B server uses -c 524288, which balloons KV cache.
# For routing we only need ~16–32k context (Dallas docs top out ~13k tokens).
# Shrink 30B ctx, add a small 9B GGUF on a second port — both stay resident.
#
# Usage:
#   bash experiments/lesson_preserve/scripts/start_dual_routing_servers.sh
#   # optional: STOP_30B=1 to kill the existing :8080 process first

set -euo pipefail

LLAMA_BIN="${LLAMA_BIN:-$HOME/llama.cpp/build-cuda/bin/llama-server}"
MODELS="${MODELS:-$HOME/llama.cpp/models}"
GGUF_9B="${GGUF_9B:-$MODELS/nvidia_NVIDIA-Nemotron-Nano-9B-v2-Q4_K_M.gguf}"
GGUF_30B="${GGUF_30B:-$MODELS/nemotron3-nano-30b.gguf}"
PORT_9B="${PORT_9B:-8081}"
PORT_30B="${PORT_30B:-8080}"
CTX_9B="${CTX_9B:-16384}"
CTX_30B="${CTX_30B:-32768}"   # escalate still gets full Dallas docs
LOG_DIR="${LOG_DIR:-/tmp/loom-routing-servers}"
mkdir -p "$LOG_DIR"

if [[ ! -x "$LLAMA_BIN" ]]; then
  echo "Missing llama-server at $LLAMA_BIN" >&2
  exit 1
fi
if [[ ! -f "$GGUF_9B" ]]; then
  echo "Missing 9B GGUF: $GGUF_9B" >&2
  echo "Download with:" >&2
  echo "  hf download bartowski/nvidia_NVIDIA-Nemotron-Nano-9B-v2-GGUF nvidia_NVIDIA-Nemotron-Nano-9B-v2-Q4_K_M.gguf --local-dir $MODELS" >&2
  exit 1
fi
if [[ "${KEEP_30B:-0}" != "1" && ! -f "$GGUF_30B" ]]; then
  echo "Missing 30B GGUF: $GGUF_30B" >&2
  echo "Re-download Unsloth Q8 (or your preferred quant), e.g.:" >&2
  echo "  hf download unsloth/Nemotron-3-Nano-30B-A3B-GGUF --include '*Q8*' --local-dir /tmp/n30 && ln -sf ..." >&2
  exit 1
fi

stop_port() {
  local port="$1"
  local pids
  pids=$(ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print}' | grep -oP 'pid=\K[0-9]+' || true)
  if [[ -n "${pids:-}" ]]; then
    echo "Stopping PIDs on :$port → $pids"
    kill $pids 2>/dev/null || true
    sleep 2
  fi
}

# Always (re)start 9B on 8081
stop_port "$PORT_9B"

# Restart 30B with routing-sized context unless KEEP_30B=1
if [[ "${KEEP_30B:-0}" != "1" ]]; then
  stop_port "$PORT_30B"
  echo "Starting 30B on :$PORT_30B  ctx=$CTX_30B …"
  nohup "$LLAMA_BIN" \
    -m "$GGUF_30B" \
    --host 127.0.0.1 --port "$PORT_30B" \
    --gpu-layers all \
    -c "$CTX_30B" \
    --jinja \
    --no-mmap \
    -fa on \
    --cache-type-k q8_0 --cache-type-v q8_0 \
    -b 512 -ub 512 \
    --reasoning off \
    >"$LOG_DIR/30b.log" 2>&1 &
  echo $! >"$LOG_DIR/30b.pid"
else
  echo "KEEP_30B=1 — leaving :$PORT_30B as-is (may OOM if ctx is still 524k)"
fi

echo "Starting 9B on :$PORT_9B  ctx=$CTX_9B …"
nohup "$LLAMA_BIN" \
  -m "$GGUF_9B" \
  --host 127.0.0.1 --port "$PORT_9B" \
  --gpu-layers all \
  -c "$CTX_9B" \
  --jinja \
  --no-mmap \
  -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  -b 256 -ub 256 \
  --reasoning off \
  >"$LOG_DIR/9b.log" 2>&1 &
echo $! >"$LOG_DIR/9b.pid"

echo "Waiting for /health …"
for i in $(seq 1 90); do
  ok9=$(curl -sf "http://127.0.0.1:$PORT_9B/health" >/dev/null && echo 1 || echo 0)
  ok30=$(curl -sf "http://127.0.0.1:$PORT_30B/health" >/dev/null && echo 1 || echo 0)
  if [[ "$ok9" == 1 && "$ok30" == 1 ]]; then
    echo "Both up:"
    echo "  pass2 Nano 9B  → http://127.0.0.1:$PORT_9B/v1"
    echo "  pass3 Nano 30B → http://127.0.0.1:$PORT_30B/v1"
    exit 0
  fi
  sleep 2
done

echo "Timed out waiting for health. Logs:" >&2
tail -n 40 "$LOG_DIR/9b.log" >&2 || true
tail -n 40 "$LOG_DIR/30b.log" >&2 || true
exit 1
