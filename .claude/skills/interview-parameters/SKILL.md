---
name: interview-parameters
description: Use when deciding which parameters of a captured notebook or python tool belong on an app's configuration page, when a DEFAULTS list needs curating, or when notebook constants must be triaged into user-facing settings and fixed values.
---

# Interview parameters

Decide which values the app's user gets to change: from **where in the notebook
each value came from**, and from measurement wherever one is about to be
*hidden*. Runs as **one batch review** after capture, never as a stream of
questions mid-extraction.

## The rule

**A parameter is never recommended `HARDCODE` on the evidence of a one-at-a-time
sweep.**

Parameters interact. A sweep that moves nothing may be measuring a parameter
another has swamped, and reporting that as "no effect" hardcodes the setting the
user most needs. Re-probe with each other numeric parameter driven to its neutral
value first.

Masking is a **comparison** between the masked and unmasked effect, never a test
for zero — an inert parameter still registers a few percent of noise.

*Worked:* a notebook passes both an absolute and a relative tolerance into a
closeness test of the form `|a-b| <= atol + rtol*|b|`. The relative one is left at
a value that alone opens a window orders of magnitude wider than the absolute one
ever reaches, so sweeping the absolute across its entire usable range moves the
result by a fraction of a percent. A naive probe reports that as inert and
recommends hardcoding the most important parameter in the notebook; with the
relative one neutralised, the same sweep moves the result completely. Correct
output: *keep both, and say they interact*.

## Two sections, in this order

### 1. Shortcuts and suspicious constants

Everything capture collected — truncations, intent comments, discarded results,
constants failing a domain sanity check. Each gets **drop / promote to parameter /
keep as written**, arriving as a one-word decision with the recommendation already
made, the user's own line quoted, and the runtime it costs at full scale in the
parenthetical. `capture-notebook-workflow` has the exact shape.

First, because **the probe in section 2 is invalid until this resolves**: a
truncation caps the output, so every sweep beneath it measures the cap.

Represent a resolved truncation as a parameter whose default reproduces the
notebook, then change the default — equivalence stays provable and the decision is
one line in `DEFAULTS`.

### 2. Config parameters

**Every row arrives already decided.** The user's work is disagreeing, not
choosing from nothing — so what they are asked is whether the decision stands,
not what they would like. Not a stream of questions, and not a wait.

Rank by provenance — named constants and default arguments > `setValue` arguments
> inline literals > untouched algorithm parameters — and pre-tick what a mass
spectrometrist would expose: tolerances, score and intensity thresholds, charge
and length ranges, the enzyme where the sample varies.

Capture's harvested sweeps arrive as **prior evidence** and move rows up that
ranking: a parameter its author swept is one they thought mattered enough to
teach, so pre-tick it. And **a flat sweep is a masking candidate** before a single
probe runs — never read one as *this does nothing*. What to say instead is below.

**Ask once, whole.** The list is already decided; what the user is being asked
is whether that decision stands — and most of the time it does. So the first
question is the only one most runs need. Show the split, then offer three ways
out of it:

```
I'd expose these on the config page, and fix the rest at your notebook's values:

  exposed   precursor tolerance · fragment tolerance · enzyme ·
            missed cleavages · peptide length
  fixed     max. fragment charge · b/y ions · limit on spectra searched

The two tolerances interact — if either is exposed, both are.
```
> *Take it as it stands* · *Let me change some* · *Measure what each one
> actually moves first (~90 s)*

**Those three are options the user selects — not a line they read.** A list of
rows with `[x]` beside them is a form drawn into a transcript: nothing can be
ticked, so disagreeing with one row means retyping all of them — right rows and a
right recommendation, with nothing to act on.

**Only *let me change some* opens the list**, and then in groups, not rows —
tolerances, digestion, ion generation, limits. Nine rows do not fit one screen of
options; four groups do, and someone who wants one row different almost always
wants its neighbours left alone. A group they open resolves row by row.

Say which rows came from the notebook's own sweeps; the person who wrote that
cell should recognise their own numbers.

**The probe does not run by default.** It is the longest wait in the framework —
O(n²), and the skill's own arithmetic puts 43 parameters at 6.2 hours — spent to
produce recommendations that provenance already gives correctly for every verdict
except one. Offer it; run it when asked, or when a `HARDCODE` is on the table.

**Offer it in the user's words, not in this skill's.** *Masking*, *the probe*,
*the sweep*, `HARDCODE` — this page is full of them because they are how the work
is thought about, and every one of them is invisible to a mass spectrometrist.
`masking` is on the forbidden list in `notebook-to-webapp` and still reaches
users, because the sentence gets written from **this** page.

| here | on screen |
|---|---|
| run the probe | measure what each setting actually changes |
| the masking re-probe | check whether one setting is swamping another |
| a flat sweep | changing it barely moves the result |
| `HARDCODE` | fix it at your notebook's value |
| the masking above | what I described — *"the wide window above"* |

