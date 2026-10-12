#!/usr/bin/env python3
"""
codec_damage.py - how much of a REAL physical entropy source the pipeline throws away.

The camera's shot noise is genuinely quantum: photon arrival is Poisson, so the
randomness in a single photosite reading is not determined by anything - not by
physics we don't know, but not determined at all. That is the only
in-principle-irreducible randomness anyone has ever found.

So the question is not "is the source good". The question is how much of it
survives the trip. This measures that, at every quality setting, on the same
kind of noise the sensor produces.

Note: q is libjpeg quality. In ffmpeg -q:v, LOWER IS BETTER (2 ~= quality 95,
31 ~= quality 20). The running stream uses -q:v 5.
"""
import numpy as np
import cv2

H, W = 480, 640
rng = np.random.default_rng(7)


def min_entropy(x):
    c = np.bincount(x.ravel(), minlength=256)
    return float(-np.log2(c.max() / c.sum()))


def autocorr(a, b):
    a = a.ravel().astype(np.float64); b = b.ravel().astype(np.float64)
    a -= a.mean(); b -= b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


def block_ratio(x):
    """JPEG is 8x8. Seam louder than interior = codec structure is visible."""
    d = np.abs(np.diff(x.astype(np.int16), axis=1)).astype(np.float64)
    cols = np.arange(d.shape[1])
    return float(d[:, cols % 8 == 7].mean() / d[:, cols % 8 != 7].mean())


# A stand-in for sensor shot noise: independent per-pixel, no structure at all.
# This is the BEST CASE a sensor noise source can look like.
sensor = rng.integers(0, 256, (H, W), dtype=np.uint8)
print("SOURCE (stand-in for sensor shot noise, structureless)")
print("   min-entropy %.4f bits/byte      block ratio %.4f\n"
      % (min_entropy(sensor), block_ratio(sensor)))

print("THE TRIP : single frame")
print("   %-10s %-8s %-14s %-12s %-10s %s"
      % ("q:v", "kb", "min-entropy", "retained", "corr", "block"))
for q in (2, 3, 5, 8, 12, 20, 31):
    ok, enc = cv2.imencode(".jpg", sensor, [cv2.IMWRITE_JPEG_QUALITY, max(1, 100 - q * 3)])
    img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    me = min_entropy(img)
    print("   %-10d %-8.1f %-14.4f %-12s %-10.4f %.4f"
          % (q, len(enc.tobytes()) / 1024, me,
             "%.1f%%" % (100 * me / min_entropy(sensor)), autocorr(img, sensor),
             block_ratio(img)))

print()
print("THE TRIP : temporal residual of two consecutive frames")
print("   (this is what 10-webcam actually harvests - differencing cancels the")
print("    static scene and keeps the noise, so it survives the codec better)")
for q in (2, 5, 12, 31):
    f1 = sensor
    f2 = rng.integers(0, 256, (H, W), dtype=np.uint8)
    _, e1 = cv2.imencode(".jpg", f1, [cv2.IMWRITE_JPEG_QUALITY, max(1, 100 - q * 3)])
    _, e2 = cv2.imencode(".jpg", f2, [cv2.IMWRITE_JPEG_QUALITY, max(1, 100 - q * 3)])
    d1 = cv2.imdecode(e1, cv2.IMREAD_GRAYSCALE).astype(np.int16)
    d2 = cv2.imdecode(e2, cv2.IMREAD_GRAYSCALE).astype(np.int16)
    resid = np.abs(d1 - d2).astype(np.uint8)
    print("   q:v %-4d residual: min-entropy %.4f   block ratio %.4f   nonzero %.1f%%"
          % (q, min_entropy(resid), block_ratio(resid), 100 * (resid > 0).mean()))

print()
print("WHAT THE CURRENT STREAM LOSES")
q = 5
ok, enc = cv2.imencode(".jpg", sensor, [cv2.IMWRITE_JPEG_QUALITY, 100 - q * 3])
img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
lost = 1 - min_entropy(img) / min_entropy(sensor)
print("   at -q:v %d the codec removes %.1f%% of the source's min-entropy"
      % (q, 100 * lost))
print("   and stamps %.2fx block seams on what is left" % block_ratio(img))
print()
print("   the fix is not a better camera, it is not letting the camera compress:")
print("   demand RAW YUYV (uncompressed) from the lamp's camera. Most UVC")
print("   webcams offer it; this 2006 QuickCam does not, which is why it")
print("   cannot be fixed and only replaced.")
