#!/usr/bin/env python
"""
entropy_demo.py - the three places randomness can enter a neural network,
measured side by side.

    python entropy_demo.py

  A. the SEED        -> picks where training starts
  B. the SAMPLER     -> picks which token you draw (temperature)
  C. the ACTIVATIONS -> noise injected INSIDE the network (nobody does this)

Pure python, no dependencies. Trains a real 4->8->6 classifier first, so the
effects are measured on a model that actually works.
"""
import math, random

D_IN, D_H, D_OUT = 4, 8, 6
STEPS, LR = 900, 0.25


# ------------------------------------------------------------------ data
def protos(seed=3):
    r = random.Random(seed)
    return [[r.gauss(0, 1) for _ in range(D_IN)] for _ in range(D_OUT)]


def make_data(P, n=300, seed=11):
    r = random.Random(seed)
    X, Y = [], []
    for _ in range(n):
        k = r.randrange(len(P))
        X.append([P[k][i] + r.gauss(0, 0.30) for i in range(D_IN)])
        Y.append(k)
    return X, Y


# ------------------------------------------------------------------ net
def init(seed):
    r = random.Random(seed)
    return {
        "W1": [[r.uniform(-1, 1) for _ in range(D_IN)] for _ in range(D_H)],
        "b1": [0.0] * D_H,
        "W2": [[r.uniform(-1, 1) for _ in range(D_H)] for _ in range(D_OUT)],
        "b2": [0.0] * D_OUT,
    }


def softmax(z):
    m = max(z); e = [math.exp(v - m) for v in z]; s = sum(e)
    return [v / s for v in e]


def forward(p, x, act_noise=0.0, rng=None, weight_noise=0.0):
    """act_noise == 0.0 means never touch the activations. That is the norm.
       weight_noise adds noise to the WEIGHTS themselves - a different model."""
    W1, W2 = p["W1"], p["W2"]
    if weight_noise and rng is not None:
        W1 = [[v + rng.gauss(0.0, weight_noise) for v in row] for row in p["W1"]]
        W2 = [[v + rng.gauss(0.0, weight_noise) for v in row] for row in p["W2"]]
    h = []
    for j in range(D_H):
        z = math.tanh(sum(W1[j][i] * x[i] for i in range(D_IN)) + p["b1"][j])
        if act_noise and rng is not None:
            z += rng.gauss(0.0, act_noise)          # <-- entropy INSIDE the net
        h.append(z)
    return [sum(W2[k][j] * h[j] for j in range(D_H)) + p["b2"][k] for k in range(D_OUT)], h


def train(p, X, Y):
    n = len(X)
    for _ in range(STEPS):
        gW1 = [[0.0] * D_IN for _ in range(D_H)]; gb1 = [0.0] * D_H
        gW2 = [[0.0] * D_H for _ in range(D_OUT)]; gb2 = [0.0] * D_OUT
        for x, y in zip(X, Y):
            logits, h = forward(p, x)
            pr = softmax(logits)
            d = list(pr); d[y] -= 1.0                # dL/dlogits for cross-entropy
            for k in range(D_OUT):
                gb2[k] += d[k]
                for j in range(D_H):
                    gW2[k][j] += d[k] * h[j]
            for j in range(D_H):
                dh = sum(d[k] * p["W2"][k][j] for k in range(D_OUT)) * (1 - h[j] * h[j])
                gb1[j] += dh
                for i in range(D_IN):
                    gW1[j][i] += dh * x[i]
        for k in range(D_OUT):
            p["b2"][k] -= LR * gb2[k] / n
            for j in range(D_H):
                p["W2"][k][j] -= LR * gW2[k][j] / n
        for j in range(D_H):
            p["b1"][j] -= LR * gb1[j] / n
            for i in range(D_IN):
                p["W1"][j][i] -= LR * gW1[j][i] / n
    return p


# ------------------------------------------------------------------ measure
def entropy_bits(pr):
    return -sum(v * math.log2(v) for v in pr if v > 0)