**The last row is the one that gets missed.** The first three are verbs, and a
verb is easy to translate because you are about to describe an action anyway. The
leak that survived was a **label**: having explained the effect properly — *"adds
10% of the peptide mass, a ~150 Da window, so the Da tolerance never gets to
decide anything"* — the next bullet referred back to it as *"the masking above"*.

Refer back by what it **does**, never by what this skill calls it. If a phrase
would need the reader to have read this page, it is the wrong phrase, and that is
true of a one-word back-reference just as much as of an instruction.

## An unmeasured parameter may be exposed, never hidden

This is what makes the probe optional without giving up what it was for.

Exposing a parameter that turns out not to matter costs one row on a config page.
Hiding one that does matter is the failure this skill exists to prevent, and the
user cannot recover from it — they cannot see what was taken away.

| verdict | needs a measurement first |
|---|---|
| KEEP, ADVANCED | no — provenance and domain sense are sufficient |
| DASHBOARD CONTROL | no — a display constant is one by inspection |
| **HARDCODE** | **yes**, and the masking re-probe with it |

The masked case above is the proof this is the *safer* default and not the looser
one. The naive probe measured a fraction of a percent on the absolute tolerance
and recommended hardcoding the most important parameter in the notebook. Provenance ranks that parameter first — it is
a default argument to the matching call — and exposes it having measured nothing.
The probe's unique power is only ever the negative verdict, and the negative
verdict is the only one that needs it.

## Explaining a flat sweep

A flat sweep is where the user is most likely to be handed a question they cannot
answer. *"The sweep is flat across a 100-fold range. How should I treat it?"* asks
them to know this skill's central finding in order to reply.

Say what they wrote, what it looks like, what it actually is, and what you would
do:

```
Your <exercise> varies the precursor tolerance across <range> and the number of
candidate peptides barely moves — <before> to <after>.

That usually means a setting does nothing and can be fixed. Here it means the
opposite: the *relative* tolerance set <k> cells earlier already opens a window
far wider than that, so the tolerance being varied never gets to decide anything.

I'd keep both and show them together on the config page.
```

## When measurement is asked for, or a HARDCODE is on the table

Probe the shortlist, never the full surface:

```bash
python probe.py --script src/python-tools/<name>.py \
    --inputs <input files> --budget-key <limiting param> --budget 30
```

It sweeps each parameter across `min`/default/`max` (booleans both ways, options
exhaustively), reduces `OUTPUTS` to metrics, and re-probes anything below the
materiality threshold for masking. Give it `--budget-key` or a probe on real data
takes minutes per sweep.

**The budget key must limit work before the expensive step, not after it.** A
resolved truncation is the obvious candidate and often the wrong one: `max-features`
on a tool whose cost is feature detection buys no time at all *and* pins
`features.rows`, so every effect size measures the cap rather than the parameter —
the same failure as probing before shortcuts resolve, wearing a different hat, and
it looks like the right answer. When nothing genuinely limits work early, budget by
shrinking the **input** instead: crop the mzML to a short RT window.

`probe.py` verifies this rather than trusting the choice — it times a run at the
budget and at a quarter of it, and warns loudly if the smaller one is not
meaningfully faster.

**A sweep that lost points has no verdict.** When a run fails, its point is
dropped from the effect calculation, so the effect is measured over fewer values
and reads lower than the truth — again the direction that produces HARDCODE.
`probe.py` reports such a parameter as `INCOMPLETE` rather than giving it a
recommendation. The usual cause is a numeric `DEFAULTS` entry with no declared
`min`/`max`, so the sweep invents bounds and probes a value the tool rejects; fix
the declaration and re-probe rather than accepting the reading.

**Say what it will cost before starting, and never leave the user watching
nothing.** This is the longest wait in the framework. `probe.py` times its
baseline, prints an estimate, names each parameter as it starts, and narrates the
masking re-probe. Relay the estimate; if it is long, say what `--budget` buys. A
user who asks "what is it doing?" has already been failed.

## Resolving each row

| effect | recommendation |
|---|---|
| masked by another parameter | **KEEP**, and keep the masking parameter too |
| large | **KEEP**, on the config page |
| small but real | **ADVANCED** (`"advanced": True`) |
| none, and not masked | **HARDCODE** (omit from `DEFAULTS`) |
| display-time only | **DASHBOARD CONTROL**, hand to the dashboard stage |

Propose a widget type with every kept parameter, and give an **explicit**
`widget_type` to anything a preset should drive — auto-typed numeric, selectbox
and multiselect widgets double-prefix their session key, so presets silently fail
on them.

## When the user says to skip it

*"They look fine, just use the notebook's values"* is a waiver of something they
have not been shown — and section 1 is the half they cannot guess at: a
`head(5)`, a tolerance that is a defect, a constant that is really a selection.
**Show the batch, then let them clear it in one word.** Accepting every
recommendation at once is theirs to do; skipping the presentation is not, because
the rows they would be accepting are the ones they have not seen.

