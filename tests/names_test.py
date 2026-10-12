#!/usr/bin/env python3
"""
names_test.py - the harness behind docs/NAMES-TEST.md.

Asks a model for a list of names, repeatedly, under whatever conditions you set,
and scores the result. Written to be run against any OpenAI-compatible endpoint.

    # a local llama.cpp server
    python3 names_test.py --url http://127.0.0.1:8011/v1/chat/completions \
        --model local-model --runs 3

    # with a system prompt and without one, to see which one is doing the damage
    python3 names_test.py --system-file system.txt
    python3 names_test.py

Scoring is deliberately blunt and it is NOT to be trusted on its own - read the
raw text. A version of this script scored a dark-fantasy slop loop as "39/40
usable" because it counted any two capitalised words as a name. It now also
flags vocabulary that means the entry is prose rather than a name, but the raw
reply is always printed for exactly that reason.
"""
import argparse
import json
import re
import sys
import time
import urllib.request

ASK = ("Write a list of 40 full names. One per line, numbered 1 to 40, each one a "
       "first name and a surname. Just the list, nothing before or after it.")

# words that mean the line is prose, not a name
PROSE = {"dying", "die", "dead", "blood", "soul", "souls", "hell", "rage", "agony",
         "tortured", "torment", "devour", "devouring", "scream", "screams", "slaughtered",
         "wound", "wounds", "abyss", "oblivion", "insatiable", "famine", "devastation",
         "poisoned", "hurt", "ache", "aching", "shattered", "curse", "cursed", "broken",
         "fierce", "wicked", "tainted", "unleashed", "unbound", "insane", "thirst",
         "hunger", "knife", "exist", "breath", "fire", "end", "to", "be", "like", "me",
         "my", "this", "every", "all", "the", "so", "much", "last", "piece", "no"}

# the usual AI-generated-name tells
SLOP_FIRST = {"luna", "nova", "seraphina", "seraphine", "elara", "aria", "lyra", "selene",
              "thorne", "raven", "ash", "kai", "azrael", "zephyr", "ember", "sage", "wren",
              "kaia", "freya", "orion", "atlas", "kael", "ryker", "cassian", "auren",
              "evren", "nyx", "isolde", "aeris", "kaida", "sylas", "vesper", "aurora"}
SLOP_LAST = {"blackwood", "ravenwood", "ashford", "thorne", "thorn", "nightingale",
             "blackthorn", "sterling", "vance", "savage", "knight", "daemon", "shadow",
             "wolf", "storm", "valentine", "everhart", "hawthorne", "grey", "sinclair",
             "drake", "frost", "winters", "ashcroft", "holloway", "wraith", "malice",
             "fathom", "fathoms", "oath", "vile", "wretch", "torn"}


def ask(url, model, system, n, temp, timeout):
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": ASK}]
    body = {"model": model, "messages": msgs, "max_tokens": n, "temperature": temp}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    ch = d["choices"][0]
    return ch["message"]["content"].strip(), time.time() - t0, ch.get("finish_reason")


def score(text):
    names, junk, nums = [], 0, []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)[\.\)]?\s+(.+?)\s*$", line)
        if not m:
            continue
        nums.append(int(m.group(1)))
        words = m.group(2).split()
        if len(words) < 2:
            junk += 1
            continue
        if any(w.strip(".,'").lower() in PROSE for w in words):
            junk += 1
            continue
        if not all(re.match(r"^[A-Z][a-z'\-]+$", w) for w in words[:2]):
            junk += 1
            continue
        names.append(m.group(2).strip())
    slop = [x for x in names if x.split()[0].lower() in SLOP_FIRST
            or x.split()[-1].lower() in SLOP_LAST]
    dup_nums = len(nums) - len(set(nums))
    reuse = len(names) - len(set(n.split()[0].lower() for n in names))
    return names, junk, dup_nums, slop, reuse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8011/v1/chat/completions")
    ap.add_argument("--model", default="local-model")
    ap.add_argument("--system-file", help="file containing a system prompt")
    ap.add_argument("--system", help="system prompt on the command line")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=1400)
    ap.add_argument("--temp", type=float, default=0.85)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    system = a.system
    if a.system_file:
        system = open(a.system_file).read().strip()
    print("endpoint : %s" % a.url)
    print("model    : %s" % a.model)
    print("system   : %s" % ("yes (%d chars)" % len(system) if system else "NONE"))

    for run in range(1, a.runs + 1):
        text, dt, fin = ask(a.url, a.model, system, a.max_tokens, a.temp, a.timeout)
        names, junk, dup, slop, reuse = score(text)
        print("\n=== run %d: %.0fs finish=%s ===" % (run, dt, fin))
        print("   usable names      : %d / 40" % len(names))
        print("   prose/junk lines  : %d" % junk)
        print("   duplicated numbers: %d" % dup)
        print("   AI-ism hits       : %d %s" % (len(slop), slop or ""))
        print("   first names reused: %d" % reuse)
        print()
        print(text)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
