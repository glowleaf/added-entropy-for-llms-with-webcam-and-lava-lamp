# Added entropy for LLMs, with a webcam (and a lava lamp)

Feeding a **physical** entropy source into a local LLM's sampling.

Local LLMs are seeded once from the OS at process start, and after that their sampling
randomness comes from software generators — Python's `random`, PyTorch's global RNG.
This wires an actual physical source (a camera pointed at a room, or better, at a lava
lamp) into that path, on both llama.cpp and SGLang, and shares one pool across machines
on the LAN.

It does **not** make the text better. What it changes is *where the randomness comes
from*. If you want better text, change the model. If you want the sampling randomness to
originate in physics you can point at, this is that.

---

## How it fits together

```
  physical source                     pool                       consumer
  ───────────────                     ────                       ────────
  ~/olv/entropy_sources.d/10-webcam   sha256(                   llama.cpp:
     │  reads the camera, prints         all source material      get_rng_seed()
     │  the temporal residual            ||                       per-request sampler seed
     ▼                                   os.urandom(32))          │
  entropy_pool.py refresh ──────────▶ pool (32 bytes) ──────────▶ SGLang:
                                        │                         sitecustomize seeds
                                        │                         Python random + torch
                                        ▼
                                  published on the LAN
                                        │
                                        ▼
                                  remote boxes pull it on a timer
```

Every source is an executable that prints bytes to stdout. That is the whole interface —
see `sources.d/README.md`. Adding a lava lamp is one file.

### Why the pool is *mixed* rather than *replaced*

The pool is `sha256(all source material || os.urandom(32))`. Either source being good
makes the seed good; both would have to fail **the same way** to poison it. This is the
same pattern a hardware wallet uses to combine its TRNG with the host's CSPRNG, and it is
why a weak camera cannot weaken the pool.

It also means a weak physical source cannot *carry* the pool. Nothing here is a security
claim.

---

## The honest measurements

The camera available here is a Logitech QuickCam Communicate STX (2006, pre-UVC,
MJPEG-only). `measure/stream_entropy.py` measures what it is actually worth, with
controls:

```
SOURCE (structureless sensor noise)   min-entropy 7.8945 bits/byte
single frame at -q:v 5                min-entropy 6.4848    82.1% retained   block 0.9969
temporal residual at -q:v 5           min-entropy 7.0036    88.7% retained   block 1.0001
```

Two things worth reading off that:

* **A single frame carries the codec's fingerprint** — 8×8 block seams at `0.9969`.
* **The temporal residual carries none** (`1.0001`, i.e. no structure at all), because
  differencing applies the same codec damage to both frames and subtraction cancels it.
  At `-q:v 31`, the worst the format offers, the residual still comes out at 6.96 bits/byte.

So the pipeline harvests the *sensor's* noise, not the encoder's decisions. `measure/codec_damage.py`
reproduces that table. `measure/entropy_demo.py` shows the other thing people get wrong —
temperature moves *which sample you draw* and never the model's belief, while noise injected
into the network moves the belief and costs accuracy roughly in proportion.

### What is actually true about the physics

Sensor shot noise is photon arrival, which is Poisson. That is not "randomness we cannot
predict yet" — it is not determined, and it is the only in-principle-irreducible randomness
anyone has found. A lens sitting in a lit room is continuously sampling it.

Honest boundary: the residual also contains *scene motion*. That is chaotic and
unpredictable to an observer, but it is information about the room, not fresh entropy to an
adversary who can see the room. The shot-noise component is the irreducible part. Point the
source at a lava lamp, or at the dark side of the room, and it is nearly all shot noise.

And the permanent limit: **you cannot measure entropy from data** — only bound it and
inspect its structure. Everything above is a bound and a structure check.

---

## Why Cloudflare points a camera at lava lamps

