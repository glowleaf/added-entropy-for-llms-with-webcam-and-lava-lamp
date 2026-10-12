#!/usr/bin/env python3
"""Restart Libby's brain on the patched binary and prove the webcam pool is
actually reaching the sampler.

Test: send the SAME request with an EXPLICIT fixed seed.
  - pool unchanged  -> output should be BIT-IDENTICAL (determinism intact)
  - pool refreshed  -> output should DIFFER (the camera is in the seed)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8011/v1/chat/completions"
POOL = "/home/hermes/olv/libby_webcam_entropy.bin"


def sh(cmd, timeout=180):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def ask(seed=12345, n=24):
    body = json.dumps({
        "model": "libby-uncensored",
        "messages": [{"role": "user", "content": "Say one short sentence about the sea."}],
        "max_tokens": n, "temperature": 1.0, "seed": seed,
    }).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"].strip()


print("=== 1. restarting the brain on the patched binary ===")
sh("sudo systemctl restart llama-abliterated.service")
ok = False
for _ in range(60):
    time.sleep(2)
    try:
        urllib.request.urlopen("http://127.0.0.1:8011/health", timeout=4).read()
        ok = True
        break
    except Exception:
        pass
print("   health: %s" % ("ok" if ok else "DID NOT COME UP"))
if not ok:
    print(sh("sudo journalctl -u llama-abliterated -n 25 --no-pager"))
    sys.exit(1)
print("   " + sh("systemctl is-active llama-abliterated.service"))

pool_before = open(POOL, "rb").read().hex()
print("   pool now: %s..." % pool_before[:16])

print()
print("=== 2. same explicit seed, two requests, pool UNCHANGED ===")
a = ask()
b = ask()
print("   A: %r" % a)
print("   B: %r" % b)
print("   identical: %s   <- determinism must hold" % (a == b))

print()
print("=== 3. force a fresh camera pool, same seed again ===")
sh("sudo systemctl start libby-webcam-entropy.service")
time.sleep(1)
pool_after = open(POOL, "rb").read().hex()
print("   pool now: %s...   changed: %s" % (pool_after[:16], pool_after != pool_before))
c = ask()
print("   C: %r" % c)
print("   C differs from A: %s   <- the camera reached the sampler" % (c != a))

print()
print("=== 4. no explicit seed: two requests should still differ (variety kept) ===")
body = json.dumps({"model": "libby-uncensored",
                   "messages": [{"role": "user", "content": "Say one short sentence about the sea."}],
                   "max_tokens": 24, "temperature": 1.0}).encode()
def ask_noseed():
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()
d1, d2 = ask_noseed(), ask_noseed()
print("   D: %r" % d1)
print("   E: %r" % d2)
print("   differ: %s" % (d1 != d2))
