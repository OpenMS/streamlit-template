"""Peptide sequence: the sequence of the picked PSM with the b and y ions (and
their neutral losses) matched in its spectrum within the fragment tolerance;
the annotated spectrum and the fragment table follow it.

Insight component: ``SequenceView``. Sequence columns: ``sequence_id``,
``sequence``, ``precursor_charge``, ``file_index``, ``scan_id``; peak columns
as ``SequenceView`` reads them (``peak_id``, ``mass``, ``intensity``, ...).
``sequence_rows`` maps a PSM table (``id_idx``, ``charge``) onto them.
"""

from __future__ import annotations

COMPONENT = "SequenceView"

SEQUENCE_COLUMNS = ["id_idx", "sequence", "charge", "file_index", "scan_id"]


def sequence_rows(psms):
    """The sequence data of a polars frame of PSMs."""
    return psms.select(SEQUENCE_COLUMNS).rename({"id_idx": "sequence_id", "charge": "precursor_charge"})


def settings(tolerance: float, ppm: bool, ion_types=("b", "y"), psm: str = "identification", file: str = "file",
             spectrum: str = "spectrum", peak: str = "peak", **overrides) -> dict:
    return dict(
        filters={psm: "sequence_id", file: "file_index", spectrum: "scan_id"},
        interactivity={peak: "peak_id"},
        deconvolved=False,
        annotation_config={"ion_types": list(ion_types), "neutral_losses": True,
                           "tolerance": tolerance, "tolerance_ppm": ppm},
    ) | overrides
