#!/usr/bin/env bash
# Ubuntu box: publish the entropy pool over the LAN so the DGX can consume it.
# Read-only 32-byte file, no credentials, served only to the local network.
set -eu

SERVE=/home/hermes/olv/entropy_serve
POOL=/home/hermes/olv/libby_webcam_entropy.bin
PORT=8079

echo "=== 1. serve directory ==="
install -d -m 755 "$SERVE"

echo "=== 2. publish the pool on every refresh ==="
sudo tee /etc/systemd/system/libby-entropy.service >/dev/null <<'EOF'
[Unit]
Description=Libby entropy pool - run every physical source, rebuild the pool, publish it to the LAN
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=hermes
Environment=HOME=/home/hermes
ExecStart=/bin/bash -c '/usr/bin/python3 /home/hermes/olv/libby_entropy.py refresh && /bin/cp -f /home/hermes/olv/libby_webcam_entropy.bin /home/hermes/olv/entropy_serve/dgx_entropy_pool.bin && /bin/chmod 644 /home/hermes/olv/entropy_serve/dgx_entropy_pool.bin'
Nice=15
TimeoutStartSec=120
EOF

echo "=== 3. the LAN reader (bound to the whole LAN, read-only static file) ==="
sudo tee /etc/systemd/system/libby-entropy-http.service >/dev/null <<EOF
[Unit]
Description=Serve Libby's entropy pool to the LAN (DGX pulls it)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hermes
WorkingDirectory=$SERVE
ExecStart=/usr/bin/python3 -m http.server $PORT --bind 0.0.0.0 --directory $SERVE
Restart=on-failure
RestartSec=5
Nice=15

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now libby-entropy-http.service
sudo systemctl start libby-entropy.service

echo "=== 4. state ==="
sleep 1
systemctl is-active libby-entropy-http.service
ss -ltn 2>/dev/null | grep ":$PORT " || echo "  (not listening - check the unit)"
ls -la "$SERVE"
echo
echo "--- local read-back ---"
curl -s -m 5 "http://127.0.0.1:$PORT/dgx_entropy_pool.bin" | xxd | head -2
echo
echo "--- the pool the brain reads, for comparison ---"
xxd "$POOL" | head -2
