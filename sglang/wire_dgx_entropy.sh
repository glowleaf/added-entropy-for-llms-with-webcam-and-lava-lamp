#!/usr/bin/env bash
# DGX: make the Qwen3.8-27B SGLang server draw its sampling entropy from the
# shared physical pool.
#
#  1. pull the pool from the Ubuntu box on a timer (LAN, read-only, no creds)
#  2. build a derivative image whose Python seeds its RNGs from that pool
#  3. point qwen27b.service at that image via the recipe's own IMAGE override
#
# Nothing here starts the model - it is wired for when it is loaded.
set -euo pipefail

BUILD=/home/machinegeorge/dgx-entropy-build
POOL=/home/machinegeorge/models/dgx_entropy_pool.bin
UBUNTU=http://192.168.1.7:8079/dgx_entropy_pool.bin
BASE=lmsysorg/sglang:qwen38-27b
IMAGE=dgx-sglang-entropy:local

echo "=== 1. pull the pool ==="
sudo tee /etc/systemd/system/dgx-entropy-pull.service >/dev/null <<EOF
[Unit]
Description=Pull the shared physical-entropy pool from the Ubuntu box
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=machinegeorge
ExecStart=/usr/bin/curl -fsS --max-time 10 -o $POOL.tmp $UBUNTU
ExecStart=/bin/mv -f $POOL.tmp $POOL
ExecStart=/bin/chmod 644 $POOL
Nice=15
TimeoutStartSec=30
EOF

sudo tee /etc/systemd/system/dgx-entropy-pull.timer >/dev/null <<'EOF'
[Unit]
Description=Refresh the DGX entropy pool at boot and every 60s

[Timer]
OnBootSec=20s
OnUnitActiveSec=60s
AccuracySec=5s
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now dgx-entropy-pull.timer
sudo systemctl start dgx-entropy-pull.service
echo "  pool on the DGX:"
ls -la "$POOL"
xxd "$POOL" | head -2

echo
echo "=== 2. build the derivative image ==="
install -d -m 755 "$BUILD"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
install -m 644 "$HERE/sglang/dgx_entropy_sitecustomize.py" "$BUILD/dgx_entropy_sitecustomize.py"
cat > "$BUILD/Dockerfile" <<EOF
FROM $BASE
# Keep any pre-existing sitecustomize out of the way rather than clobbering it.
RUN if [ -f /usr/local/lib/python3.12/dist-packages/sitecustomize.py ]; then \\
      mv /usr/local/lib/python3.12/dist-packages/sitecustomize.py \\
         /usr/local/lib/python3.12/dist-packages/_sitecustomize_pre_dgx_entropy.py; \\
    fi
COPY dgx_entropy_sitecustomize.py /usr/local/lib/python3.12/dist-packages/sitecustomize.py
EOF
docker build -t "$IMAGE" "$BUILD"
echo "  built:"
docker images "$IMAGE"

echo
echo "=== 3. point the 27B service at it ==="
sudo install -d -m 755 /etc/systemd/system/qwen27b.service.d
sudo tee /etc/systemd/system/qwen27b.service.d/entropy.conf >/dev/null <<EOF
# Run the entropy-seeded derivative image instead of the stock one.
# Roll back by deleting this file and running: systemctl daemon-reload
[Service]
Environment=IMAGE=$IMAGE
EOF
sudo systemctl daemon-reload
systemctl show -p Environment qwen27b.service | tr ' ' '\n' | grep -i image || true

echo
echo "=== 4. prove it inside the real image ==="
echo "--- a) normal startup still works ---"
docker run --rm -v /home/machinegeorge/models:/root/models "$IMAGE" python3 -c "print('startup ok')" 2>&1 | grep -E "startup ok|dgx-entropy" || true

echo "--- b) what did it derive, and from what ---"
docker run --rm -v /home/machinegeorge/models:/root/models "$IMAGE" python3 -c "
import torch
print('torch global seed:', torch.initial_seed())
print('first draws:', [int(x) for x in (torch.rand(4)*1000)])
" 2>&1 | grep -vE "^==|CUDA|Copyright|governed|https://|A copy|By pulling|^$"

echo "--- c) the pool it read ---"
cat /tmp/dgx_entropy_seed_LAST 2>/dev/null || true
