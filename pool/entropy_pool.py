#!/usr/bin/env python3
"""
libby_entropy.py - the entropy plumbing for Libby's brain.

Any number of PHYSICAL sources can feed her sampler without touching the brain,
the C patch, or the systemd units again. To add one:

    drop an EXECUTABLE into  ~/olv/entropy_sources.d/
    it prints any number of bytes to stdout on each run

That is the whole interface. It gets run every cycle, its bytes are hashed into
the pool, and the pool is what the sampler seed folds in. A lava lamp is one
script in that directory. So is a second camera, a microphone, a Geiger counter.

    python3 libby_entropy.py refresh    run every source, rebuild the pool
    python3 libby_entropy.py get        print a uint32 seed (instant)
    python3 libby_entropy.py sources    show the wired sources and their state
    python3 libby_entropy.py test       prove the pipeline end to end

Pool file:  ~/olv/libby_webcam_entropy.bin   (32 bytes; path baked into the
            patched llama.cpp default, override with LIBBY_WEBCAM_POOL)

Fail-safe by construction: every source failure, a missing source, an empty
pool, or a stale pool all degrade to os.urandom alone. This can never stop her
brain from seeding itself, and it never blocks a request - the brain only ever
reads a 32-byte file.
"""
import hashlib
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
SOURCES = os.environ.get("LIBBY_ENTROPY_SOURCES", os.path.join(HOME, "olv/entropy_sources.d"))
POOL = os.environ.get("LIBBY_WEBCAM_POOL", os.path.join(HOME, "olv/libby_webcam_entropy.bin"))
FRESH_S = 600
SRC_TIMEOUT = 25


def list_sources():
    if not os.path.isdir(SOURCES):
        return []
    out = []
    for name in sorted(os.listdir(SOURCES)):
        p = os.path.join(SOURCES, name)
        if os.path.isfile(p) and os.access(p, os.X_OK) and not name.startswith("."):
            out.append((name, p))
    return out


def run_source(name, path):
    """Run one source, return its raw stdout bytes (b'' on any failure)."""
    env = dict(os.environ)
    env["LIBBY_ENTROPY_CONTRIBUTING"] = name
    try:
        r = subprocess.run([path], capture_output=True, timeout=SRC_TIMEOUT, env=env)
        if r.returncode != 0 and not r.stdout:
            print("  %-16s FAILED rc=%d %s" % (name, r.returncode,
                                                (r.stderr or b"")[:80].decode(errors="replace")),
                  file=sys.stderr)
            return b""
        print("  %-16s %d bytes" % (name, len(r.stdout)), file=sys.stderr)
        return r.stdout
    except subprocess.TimeoutExpired:
        print("  %-16s TIMEOUT after %ds" % (name, SRC_TIMEOUT), file=sys.stderr)
        return b""
    except Exception as e:                                            # noqa: BLE001
        print("  %-16s error %s" % (name, str(e)[:60]), file=sys.stderr)
        return b""


def refresh(verbose=True):
    """Run every source, hash them together with os.urandom, write the pool.
       Always leaves a usable pool behind, even with zero working sources."""
    parts = []
    srcs = list_sources()
    if verbose:
        print("sources: %d wired" % len(srcs), file=sys.stderr)
    for name, path in srcs:
        b = run_source(name, path)
        if b:
            parts.append(hashlib.sha256(name.encode() + b).digest())
    material = b"".join(parts)
    pool = hashlib.sha256(material + os.urandom(32)).digest()
    tmp = POOL + ".tmp"
    with open(tmp, "wb") as f:
        f.write(pool)
    os.replace(tmp, POOL)
    try:
        os.chmod(POOL, 0o600)
    except Exception:                                                 # noqa: BLE001
        pass
    if verbose:
        print("pool: %d/%d sources contributed, %d bytes of source material"
              % (len(parts), len(srcs), len(material)), file=sys.stderr)
    return len(parts), len(srcs)


def get_seed():
    """uint32 for the sampler. Instant, never raises."""
    cam = b""
    note = "pool missing"
    try:
        age = time.time() - os.path.getmtime(POOL)
        if age <= FRESH_S:
            with open(POOL, "rb") as f:
                cam = f.read(32)
            note = "pool %.0fs old" % age
        else:
            note = "pool stale (%.0fs) - os.urandom only" % age
    except Exception as e:                                            # noqa: BLE001
        note = "pool unreadable (%s)" % str(e)[:40]
    d = hashlib.sha256(cam + os.urandom(32)).digest()
    return int.from_bytes(d[:4], "big"), note


def cmd_sources():
    print("sources dir: %s" % SOURCES)
    srcs = list_sources()
    if not srcs:
        print("  (none wired)")
    for name, path in srcs:
        print("  %-18s %s" % (name, path))
    print()
    try:
        st = os.stat(POOL)
        print("pool: %s  %d bytes  %.0fs old" % (POOL, st.st_size, time.time() - st.st_mtime))
        print("      %s" % open(POOL, "rb").read(16).hex())
    except Exception as e:                                            # noqa: BLE001
        print("pool: MISSING (%s)" % e)


def cmd_test():
    print("=== 1. wired sources ===")
    for name, path in list_sources():
        print("  %-18s %s" % (name, path))
    print()
    print("=== 2. refresh, per-source bytes ===")
    n, tot = refresh()
    print()
    print("=== 3. three seeds in a row (must all differ) ===")
    seen = set()
    for _ in range(3):
        s, note = get_seed()
        seen.add(s)
        print("  %d\t%s" % (s, note))
    print("  distinct: %d/3" % len(seen))
    print()
    print("=== 4. empty-source worst case (must still produce a seed) ===")
    empty = os.path.join(HOME, "olv/_entropy_test_empty")
    os.makedirs(empty, exist_ok=True)
    global SOURCES
    keep, SOURCES = SOURCES, empty
    try:
        n, tot = refresh(verbose=False)
        s, note = get_seed()
        print("  sources=%d  seed=%d  %s  -> survived" % (tot, s, note))
    finally:
        SOURCES = keep
        try:
            os.rmdir(empty)
        except OSError:
            pass
    refresh(verbose=False)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    if cmd == "refresh":
        n, tot = refresh()
        return 0 if tot else 0
    if cmd == "get":
        s, note = get_seed()
        print("%d\t%s" % (s, note))
        return 0
    if cmd == "sources":
        cmd_sources()
        return 0
    if cmd == "test":
        cmd_test()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