The same three principles are why this repo exists, so it is worth stating where they
come from. Cloudflare has a wall of lava lamps in the lobby of their San Francisco office,
photographed by a camera and fed into the randomness behind the TLS connections their
network serves — upwards of 55 million HTTP requests per second
([Randomness 101: LavaRand in Production](https://blog.cloudflare.com/randomness-101-lavarand-in-production/),
2017; [Harnessing chaos in Cloudflare offices](https://blog.cloudflare.com/harnessing-office-chaos/), 2024).

**1. The seed is the fragile part, not the generator.** Cryptography runs on a CSPRNG that
turns a random *seed* into an endless stream of unpredictable bytes. The generator itself
is fine; nobody breaks it. But, in Cloudflare's own words, *"this all depends on having a
secure random seed to begin with."* So the entire security of every connection reduces to
getting one thing right: real randomness at the start. That is why physical entropy is worth
attention — it is the single point where the guarantees either hold or silently do not.

**2. Local sources are plausible, not verifiable.** For years their servers seeded their
entropy pools from local noise — "the precise timing of packet arrivals or keyboard events."
That works, but it is unverifiable, and in a virtualised environment it can be far weaker
than it sounds or even partly influenceable by an adversary sharing the same host. A
physical source is out of reach in a way that a shared cache's timing is not.

**3. The decisive reason: you can look at it.** A wall of lava lamps is a chaotic physical
system that any person walking through the lobby can see is doing something unpredictable.
You cannot do that with a CPU's `RDRAND` — its internals are unpublished, so you must trust
the vendor. Entropy is the one input where a hidden defect destroys everything downstream
without a visible symptom, and there is a recent, expensive proof: a firmware flaw from 2021
meant one hardware wallet generated recovery seeds *without using its hardware random number
generator*, and roughly $88 million was drained from the resulting addresses before anyone
noticed, five years later. Against that class of failure, a source whose operation is visible
to the naked eye is worth having.

**And it is mixed, never sole.** LavaRand is one input among several, and by 2024 Cloudflare
had deliberately diversified it — *"what was initially just a single species of physical
entropy source – lava lamps – has grown and diversified."* That is the same doctrine used
here: many sources combined so that no single failure, and no single malicious source, can
poison the pool.

The honest addendum is that a wall of lava lamps is also superb communication — it makes an
invisible problem visible, and it has taught more people about entropy than any RFC. But the
cryptographic role is real, not decorative. Same three principles, different stakes: theirs
is the TLS for a third of the web, ours is where a local model's sampling randomness comes
from.

```
                seed = the fragile part
                        │
        ┌───────────────┼───────────────┐
   physical source   local noise    hardware RNG
   (you can see it)  (unverifiable) (vendor's word)
        └───────────────┼───────────────┘
                        ▼
                  hashed together        ← no single source can poison it
                        ▼
                     CSPRNG
```

---

## Findings that cost time

Recorded so nobody repeats them.

| Finding | Detail |
|---|---|
| `llama.cpp`'s choke point is `get_rng_seed()` | In `src/llama-sampler.cpp`. When the seed is `LLAMA_DEFAULT_SEED` it draws from `std::random_device`; every request without an explicit seed goes through it. |
| `SamplingParams.__post_init__` **cannot** be monkey-patched | SGLang's `SamplingParams` is a `msgspec.Struct`, which bakes the `__post_init__` reference in at class creation. Patching it fires zero times (probed). |
| SGLang's per-request `seed` is **inert** by default | `sampling_seed` is only turned into a tensor when `enable_deterministic` is set. Without `--enable-deterministic-inference` the sampler draws from torch's global RNG, so injecting a per-request seed looks like it works and does nothing. |
| SGLang draws its process seed from **Python's `random`** | `server_args.py`: `if self.random_seed is None: self.random_seed = random.randint(0, 1 << 30)`, then applied by the engine via `set_random_seed()` in the scheduler and tp_worker. Seeding Python's `random` early therefore reaches the engine's own official seed path. |
| ffmpeg's `-q:v 5` is **not** libjpeg quality 5 | `-q:v` runs 1 (best) to 31 (worst); libjpeg quality runs the other way. Mixing them up overstates codec damage by ~2.5×. |
| Do not take entropy from a codec's output | Measure the residual, not a frame. See the table above. |

---

## Install

Paths in the scripts are the ones in use on this setup (`/home/hermes/olv/...`). Adjust
for your own, or set the environment variables the modules already read
(`LIBBY_ENTROPY_SOURCES`, `LIBBY_WEBCAM_POOL`, `LIBBY_WEBCAM_STREAM`, `DGX_ENTROPY_POOL`,
`DGX_ENTROPY_MAX_AGE`, `DGX_ENTROPY_OFF`).

### 1. The pool and its sources (any box with the physical source attached)

```
install/install_ubuntu.sh
```

Installs `entropy_pool.py`, the `10-webcam` source, a systemd timer that refreshes the pool
every 60s and at boot, and a drop-in that refreshes it before the LLM service starts
(prefixed `-` so entropy can never block the service from coming up).

### 2. A local llama.cpp server

```
python3 llama-cpp/patch_llama_webcam_entropy.py    # backs up source + binary, idempotent
cmake --build build --target llama-server -j
```

The patch folds the pool into `get_rng_seed()`. It keeps the existing OS/clock value
mixed in, so every request still gets its own unique seed — no determinism regression.

### 3. A local SGLang server

```
sglang/wire_dgx_entropy.sh
```

Builds a derivative image whose `sitecustomize.py` reads the pool and seeds Python's
`random` and torch's global/CUDA generators from it, then points the service at that image
through the recipe's own `IMAGE` override. Torch is seeded via a post-import hook, so it is
never imported early.

### 4. Sharing one pool with other machines

```
install/publish_pool_to_lan.sh     # on the box that owns the physical source
```

Serves the 32-byte pool over the LAN (no credentials, read-only, static file). Remote boxes
pull it on a timer into a local file that their consumer reads. **Because remote boxes
consume the published pool rather than harvesting for themselves, adding a source once
feeds every machine.**

---

## Adding a lava lamp

A lava lamp is a good source: the wax moves unpredictably, so consecutive frames differ in
ways nobody can forecast. Drop an executable into the sources directory; it prints bytes.

The recipe, in full, is in `sources.d/README.md`. The two things that matter:

* **Difference consecutive frames, do not single-frame it.** The lamp is lit by a fixed
  bulb, so the background is constant and only the blobs move. Differencing throws away the
  constant and keeps the motion.
* **Do not darken or over-gain it to "make it noisier."** A lamp's entropy is in the
  *motion*, which is high contrast and easy to capture. Gain-riding a dark frame mostly
  harvests amplifier noise, and the amplifier's noise is not independent of the sensor's.

Then: `entropy_pool.py refresh && entropy_pool.py sources`.

---

## Files

| Path | What |
|---|---|
| `pool/entropy_pool.py` | Runs every source, mixes, writes the pool, prints a seed (`refresh` / `get` / `sources` / `test`) |
| `pool/sources.d/10-webcam` | The webcam source: reads the running MJPEG stream, prints the temporal residual |
| `pool/sources.d/README.md` | The source contract + the lava-lamp recipe |
| `llama-cpp/patch_llama_webcam_entropy.py` | Patches `get_rng_seed()` in `src/llama-sampler.cpp` |
| `sglang/dgx_entropy_sitecustomize.py` | Seeds Python + torch RNGs from the pool; installed into the image |
| `sglang/wire_dgx_entropy.sh` | Pull timer + derivative image build + service override |
| `install/install_ubuntu.sh` | Pool, sources, timer, service drop-in |
| `install/publish_pool_to_lan.sh` | LAN publication for remote consumers |
| `measure/codec_damage.py` | How much of a source the codec removes, by quality setting |
| `measure/stream_entropy.py` | Entropy bounds + codec structure on a live MJPEG stream |
| `measure/webcam_entropy.py` | Same, reading the capture device directly |
| `measure/entropy_demo.py` | The three places entropy can enter a network, measured side by side |
| `tests/verify_brain_webcam_entropy.py` | End-to-end: restart-safety, per-request variety, pool reaches the sampler |
| `tests/verify_sglang_random_seed.py` | Proves the pool reaches SGLang's own `random_seed` |

---

## Fail-safe by construction

Every failure path degrades to `os.urandom` and logs why: no source, a source that crashes
or times out, an empty or stale pool, an unreadable file, a missing torch. A source cannot
break the pool, and entropy can never block a model from starting. `entropy_pool.py test`
includes the zero-sources worst case.

## License

MIT. See `LICENSE`.
