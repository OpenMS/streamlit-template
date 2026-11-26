"""Render-time options of the identification panels: the precursor marker of a
spectrum and the place of the protein, peptide and PSM tables."""

import math

from src.viz.identification import annotated_spectrum, predicted_spectrum, protein_peptides, protein_psms, protein_table


class Marked:
    def __init__(self, cache_id=None, x_markers=None):
        pass


class Plain:
    def __init__(self, cache_id=None):
        pass


class Browsed:
    def __init__(self, cache_id=None, level=None, narrowed_labels=None):
        pass


def test_the_precursor_is_marked_with_its_charge():
    assert annotated_spectrum.precursor_marker(Marked, 512.27, 2) == {
        "x_markers": [{"x": 512.27, "label": "precursor 2+"}]}
    assert annotated_spectrum.precursor_marker(Marked, "512.27", None)["x_markers"][0]["label"] == "precursor"
    assert predicted_spectrum.precursor_marker is annotated_spectrum.precursor_marker


def test_no_marker_without_an_mz_or_on_an_older_insight():
    for mz in (None, "", math.nan, 0, -1):
        assert annotated_spectrum.precursor_marker(Marked, mz, 2) == {}
    assert annotated_spectrum.precursor_marker(Plain, 512.27, 2) == {}


def test_the_tables_know_their_level_and_what_narrows_them():
    assert protein_table.display(Browsed) == {"level": 0}
    assert protein_peptides.display(Browsed) == {
        "level": 1, "narrowed_labels": {"protein": "Protein"}}
    assert protein_psms.display(Browsed, protein="prot")["narrowed_labels"] == {"prot": "Protein", "peptide": "Peptide"}
    assert protein_psms.display(Plain) == {}
