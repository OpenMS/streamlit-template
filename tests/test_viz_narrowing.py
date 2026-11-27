"""Library: the line above the narrowed peptide and PSM tables: place, stepping and Show all."""
import pandas as pd

from src.viz.identification import narrowing


class State:
    def __init__(self, **selections):
        self.selections = dict(selections)

    def get_selection(self, identifier):
        return self.selections.get(identifier)

    def set_selection(self, identifier, value):
        self.selections[identifier] = value

    def clear_selection(self, identifier):
        self.selections.pop(identifier, None)


PROTEINS = pd.DataFrame({"accession": ["P1", "P2", "P3"]})
PEPTIDES = pd.DataFrame({"accession": ["P1", "P1", "P2", "P1"], "peptide": ["AAK", "CCR", "DDK", "AAK"]})


def test_place_counts_from_one_and_misses_unknown_values():
    items = narrowing.proteins_of(PROTEINS)
    assert narrowing.place(items, "P2") == (2, 3)
    assert narrowing.place(items, "P9") is None
    assert narrowing.place(items, None) is None


def test_neighbour_wraps_around_the_list():
    items = ["P1", "P2", "P3"]
    assert narrowing.neighbour(items, "P3", 1) == "P1"
    assert narrowing.neighbour(items, "P1", -1) == "P3"
    assert narrowing.neighbour(items, "P2", 1) == "P3"
    assert narrowing.neighbour(items, "P9", 1) is None


def test_peptides_of_a_protein_are_listed_once_in_table_order():
    assert narrowing.peptides_of(PEPTIDES, "P1") == ["AAK", "CCR"]
    assert narrowing.peptides_of(PEPTIDES, None) == []
    assert narrowing.peptides_of(PEPTIDES.drop(columns="peptide"), "P1") == []


def test_stepping_to_another_protein_forgets_its_peptide_and_psm():
    state = State(protein="P1", peptide="AAK", psm="run:3")
    narrowing._pick(state, "protein", "P2")
    assert state.selections == {"protein": "P2"}


def test_show_all_peptides_keeps_the_protein():
    state = State(protein="P1", peptide="AAK", psm="run:3")
    narrowing._pick(state, "peptide", None)
    assert state.selections == {"protein": "P1"}
