#!/usr/bin/env python3
"""Patch llama.cpp so the sampler's per-request RNG seed folds in Libby's
webcam entropy pool. Backs up both source and binary first. Idempotent."""
import os
import shutil
import sys

SRC = os.path.expanduser("~/llama.cpp/src/llama-sampler.cpp")
BIN = os.path.expanduser("~/llama.cpp/build/bin/llama-server")
MARK = "LIBBY_WEBCAM_ENTROPY"

OLD = """static uint32_t get_rng_seed(uint32_t seed) {
    if (seed == LLAMA_DEFAULT_SEED) {
        // use system clock if std::random_device is not a true RNG
        static bool is_rd_prng = std::random_device().entropy() == 0;
        if (is_rd_prng) {
            return (uint32_t) std::chrono::system_clock::now().time_since_epoch().count();
        }
        std::random_device rd;
        return rd();
    }
    return seed;
}"""

NEW = """// === LIBBY_WEBCAM_ENTROPY (2026-10-13) =====================================
// Fold the webcam entropy pool into the per-request sampler seed.
// Pool = sha256(camera temporal residual || os.urandom(32)), refreshed on a
// timer by ~/olv/libby_webcam_seed.py. Either source being good makes the seed
// good; both would have to fail the same way to poison it. The OS/clock value
// is still mixed in, so every request keeps its own unique seed.
// Disable: unset LIBBY_WEBCAM_POOL and delete ~/olv/libby_webcam_entropy.bin.
static uint32_t libby_webcam_seed_mix(uint32_t s) {
    static const bool enabled = std::getenv("LIBBY_WEBCAM_OFF") == nullptr;
    if (!enabled) {
        return s;
    }
    std::string path;
    const char * pool = std::getenv("LIBBY_WEBCAM_POOL");
    if (pool != nullptr) {
        path = pool;
    } else {
        const char * home = std::getenv("HOME");
        if (home != nullptr) {
            path = std::string(home) + "/olv/libby_webcam_entropy.bin";
        }
    }
    if (path.empty()) {
        return s;
    }
    std::ifstream fin(path, std::ios::binary);
    if (!fin) {
        return s;
    }
    uint32_t words[8];
    fin.read(reinterpret_cast<char *>(words), sizeof(words));
    if (fin.gcount() != (std::streamsize) sizeof(words)) {
        return s;
    }
    uint32_t acc = 0;
    for (int i = 0; i < 8; ++i) {
        acc ^= words[i];
    }
    acc ^= acc >> 16; acc *= 0x7feb352du; acc ^= acc >> 15;
    return s ^ acc;
}
// ============================================================================

static uint32_t get_rng_seed(uint32_t seed) {
    if (seed == LLAMA_DEFAULT_SEED) {
        // use system clock if std::random_device is not a true RNG
        static bool is_rd_prng = std::random_device().entropy() == 0;
        if (is_rd_prng) {
            return libby_webcam_seed_mix(
                (uint32_t) std::chrono::system_clock::now().time_since_epoch().count());
        }
        std::random_device rd;
        return libby_webcam_seed_mix(rd());
    }
    return libby_webcam_seed_mix(seed);
}"""

src = open(SRC).read()

if MARK in src:
    print("already patched, nothing to do")
    sys.exit(0)

if OLD not in src:
    print("FAIL: could not find get_rng_seed verbatim - refusing to guess")
    sys.exit(1)

# includes we now need
for inc in ("<fstream>", "<string>"):
    if "#include %s" % inc not in src:
        src = src.replace("#include <numeric>", "#include <numeric>\n#include %s" % inc, 1)
        print("added include %s" % inc)

shutil.copy2(SRC, SRC + ".pre-webcam-entropy")
print("backed up %s" % (SRC + ".pre-webcam-entropy"))

src = src.replace(OLD, NEW, 1)
open(SRC, "w").write(src)
print("patched %s" % SRC)

# binary backup so a failed rebuild can be undone instantly
if os.path.exists(BIN) and not os.path.exists(BIN + ".pre-webcam-entropy"):
    shutil.copy2(BIN, BIN + ".pre-webcam-entropy")
    print("backed up %s" % (BIN + ".pre-webcam-entropy"))
for extra in ("libllama.so", "libggml.so", "libggml-base.so", "libggml-cpu.so"):
    p = os.path.expanduser("~/llama.cpp/build/bin/" + extra)
    if os.path.exists(p) and not os.path.exists(p + ".pre-webcam-entropy"):
        shutil.copy2(p, p + ".pre-webcam-entropy")
        print("backed up %s" % (p + ".pre-webcam-entropy"))

print("OK")
