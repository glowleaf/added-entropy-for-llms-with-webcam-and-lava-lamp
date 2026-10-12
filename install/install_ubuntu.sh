#!/usr/bin/env bash
# Wire physical entropy sources into Libby's brain, boot-persistent.
#   - ~/olv/entropy_sources.d/   drop-in directory; any executable in it is a source
#   - libby_entropy.py           runs every source, mixes, writes the pool
#   - libby-entropy.timer        refresh every 60s and at boot
#   - llama-abliterated drop-in  refresh before her brain starts, so a
#                                `systemctl restart` always comes up with a
#                                fresh pool. Prefixed with '-' so entropy can
#                                never stop her brain from starting.
set -eu

OLV=/home/hermes/olv
SRC="$OLV/entropy_sources.d"

echo "=== 1. directories ==="
install -d -m 755 "$SRC"
echo "  $SRC"

echo "=== 2. install the plumbing and the sources ==="
HERE="$(cd "$(dirname "$0")/.." && pwd)"
install -m 755 "$HERE/pool/entropy_pool.py" "$OLV/libby_entropy.py"
install -m 755 "$HERE/pool/sources.d/10-webcam" "$SRC/10-webcam"
install -m 644 "$HERE/pool/sources.d/README.md" "$SRC/README.md"
ls -la "$SRC"

echo "=== 3. refresh timer (boot + every 60s) ==="
sudo tee /etc/systemd/system/libby-entropy.service >/dev/null <<'EOF'
[Unit]
Description=Libby entropy pool - run every physical source and rebuild the sampler pool
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=hermes
Environment=HOME=/home/hermes
ExecStart=/usr/bin/python3 /home/hermes/olv/libby_entropy.py refresh
Nice=15
TimeoutStartSec=120
EOF

sudo tee /etc/systemd/system/libby-entropy.timer >/dev/null <<'EOF'
[Unit]
Description=Refresh Libby's entropy pool at boot and every 60s

[Timer]
OnBootSec=15s
OnUnitActiveSec=60s
AccuracySec=5s
Persistent=true

[Install]
WantedBy=timers.target
EOF

# retire the old webcam-only unit; leave the files in place, just stop it
sudo systemctl disable --now libby-webcam-entropy.timer 2>/dev/null || true

echo "=== 4. refresh before her brain starts ==="
sudo install -d -m 755 /etc/systemd/system/llama-abliterated.service.d
sudo tee /etc/systemd/system/llama-abliterated.service.d/entropy.conf >/dev/null <<'EOF'
# Keep the entropy pool fresh whenever her brain (re)starts.
# The '-' means a failure here can NEVER block the brain from coming up.
[Service]
ExecStartPre=-/usr/bin/python3 /home/hermes/olv/libby_entropy.py refresh
EOF

echo "=== 5. enable ==="
sudo systemctl daemon-reload
sudo systemctl enable --now libby-entropy.timer
sudo systemctl start libby-entropy.service

echo "=== 6. state ==="
systemctl is-enabled libby-entropy.timer
systemctl list-timers libby-entropy.timer --no-pager | head -3
echo "--- drop-in in place ---"
sudo systemctl cat llama-abliterated.service | tail -8
echo
echo "=== 7. pool ==="
python3 "$OLV/libby_entropy.py" sources
