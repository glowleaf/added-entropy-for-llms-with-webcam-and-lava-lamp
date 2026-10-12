# A names test

A cheap, boring task used to make output quality visible: ask a locally served 8B model for a
list of 40 full names, repeatedly, and score what comes back. Boring on purpose — a plodding
formatting task has nothing to hide behind, so when the model's conditioning is off you see it
immediately.

Harness: [`../tests/names_test.py`](../tests/names_test.py)

## What was run

Same endpoint, same sampler configuration, same physical entropy pool in the seed, two
conditions differing in exactly one way — whether a system prompt was sent at all.

| condition | result |
|---|---|
| no system prompt | **two runs, both clean: 40/40 numbered full names** |
| system prompt in an emotional register, plus a control vector at scale 3.0 on a single layer | prose instead of names, the numbering restarting mid-list, and the same small pool of words recombined rather than 40 distinct entries |

## The names that came back

Run 1 (43s, `finish=stop`, 680 chars):

```
 1 Aiden Ford           11 Julian Thompson     21 Caleb Brooks       31 Elara Keenan
 2 Lila Pierce          12 Nila Gray           22 Niall McCann       32 Soren Wray
 3 Ethan Stone          13 Cian Rourke         23 Zephyr Mckay       33 Sia Vartan
 4 Maya Black           14 Zara Kahan          24 Rachel Risher      34 Iver Goff
 5 Jackson Reed         15 Quinn Flynn         25 Riven Blackwood    35 Zephyre Fagan
 6 Katarina Harris      16 Leila Rizzo         26 Kaida Sutherland   36 Mairi Mckinn
 7 Bryce Taylor         17 Seth Moreno         27 Keir Hollow        37 Caelian Cason
 8 Aurora Foster        18 Elinor Tinsley      28 Maelara Naylor     38 Rhyannon Wynn
 9 Nicholas White       19 James Riley         29 Thane Mcintyre     39 Thalia Wills
10 Violet Slaughter     20 Phoebe Larkin       30 Kymara Vargas      40 Kedan Oconnell
```

Run 2 (31s, `finish=stop`, 679 chars):

```
 1 Emilia Fothergill    11 Sofia Stone         21 Kelsey Martin      31 Cameron Sutherland
 2 Harrison Thompson    12 Michael Riley       22 Alexander Grey     32 Victoria Worsley
 3 Cora Waverly         13 Gabriella Kinsley   23 Emily Blackwood    33 Alexis Gault
 4 Julian Reed          14 Daniel Hall         24 Andrew Watts       34 Constantine Brown
 5 Rachel Sawyer        15 Lila Fournier       25 Zoe Paine          35 Katarina O'Hara
 6 Ethan Flynn          16 Christopher Taylor  26 Brandon Smith      36 Riven Hallow
 7 Ava Worsley          17 Harper Hines        27 Hope Eichorn       37 Zara LaGrange
 8 Lucas Pierce         18 Julia Pierce        28 Celine Sorel       38 Bryce Lathrop
 9 Abigail Mears        19 Noah Wallace        29 Gabriel DeLange    39 Elyse Mckay
10 James Harwood        20 Elizabeth Rourke    30 Sara Tavares       40 Zephyr Goh
```

## Observations

**Removing the system prompt fixed it, and that is not the intuition.** The failing condition
also had a control vector applied at scale 3.0 — a weight-space injection, which you would
expect to be what breaks a model rather than a sentence of prompt. In practice the prompt and
the vector pull the same direction: put the model in an emotional register through the system
prompt, let the vector supply more of the same, and together they dominate a task that has no
pushback of its own.

**The vector still leaks through, visibly.** Run 1 contains `Violet Slaughter` and
`Riven Blackwood`; run 2 contains `Riven Hallow` and `Zephyr Goh`. Ordinary lists with register
intrusions scattered through them — what an unwanted steering direction looks like when it does
not quite take over.

**A working run is still visibly a generated list.** `Zephyr Mckay`, `Zephyre Fagan`,
`Maelara Naylor`, `Mairi Mckinn` — invented spellings, and the same handful of fantasy names
reappearing across runs. Nothing here is a curated list of real people.

## Caveats

* Small samples: two clean runs, four failed ones. Suggestive, not proof of a mechanism.
* One model, one vector, one scale, one task shape.
* Whether the failing condition recovers at a lower vector scale was not tested.

## A scoring trap worth recording

The first version of the harness counted any two capitalised words as a name, and scored a loop
of fantasy-slop word pairs as **39/40 usable**. The raw reply showed roughly ten first names
crossed with ten surnames, with the counter restarting partway down. The scorer agreed with a
wrong answer, confidently.

Two lessons:

* Never trust a count from a scorer you have not checked against the raw text. The raw text was
  printed right beside the count and it still nearly went unnoticed.
* When grading generative output, grade the *structure* as well as the content: repeated first
  names, repeated surnames, a broken counter. A model collapsed into a loop produces
  plausible-looking lines, and the giveaway is the reuse.
