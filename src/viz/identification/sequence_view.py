"""Sequence view: the proteoform's sequence with its modifications and the
fragment ions that cover each bond, the matched fragments listed below. For a
run that was not identified, a sequence the user sets is matched against the
selected spectrum. Picking a residue, mass or fragment is shared with the other
components.

Insight component: ``ProteinSequenceView``. Columns: ``MonoMass`` (the
spectrum's masses), ``PrecursorMass``, ``fragmentation`` (the spectrum's
fragmentation method), and for identifications ``proteoform_index`` and
``scan_idx``, else ``index`` (the spectrum).
"""

from __future__ import annotations

COMPONENT = "ProteinSequenceView"

OPTIONS = dict(mass_column="MonoMass", precursor_mass_column="PrecursorMass")


def _shared(mass, residue, annotation_title, svg_filename, spectrum_key):
    return dict(
        mass_identifier=mass, aa_identifier=residue, fragmentation_column="fragmentation",
        **OPTIONS, annotation_title=annotation_title, svg_filename=svg_filename,
        **({"spectrum_key_column": spectrum_key} if spectrum_key else {}),
    )


def identified_settings(settings=None, prsm: str = "protein", mass: str = "mass", residue: str = "aa",
                        fragment: str = "fragment", annotation_title: str = "Fragment annotation",
                        svg_filename: str = "sequence", spectrum_key: str | None = "scan_idx",
                        **overrides) -> dict:
    """Constructor arguments of the view of the PrSM in ``prsm``; ``settings``
    holds the search's tolerances and ion types; ``spectrum_key`` names the
    column whose spectrum the matched fragments are marked on (None when the
    installed Insight cannot mark them)."""
    return dict(
        filters={prsm: "proteoform_index"}, fragment_identifier=fragment,
        settings=settings, entry_title="Proteoform", observed_mass_label="Observed proteoform mass",
        **_shared(mass, residue, annotation_title, svg_filename, spectrum_key),
    ) | overrides


def sequence_settings(sequence, spectrum: str = "scan", mass: str = "mass", residue: str = "aa",
                      sequence_selection: str = "sequence", annotation_title: str = "Fragment annotation",
                      svg_filename: str = "sequence", spectrum_key: str | None = "index",
                      **overrides) -> dict:
    """Constructor arguments of the view of a sequence the user set, matched
    against the spectrum in ``spectrum``."""
    return dict(
        filters={spectrum: "index"}, sequence=sequence, sequence_identifier=sequence_selection,
        **_shared(mass, residue, annotation_title, svg_filename, spectrum_key),
    ) | overrides


settings = identified_settings
