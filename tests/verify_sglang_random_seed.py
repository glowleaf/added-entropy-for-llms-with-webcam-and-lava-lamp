#!/usr/bin/env python3
"""Does the pool reach SGLang's OWN process seed?  (v2 - surfaces errors)

ServerArgs.random_seed is drawn from Python's `random` module when unset
(server_args.py:4094), then applied by the engine via set_random_seed() in the
scheduler and tp_worker. Our sitecustomize seeds `random` from the pool before
that runs. So: different pool -> different random_seed.
"""
import os
import subprocess
import time

IMAGE = "dgx-sglang-entropy:local"
MODELS = "/home/machinegeorge/models"
TESTPOOL = os.path.join(MODELS, "dgx_entropy_TEST.bin")

PROBE = (
    "import traceback\n"
    "try:\n"
    "    from sglang.srt.server_args import ServerArgs\n"
    "    sa = ServerArgs(model_path='/root/models/current')\n"
    "    print('RANDOM_SEED', sa.random_seed)\n"
    "    print('DETERMINISTIC', sa.enable_deterministic_inference)\n"
    "except Exception:\n"
    "    traceback.print_exc()\n"
)


def run(pool_bytes):
    with open(TESTPOOL, "wb") as f:
        f.write(pool_bytes)
    os.chmod(TESTPOOL, 0o644)
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", "%s:/root/models" % MODELS,
         "-e", "DGX_ENTROPY_POOL=/root/models/dgx_entropy_TEST.bin",
         IMAGE, "python3", "-c", PROBE],
        capture_output=True, text=True, timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    d = {}
    for line in out.splitlines():
        if line.startswith("RANDOM_SEED"):
            d["seed"] = line.split()[1]
        elif line.startswith("DETERMINISTIC"):
            d["det"] = line.split()[1]
        elif "Error" in line and "err" not in d:
            d["err"] = line.strip()[:90]
    return d


print("=== pool A vs pool B ===")
a = run(bytes.fromhex("11" * 32))
b = run(bytes.fromhex("22" * 32))
print("   pool 11..  ->  ServerArgs.random_seed = %s   %s" % (a.get("seed"), a.get("err", "")))
print("   pool 22..  ->  ServerArgs.random_seed = %s   %s" % (b.get("seed"), b.get("err", "")))
differs = bool(a.get("seed") and b.get("seed") and a["seed"] != b["seed"])
print("   pool drives the engine's own seed: %s" % differs)

print()
print("=== determinism flag, straight from the engine ===")
print("   enable_deterministic_inference = %s" % a.get("det"))

print()
print("=== the live pool ===")
live = os.path.join(MODELS, "dgx_entropy_pool.bin")
try:
    st = os.stat(live)
    print("   %d bytes, %.0fs old" % (st.st_size, time.time() - st.st_mtime))
    with open(live, "rb") as f:
        c = run(f.read())
    print("   -> ServerArgs.random_seed = %s" % c.get("seed"))
except FileNotFoundError:
    print("   MISSING")

try:
    os.remove(TESTPOOL)
except OSError:
    pass
print()
print("DONE" if differs else "NOT PROVEN")
