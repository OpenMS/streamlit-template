# Guidance is judged by blind pairwise comparison, not an absolute rubric

The self-improvement loop scores how well a skill guides its user, not only what
it produces. That score is obtained by having a judge model read two persona
transcripts of the same task -- one from before a skill edit, one from after,
neither labelled -- and say which guided the user better, and why. Verdicts are
counted across personas; a majority preference for the edited skill is a keep.

An absolute rubric was the obvious alternative and is richer: it says *how* good a
transcript is, not merely which of two is better, and it produces a number that
plots over time. It was rejected because it varies by roughly +/-0.4 on a 5-point
scale between reruns of an unchanged skill, and the loop's ratchet keeps any tick
whose score rose. A metric whose noise exceeds the size of a typical skill edit
will ratchet in edits that changed nothing, and the loop cannot tell that this is
happening from the inside.

Preference between two concrete artifacts is far more stable than a score against
an imagined ideal, and the judge's stated reason is directly actionable -- it
names the next tick's edit, which a number never does.

## Consequences

Guidance has no absolute scale, so there is no guidance figure to plot across
ticks and no way to compare a transcript against one from a distant tick without
re-judging the pair. The history in `eval/scores.jsonl` records verdicts and
reasons rather than a guidance score.

Every tick must retain the previous transcript for each persona, which makes the
persona transcripts a stored artifact rather than a byproduct, and doubles the
transcript generation cost of a tick that re-runs a persona from scratch.

The artifact dimensions stay scored numerically and keep their weights. They are
saturated at 1.00 across the current corpus and no longer discriminate between
skill edits, but they remain the regression guard: a tick that drops one has
broken something that worked, and that has already happened once.