This is where *never ask for what you can determine* stops. That a constant is
**suspicious** is determinable, and saying so costs the user nothing. Whether it
is a setting, a shortcut, or a defect is theirs. A reader under this pressure
collapsed the batch to "one pass, no interview" and cited the determinable rule
to justify it.

`mode=auto` is the sanctioned way to take every recommendation without blocking,
and it still emits the batch to the transcript. A human-facing run always shows it.

## Every effect size carries the scope it was measured under

A masking verdict is only valid over the parameter set it was computed on.
`probe.py` re-probes against the other entries in `DEFAULTS`, not the algorithm's
full surface — so "each other numeric parameter" means *each one in the set being
probed*.

An extracted tool exposes the parameters its author named; the library calls
underneath it expose many more. **11 named, 43 in all, 32 of them hidden.** A row reading `fragment tolerance 97.2% KEEP` was measured with
those 32 pinned at values nobody chose. Widen the set and the row stops being
evidence.
Say what the numbers were measured over every time you show them, and re-probe
rather than carrying old figures forward beside new parameters.

The probe is O(n²) — bound it first. At ~4s per run: 11 parameters is 2.3 min
of sweeps and up to 0.4 hours of masking; 43 is 8.8 min and **6.2 hours**.
`probe.py` estimates this and refuses a pass predicted over an hour without
`--allow-long`.

**Crop first; the choices below are for when a cropped pass is still refused.**
That is the ordinary outcome and it is why this table is rarely reached: measured,
3 of 3 readers priced the full pass at ~2 hours, named the refusal, cropped the
mzML to a five-minute window, and finished in fifteen. Reaching for the table
before cropping offers the user a menu of compromises they did not need. It
applies where bounding cannot get there — a parameter set large enough that even a
short window leaves hours, or an input that cannot be cropped without flooring the
metric.

When a bounded pass is still refused, put the four choices to the user rather than
picking one:

| choice | what it costs |
|---|---|
| `--params a,b,c` | probe a shortlist; the rest get **no verdict** |
| `--budget <smaller>` | faster and coarser; effect sizes carry that scope |
| `--no-masking` | minutes instead of hours, but it **cannot distinguish inert from masked** — the single error this skill exists to prevent. Say that plainly whenever you offer it |
| `--allow-long` | run it as-is; say how long |

A parameter the probe never measured has no verdict *of the kind a probe gives*:
no effect size, and never `HARDCODE`. It still carries the provenance
recommendation every row in the batch carries — that is precisely what makes the
probe optional — but the two must never be dressed as each other. Mark the
unmeasured ones, keep them out of the effect-size table rather than listing them
at 0%, and offer a probing pass. **Never show an unmeasured parameter beside
measured ones without saying which is which** — 0% next to 97.2% reads as "no
effect" when it means "never tested".

(Before the probe became opt-in this read *"they cannot be given a
recommendation"*, which was right when every row was measured and, left standing,
forbids the batch in §2 outright.)

## Never hardcode a parameter whose value depends on a visible one

A masked pair is indivisible. Freezing one half while exposing the other is
never valid, and the reason is usually a reasonable-sounding request to simplify
the config page.

Measured: hide `precursor-tolerance-abs` at the notebook's 0.1 Da, leave
`precursor-tolerance-ppm` visible, and a user asking for a tight 10 ppm — a
0.017 Da window — gets **367 spectra with candidates instead of 94**. The hidden
control is six times wider than the one requested, so it wins. **A hidden
parameter that overrides a visible one is worse than an extra visible parameter**;
the user can at least see the extra one.

When a budget cannot be met without splitting a pair, offer the three real options
rather than picking silently:

| option | what it costs |
|---|---|
| **keep both** | budget becomes N+1; usually right |
| **hardcode both**, coherently together | the control is lost, but nothing on screen lies |
| **collapse into one derived control** | most work; expose ppm and derive the absolute, as production search engines do |

Generally: **if hiding a parameter would let it contradict one that stays visible,
it cannot be hidden.** Hardcoding is safe only for a parameter nothing visible
interacts with. A user constraint is not a reason to break an invariant the probe
was run to establish — honour it if you can, price it if you cannot, and let them
decide. They asked for a simple page, not a lying one.

## Common mistakes

- Probing before shortcuts are resolved. Every sweep measures the truncation.
- Treating "past the zero threshold" as "has an effect" — **once masking has
  been ruled out**. 0.7% across a parameter's whole usable range is inert in
  practice only when nothing was swamping it; the same fraction of a percent on a
  masked parameter is this skill's flagship case. The reading alone never
  decides.
- Reporting the first masking parameter found. Check all, report the strongest.
- Silently fixing a suspicious constant. It is a finding with a
  recommendation, not a repair — changing it re-derives the golden values.
- Forgetting a parameter can produce nothing. A strict tolerance may
  legitimately identify zero rows; the tool must still emit its declared schema so
  panels render an empty state instead of a traceback.
