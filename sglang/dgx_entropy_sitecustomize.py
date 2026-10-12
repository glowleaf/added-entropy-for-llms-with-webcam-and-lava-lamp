"""
sitecustomize.py - DGX entropy wiring for the Qwen3.8-27B SGLang server.

Installed at /usr/local/lib/python3.12/dist-packages/sitecustomize.py inside a
derivative image, so Python imports it automatically before anything else runs.

What it does: reads the shared physical-entropy pool (the camera/lava-lamp pool
built by the Ubuntu box) and uses it to seed the process RNGs - Python's
`random` and, the moment torch is first imported, torch's global generator plus
every CUDA generator. SGLang samples from torch's global RNG whenever a request
does not carry a usable seed, so this is what makes the model's sampling
randomness derive from the physical sources.

Still mixed with os.urandom, deliberately. Either source being good makes the
seed good; both would have to fail the same way to poison it.

Fail-safe: any failure here - no pool, stale pool, missing torch, anything -
leaves the normal startup untouched. It can never stop the server from booting.

Env:
  DGX_ENTROPY_POOL      explicit pool path
  DGX_ENTROPY_MAX_AGE   seconds before a pool is considered stale (default 600)
  DGX_ENTROPY_OFF=1     disable entirely
  DGX_ENTROPY_VERBOSE=1 extra logging
"""
import hashlib
import os
import sys
import time

_DEFAULT_POOLS = [
    "/root/models/dgx_entropy_pool.bin",
    "/root/models/entropy_pool.bin",
]
_POOL = os.environ.get("DGX_ENTROPY_POOL", "")
_MAX_AGE = float(os.environ.get("DGX_ENTROPY_MAX_AGE", "600"))
_OFF = os.environ.get("DGX_ENTROPY_OFF") == "1"
_VERBOSE = os.environ.get("DGX_ENTROPY_VERBOSE") == "1"


def _log(msg):
    try:
        sys.stderr.write("[dgx-entropy] %s\n" % msg)
        sys.stderr.flush()
    except Exception:
        pass


def _read_pool():
    """Return (bytes, note). Never raises."""
    if _OFF:
        return b"", "disabled by DGX_ENTROPY_OFF"
    candidates = ([_POOL] if _POOL else []) + _DEFAULT_POOLS
    for p in candidates:
        if not p:
            continue
        try:
            age = time.time() - os.path.getmtime(p)
        except FileNotFoundError:
            continue
        except Exception as e:
            return b"", "stat failed on %s (%s)" % (p, str(e)[:40])
        if age > _MAX_AGE:
            return b"", "stale: %s is %.0fs old (max %.0f)" % (p, age, _MAX_AGE)
        try:
            with open(p, "rb") as f:
                b = f.read(256)
        except Exception as e:
            return b"", "read failed on %s (%s)" % (p, str(e)[:40])
        if b:
            return b, "%s, %.0fs old, %d bytes" % (p, age, len(b))
        return b"", "%s was empty" % p
    return b"", "no pool file found (looked at %s)" % ", ".join(c for c in candidates if c)


_pool, _note = _read_pool()
_material = hashlib.sha256(_pool + os.urandom(32)).digest()
_seed = int.from_bytes(_material[:8], "big")
_source = "physical pool + os.urandom" if _pool else "os.urandom only"

# --- python's random, immediately ---
try:
    import random
    random.seed(_material)
except Exception as e:
    _log("python random seed failed: %s" % str(e)[:60])

_log("sampling entropy from %s [%s]" % (_source, _note))
try:
    with open("/tmp/dgx_entropy_seed.txt", "w") as f:
        f.write("source=%s\nnote=%s\nseed=%d\nmaterial=%s\n"
                % (_source, _note, _seed, _material.hex()))
except Exception:
    pass


# --- torch: seeded the moment it is first imported, without importing it early ---
def _seed_torch(mod):
    try:
        mod.manual_seed(_seed)
        if getattr(mod, "cuda", None) is not None and mod.cuda.is_available():
            mod.cuda.manual_seed(_seed)
            try:
                mod.cuda.manual_seed_all(_seed)
            except Exception:
                pass
        _log("torch seeded with %d (global + cuda)" % _seed)
    except Exception as e:
        _log("torch seeding failed: %s" % str(e)[:60])


class _PostImportSeeder:
    """Seed a module right after it finishes importing, once."""

    def __init__(self, name, callback):
        self.name = name
        self.callback = callback
        self._armed = True

    def find_spec(self, fullname, path=None, target=None):
        if not self._armed or fullname != self.name:
            return None
        self._armed = False                      # disarm BEFORE find_spec, or we recurse
        try:
            import importlib.util
            spec = importlib.util.find_spec(fullname)
        except Exception:
            return None
        if spec is None or spec.loader is None:
            return None
        original = spec.loader.exec_module

        def exec_module(module):
            original(module)
            try:
                self.callback(module)
            except Exception as e:
                _log("post-import seeding failed: %s" % str(e)[:60])

        try:
            spec.loader.exec_module = exec_module
        except Exception:
            return None
        return spec


try:
    _hook = _PostImportSeeder("torch", _seed_torch)
    sys.meta_path.insert(0, _hook)
    if _VERBOSE:
        _log("torch post-import seeder armed")
except Exception as e:
    _log("could not arm torch seeder: %s" % str(e)[:60])
