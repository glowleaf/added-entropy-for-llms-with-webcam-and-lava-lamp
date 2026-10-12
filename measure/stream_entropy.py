#!/usr/bin/env python3
"""
stream_entropy.py - what is the camera's live MJPEG stream actually worth
as an entropy source? Measured, with controls.

Taps the ALREADY RUNNING stream read-only at http://127.0.0.1:8080/stream.
Does not open /dev/video0 and does not disturb the running pipeline.

Controls:
  A. pure random noise            -> what real noise looks like
  B. that same noise after JPEG q5 -> what the codec does to it
  C. the live camera stream        -> what you would actually be harvesting
"""
import io
import urllib.request
import numpy as np
import cv2

URL = "http://127.0.0.1:8080/stream"
N = 12


def grab_frames(url, n, timeout=25):
    req = urllib.request.urlopen(url, timeout=timeout)
    buf, frames = b"", []
    while len(frames) < n:
        chunk = req.read(8192)
        if not chunk:
            break
        buf += chunk
        while True:
            s = buf.find(b"\xff\xd8")
            e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
            if s < 0 or e < 0:
                break
            img = cv2.imdecode(np.frombuffer(buf[s:e + 2], np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                frames.append(img)
            buf = buf[e + 2:]
            if len(frames) >= n:
                break
    req.close()
    return frames


def autocorr(x, y=None):
    if y is None:
        y = x
    a = x.ravel().astype(np.float64); b = y.ravel().astype(np.float64)
    a -= a.mean(); b -= b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


def shannon(x):
    c = np.bincount(x.ravel(), minlength=256).astype(float)
    p = c[c > 0] / c.sum()
    return float(-(p * np.log2(p)).sum())


def min_entropy(x):
    c = np.bincount(x.ravel(), minlength=256)
    return float(-np.log2(c.max() / c.sum()))


def block_ratio(x):
    """JPEG is 8x8. If the codec is visible, the seam between blocks is louder
       than the interior. Ratio ~1.0 means no block structure."""
    d = np.abs(np.diff(x.astype(np.int16), axis=1)).astype(np.float64)
    cols = np.arange(d.shape[1])
    seam = d[:, (cols % 8) == 7].mean()
    inner = d[:, (cols % 8) != 7].mean()
    return float(seam / inner) if inner else 0.0


def report(tag, x, prev=None):
    print(f"   {tag:<26} autocorr {autocorr(x, prev):+.4f}   "
          f"block {block_ratio(x):.4f}   shannon {shannon(x):.4f}   "
          f"min-ent {min_entropy(x):.4f}")


print("=" * 78)
print("CONTROL A - pure random noise (this is what an entropy source looks like)")
print("=" * 78)
noise = np.random.randint(0, 256, (240, 320), dtype=np.uint8)
report("os-random noise", noise)

print()
print("=" * 78)
print("CONTROL B - that SAME noise, passed through JPEG at q5 (what MJPEG does)")
print("=" * 78)
ok, enc = cv2.imencode(".jpg", noise, [cv2.IMWRITE_JPEG_QUALITY, 5])
dec = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
report("noise after jpeg q5", dec, noise)
print(f"   correlation survived: {autocorr(dec, noise):+.4f}  "
      f"(1.0 = untouched, 0.0 = codec erased it)")
print(f"   compressed size: {len(enc.tobytes()):,} bytes for {noise.size:,} pixels "
      f"({len(enc.tobytes())/noise.size:.4f} bytes/pixel)")

print()
print("=" * 78)
print("C - THE LIVE CAMERA STREAM")
print("=" * 78)
F = grab_frames(URL, N)
if len(F) < 4:
    print(f"   only got {len(F)} frames from {URL}")
else:
    print(f"   got {len(F)} frames at {F[0].shape[1]}x{F[0].shape[0]}")
    prev = None
    for f in F[:6]:
        report("live frame", f, prev)
        prev = f
    print()
    print("   frame-to-frame residual (the only genuinely fresh part):")
    for i in range(4):
        r = np.abs(F[i].astype(np.int16) - F[i + 1].astype(np.int16)).astype(np.uint8)
        report(f"   residual {i}->{i+1}", r)
    print()
    print(f"   mean |frame delta| : {np.mean([np.abs(F[i].astype(np.int16)-F[i+1].astype(np.int16)).mean() for i in range(len(F)-1)]):.2f}")
    print(f"   identical frames?  : {all(np.array_equal(F[i], F[i+1]) for i in range(len(F)-1))}")
