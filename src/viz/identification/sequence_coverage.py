"""Sequence coverage: the reference sequence in blocks, every identified
oligonucleotide or peptide drawn as a bar under the residues it covers, one
track per group (a condition, a run), stacked where matches overlap and
coloured by how often each was identified; modified residues marked. A click
picks the match.

Insight component: ``SequenceCoverage``. Columns: ``match_id`` (the match),
``start`` and ``end`` (1-based, inclusive), ``sequence``, ``count``
(identifications), ``track``, ``mod_positions`` and ``mod_labels`` (lists, the
positions in the reference) and ``reference`` (what the coverage is drawn
over, the filter).
"""

from __future__ import annotations

COMPONENT = "SequenceCoverage"


def settings(reference, reference_name: str | None = None, count_label: str = "Identifications",
             match: str = "match", reference_filter: str = "reference", track_order=None,
             **overrides) -> dict:
    """Constructor arguments over ``reference`` (a string or a list of residue
    tokens, such as ``["A", "[m1A]", "G"]``)."""
    return dict(
        reference=reference, reference_name=reference_name,
        start_column="start", end_column="end", label_column="sequence",
        count_column="count", track_column="track",
        modifications_column="mod_positions", modification_labels_column="mod_labels",
        filters={reference_filter: "reference"}, interactivity={match: "match_id"},
        count_label=count_label, track_order=list(track_order or []),
    ) | overrides


def rows(hits: list[dict], reference: str = "", track: str = ""):
    """A polars frame of ``hits`` (``sequence``, ``start``, ``end``, optional
    ``count`` and ``modifications`` as ``[{"position", "token"}]``), numbered
    from 0 in their order."""
    import polars as pl

    records = []
    for index, hit in enumerate(hits):
        mods = hit.get("modifications") or []
        records.append({
            "match_id": index, "reference": reference, "track": hit.get("track", track),
            "start": int(hit["start"]), "end": int(hit["end"]), "sequence": str(hit.get("sequence", "")),
            "count": int(hit["count"]) if hit.get("count") is not None else 1,
            "mod_positions": [int(m["position"]) for m in mods],
            "mod_labels": [str(m.get("token", m.get("label", ""))) for m in mods],
        })
    schema = {"match_id": pl.Int64, "reference": pl.Utf8, "track": pl.Utf8, "start": pl.Int64,
              "end": pl.Int64, "sequence": pl.Utf8, "count": pl.Int64,
              "mod_positions": pl.List(pl.Int64), "mod_labels": pl.List(pl.Utf8)}
    return pl.DataFrame(records, schema=schema)
