# Design rounds judge one panel at a time, then the assembled page once

> **Refined, not superseded.** The count below was retired at tick 007: a round
> offers *up to* three suggestions, a ceiling rather than a quota. The per-panel
> decision this ADR records is unchanged. See "Refinement" below.

A design round shows the user one panel, offers three suggestions -- one on data,
one on layout, one on behaviour -- plus a free field and an exit, applies the
choice and re-renders. Panels are built and judged in sequence. Only when every
panel has been approved does the framework run the usability gate and open a final
round on the page as a whole, with the gate's findings and the screenshot feeding
that round's suggestions.

The objection to per-panel rounds is real: a layout cannot be judged from one
panel, and a user asked to improve panel one has not yet seen panels two and
three. Judging the whole assembled page every round avoids that entirely.

Per-panel was chosen anyway, because the alternative asks the user to review a
dashboard the framework designed alone and then argue with it. Building each panel
with its author present is what makes the result theirs, and it matches how the
dashboard skill already builds -- one panel, reload, look, adjust -- so the
user-facing rhythm and the debugging rhythm are the same rhythm.

The gate-fed final round is what repairs the objection. Layout, the summary strip,
colour consistency across panels, and what the page shows before anything is
selected are exactly the properties that only exist once everything is on screen,
and they are also what the gate and the screenshot can speak to.

## Refinement

The round as described here offers three suggestions. Tick 007 of the
self-improvement loop refined that to **up to three -- a ceiling, not a quota**:
every suggestion must point at something visible, and a page the gate passes with
no design notes honestly receives none. The per-panel structure this ADR decided
is unchanged; only the count is.

## Consequences

A dashboard costs at least N+1 rounds for N panels, and more where a user iterates
on one panel. This is the framework's longest interaction by some margin and is
what the tutorial's time budget is mostly spent on.

The first panel has nothing to link to, so its behaviour-axis suggestion is
necessarily a promise about panels that do not exist yet. The suggestion must name
the panel it is preparing for, or it reads as arbitrary.

The usability gate acquires a second role. It was a pass/fail check run once at the
end; it now also generates design input mid-conversation, so its warnings need to
be phrased for a user rather than only for a log.
