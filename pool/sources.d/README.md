# Libby's entropy sources

Drop an **executable** in this directory and it is a source. That is the entire
interface. No edits to the brain, the C patch, or the systemd units are needed.

## Contract

* The file must be executable (`chmod +x`).
* On each run it prints any number of bytes to **stdout**.
* Those bytes are hashed into the pool together with every other source and
  with `os.urandom`.
* Non-zero exit, a crash, a timeout (25s), or no output: that source is simply
  skipped for that cycle. It can never break the pool or delay a request.
* Anything you print to stderr is shown in the journal for diagnostics.
* Use `LIBBY_ENTROPY_CONTRIBUTING` (set to the filename) if you want to log.

Prefix the filename with a number for ordering: `10-webcam`, `20-lavalamp`.

Run it once by hand to check it:

    ~/olv/entropy_sources.d/20-lavalamp > /dev/null && echo ok

## The pool

`~/olv/libby_entropy.py refresh` runs every source, hashes the lot with
`os.urandom(32)`, and writes the result to `~/olv/libby_webcam_entropy.bin`.

That 32-byte file is what the patched `llama.cpp` sampler folds into its
per-request seed (`get_rng_seed` -> `libby_webcam_seed_mix`). The brain only
ever reads a 32-byte file, so nothing here can add latency to a request.

Mixing is deliberate and is the same pattern a hardware wallet uses: the pool is
`sha256(all source material || os.urandom(32))`. **Either** source being good
makes the seed good. Both would have to fail the same way to poison it. It also
means a weak physical source cannot *weaken* the pool - but it cannot carry it
either, so nothing here is a security claim.

## Already wired

| source | what it does |
|---|---|
| `10-webcam` | Logitech QuickCam STX. Reads the already-running MJPEG stream on `127.0.0.1:8080` read-only, takes the temporal residual between distinct frames so the static scene cancels, prints it. Measured weak: min-entropy ~2.93 bits/byte vs 7.76 for true noise, and visible 8x8 JPEG block structure. |

## Adding a lava lamp

A lava lamp is a chaos source: the wax blobs move unpredictably, so successive
camera frames differ in ways nobody can forecast. The recipe is the same shape
as `10-webcam`:

1. Point a camera at the lamp. If it is a second USB camera, stream it with
   ffmpeg to a port, or read the device directly if nothing else holds it.
2. Take the residual between consecutive frames, not a single frame - the lamp
   is lit by a fixed bulb, so the background is constant and only the blobs
   move. Differencing throws away the constant and keeps the movement.
3. Print the residual to stdout. Do not hash it yourself - `libby_entropy.py`
   does that.
4. Do not darken or over-gain it to "make it noisier". A lava lamp's entropy is
   in the *motion*, which is high contrast and easy to capture. Gain-riding a
   dark frame mostly harvests sensor noise plus amplifier noise, and the
   amplifier's noise is not independent of the sensor's.
5. Print nothing and exit non-zero if the camera is unreachable. Silent zeros
   are worse than no contribution.

Then verify it is live:

    python3 ~/olv/libby_entropy.py refresh
    python3 ~/olv/libby_entropy.py sources
    journalctl -u libby-entropy.service -n 20 --no-pager

## Honest limits

* You cannot measure entropy from data - only bound it and inspect structure.
* Never feed raw pixels or a codec's output straight into a seed. Differencing
  plus SHA-256 is why `10-webcam` is not just "screenshot the room".
* The kernel already harvests hardware timing jitter, including from these
  devices. That is why the pool is mixed rather than replaced: this wiring adds
  a physical source, it does not replace the operating system's.
