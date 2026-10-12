#!/usr/bin/env python3
"""
webcam_entropy.py - is the Ubuntu box's camera actually a usable entropy source?

Measures, honestly:
  1. how much one frame changes from the next          (fresh information)
  2. how much of that change is STRUCTURE vs NOISE      (spatial autocorrelation)
  3. min-entropy bound of the conditioned output        (not Shannon - see note)
  4. a control: os.urandom on the same tests

Run:  python3 webcam_entropy.py
"""
import hashlib, os, subprocess, sys
import numpy as np
import cv2

CAM, FRAMES = 0, 12
TEST_BYTES = 200_000


def capture(n):
    cap = cv2.VideoCapture(CAM)
    if not cap.isOpened():
        sys.exit("could not open /dev/video0")
    frames = []
    for _ in range(n):
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
    cap.release()
    return frames


def shannon(b):
    c = np.bincount(np.frombuffer(b, dtype=np.uint8), minlength=256).astype(float)
    p = c[c > 0] / c.sum()
    return float(-(p * np.log2(p)).sum())


def min_entropy(b):
    """-log2 of the most common byte value. The honest bound, not Shannon."""
    c = np.bincount(np.frombuffer(b, dtype=np.uint8), minlength=256)
    return float(-np.log2(c.max() / c.sum()))


def autocorr_spatial(x):
    """Neighbour correlation. Pure noise -> ~0. Scene structure -> high."""
    a = x[:, :-1].ravel().astype(np.float64)
    b = x[:, 1:].ravel().astype(np.float64)
    a -= a.mean(); b -= b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


def autocorr_temporal(x, y):
    a = x.ravel().astype(np.float64); b = y.ravel().astype(np.float64)
    a -= a.mean(); b -= b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


def monobit(b):
    bits = np.unpackbits(np.frombuffer(b, dtype=np.uint8))
    ones = bits.sum() / len(bits)
    return float(ones)


print("=" * 66)
print("RAW FRAMES")
print("=" * 66)
F = capture(FRAMES)
if len(F) < 4:
    sys.exit(f"only got {len(F)} frames")
print(f"   captured {len(F)} frames, {F[0].shape[1]}x{F[0].shape[0]}, uint8 grey")

raw = b"".join(f.tobytes() for f in F)
print(f"   raw bytes {len(raw):,}")
print(f"   shannon entropy   {shannon(raw):.4f} bits/byte   (near 8 for ANY image - "
      "this number is a trap)")
print(f"   min-entropy bound {min_entropy(raw):.4f} bits/byte")
print(f"   spatial autocorr  {autocorr_spatial(F[0]):+.4f}   (scene structure)")

print()
print("=" * 66)
print("FRAME-TO-FRAME CHANGE - the fresh part")
print("=" * 66)
diffs = []
for a, b in zip(F[:-1], F[1:]):
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8)
    diffs.append(d)
for i, d in enumerate(diffs[:5]):
    print(f"   frame {i}->{i+1}: mean |delta| {d.mean():6.2f}   "
          f"spatial autocorr {autocorr_spatial(d):+.4f}")

print()
print("=" * 66)
print("CONDITIONED OUTPUT  (sha256 of each frame's residual chain)")
print("=" * 66)
# chain the residuals through sha256: this is how you would REALLY use it
pool = hashlib.sha256()
for d in diffs:
    pool.update(d.tobytes())
seed = pool.digest()
print(f"   chained digest: {seed.hex()}")

# gather a big sample by hashing many small residual chunks
chunks = []
for d in diffs:
    flat = d.tobytes()
    for off in range(0, len(flat) - 4096, 4096):
        chunks.append(hashlib.sha256(flat[off:off + 4096]).digest())
mine = b"".join(chunks)[:TEST_BYTES]
ctrl = os.urandom(TEST_BYTES)

print()
print(f"{'':<22}{'webcam-conditioned':>20}{'os.urandom':>16}")
for name, fn in (("shannon bits/byte", shannon),
                 ("min-entropy bits/byte", min_entropy),
                 ("ones fraction (0.5 ideal)", monobit)):
    print(f"   {name:<19}{fn(mine):>20.4f}{fn(ctrl):>16.4f}")

print()
print("   temporal autocorr between consecutive conditioned blocks:")
print(f"      webcam {autocorr_temporal(np.frombuffer(mine[:20000],dtype=np.uint8), np.frombuffer(mine[20000:40000],dtype=np.uint8)):+.4f}"
      f"     control {autocorr_temporal(np.frombuffer(ctrl[:20000],dtype=np.uint8), np.frombuffer(ctrl[20000:40000],dtype=np.uint8)):+.4f}")

print()
print("=" * 66)
print("KERNEL, FOR COMPARISON")
print("=" * 66)
print(f"   entropy_avail: {open('/proc/sys/kernel/random/entropy_avail').read().strip()}"
      "   (always 256 on kernels 5.18+ - it is fully seeded and never drains)")
print(f"   cpu hardware rng present: "
      + ("yes" if os.path.exists("/dev/hwrng") else "no /dev/hwrng (but rdrand is inline)"))