def evaluate(p, X, Y, temperature=1.0, act_noise=0.0, logit_noise=0.0,
             weight_noise=0.0, draws=60, trials=8, seed=5):
    """
    belief  = how often the model's TOP PICK matches the truth under this knob.
              temperature cannot move this number; noise inside the net can.
    variety = how much the drawn output varies across draws (0 = always same)
    """
    rng = random.Random(seed)
    belief = 0.0
    div = 0.0
    for x, y in zip(X, Y):
        hits = 0
        for _ in range(trials):
            logits, _ = forward(p, x, act_noise, rng, weight_noise)
            if logit_noise:
                logits = [l + rng.gauss(0.0, logit_noise) for l in logits]
            if logits.index(max(logits)) == y:
                hits += 1
        belief += hits / trials
        counts = [0] * D_OUT
        for _ in range(draws):
            logits, _ = forward(p, x, act_noise, rng, weight_noise)
            if logit_noise:
                logits = [l + rng.gauss(0.0, logit_noise) for l in logits]
            pr = softmax([l / temperature for l in logits])
            r, c, pick = rng.random(), 0.0, D_OUT - 1
            for k, v in enumerate(pr):
                c += v
                if r < c:
                    pick = k; break
            counts[pick] += 1
        div += entropy_bits([c / draws for c in counts]) / math.log2(D_OUT)
    return belief / len(X), div / len(X)


# ------------------------------------------------------------------ main
def main():
    P = protos()
    Xtr, Ytr = make_data(P, 300, seed=11)
    Xte, Yte = make_data(P, 150, seed=99)

    print("A. THE SEED - same data, three different starting points\n")
    models = []
    for s in (1, 2, 3):
        p = train(init(s), Xtr, Ytr)
        a, _ = evaluate(p, Xte, Yte, temperature=0.05)
        models.append(p)
        w1 = p["W1"][0]
        print(f"   seed {s}:  accuracy {a*100:5.1f}%    first hidden row "
              + " ".join(f"{v:+.6f}" for v in w1))
    print("   -> weights share nothing, behaviour is the same\n")

    p = models[0]
    print("B. THE SAMPLER - vary temperature. weights never change.\n")
    print(f"   {'temperature':>12}{'belief correct':>16}{'output variety':>18}")
    for t in (0.05, 0.3, 0.7, 1.0, 2.0, 4.0, 8.0):
        a, d = evaluate(p, Xte, Yte, temperature=t)
        print(f"   {t:>12}{a*100:>15.1f}%{d:>18.3f}")
    print("   -> variety rises a lot. the model's answer never moves.\n")

    print("C. ACTIVATION NOISE - entropy injected INSIDE the network\n")
    print(f"   {'noise sigma':>12}{'belief correct':>16}{'output variety':>18}")
    for s in (0.0, 0.1, 0.2, 0.4, 0.8, 1.5, 2.5, 4.0, 6.0):
        a, d = evaluate(p, Xte, Yte, temperature=0.05, act_noise=s)
        print(f"   {s:>12}{a*100:>15.1f}%{d:>18.3f}")
    print("   -> at low noise variety rises free. then the answer itself decays.\n")

    print("D. LOGIT NOISE - the same idea applied at the very end\n")
    print(f"   {'noise sigma':>12}{'belief correct':>16}{'output variety':>18}")
    for s in (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0):
        a, d = evaluate(p, Xte, Yte, temperature=0.05, logit_noise=s)
        print(f"   {s:>12}{a*100:>15.1f}%{d:>18.3f}")

    print("\nE. WEIGHT NOISE - entropy added to what the model BELIEVES\n")
    print(f"   {'noise sigma':>12}{'belief correct':>16}{'output variety':>18}")
    for s in (0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8):
        a, d = evaluate(p, Xte, Yte, temperature=0.05, weight_noise=s)
        print(f"   {s:>12}{a*100:>15.1f}%{d:>18.3f}")
    print("   -> a narrow band where it HELPS, then a cliff. entropy in the")
    print("      belief is not free the way entropy in the sampler is.")


if __name__ == "__main__":
    main()
