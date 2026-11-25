"""PrSMs: every proteoform-spectrum match of a run with its scan, protein,
characterization, matched fragments, score and q-values; a button per row opens
the whole row. A click picks the PrSM and its spectrum.

Insight component: ``Table``. Columns: ``index`` (the PrSM), ``scan_idx``,
``Scan``, ``accession``, ``description``, ``Proforma``, ``residues``,
``length``, ``Characterization`` (Characterized, Partial or Ambiguous),
``RetentionTime``, ``precursor_mz``, ``precursor_charge``, ``precursor_mass``,
``ProteoformMass``, ``delta_mass``, ``MatchingFragments``, ``Coverage(%)``,
``Cleavages``, ``ModCount``, ``LocalizedMods``, ``modification_sites``,
``TagCount``, ``Score``, ``ProteoformLevelQvalue``, ``ProteinLevelQvalue``,
``is_best`` (the best PrSM of its spectrum).
"""

from __future__ import annotations

from src.viz.columns import BROWSE, DASH_FOR_MISSING, HIDDEN, MASS, fixed
from src.viz.columns import threshold_filters
from src.viz.identification._hierarchy import ON_SELECT

COMPONENT = "Table"

# Essential columns visible, the rest in the column chooser and the row overview
COLUMNS = [
    {'title': 'Scan No.', 'field': 'Scan', 'sorter': 'number',
     'headerTooltip': 'The identifier of the mass spectrometry scan associated with the identified proteoform.'},
    {'title': 'Accession', 'field': 'accession',
     'headerTooltip': 'The unique identifier for the protein in the reference database.'},
    {'title': 'Description', 'field': 'description', **HIDDEN},
    {'title': 'Proteoform', 'field': 'Proforma', 'tooltip': True, **HIDDEN,
     'headerTooltip': 'The proteoform in ProForma notation.'},
    {'title': 'Residues', 'field': 'residues', **HIDDEN,
     'headerTooltip': 'First and last residue of the proteoform in the protein and the protein length; "?" for a terminus that was not determined.'},
    {'title': 'Length', 'field': 'length', 'sorter': 'number', **HIDDEN,
     'headerTooltip': 'The total number of amino acids in the matched protein.'},
    {'title': 'Characterization', 'field': 'Characterization', 'sorter': 'string',
     'formatter': 'badge', 'formatterParams': {'colorMap': {
         'Characterized': '#2E7D32', 'Partial': '#F9A825', 'Ambiguous': '#C62828',
     }},
     'headerTooltip': (
         'How completely the fragments pin down the proteoform (in the spirit of '
         "ProSight's C-score colors). Characterized: both termini determined, every "
         'mass shift localized to one residue and at least 25% of the bonds explained '
         'by fragments. Ambiguous: less than 10% of the bonds explained. Partial: '
         'anything in between.'
     )},
    {'title': 'Retention time (s)', 'field': 'RetentionTime', 'sorter': 'number', **fixed(), **HIDDEN},
    {'title': 'Precursor m/z', 'field': 'precursor_mz', 'sorter': 'number', **HIDDEN, **MASS},
    {'title': 'Precursor charge', 'field': 'precursor_charge', 'sorter': 'number', **HIDDEN},
    {'title': 'Precursor mass', 'field': 'precursor_mass', 'sorter': 'number', **HIDDEN, **MASS,
     'headerTooltip': 'Monoisotopic precursor mass in Daltons.'},
    {'title': 'Mass', 'field': 'ProteoformMass', 'sorter': 'number', **DASH_FOR_MISSING, **HIDDEN,
     'headerTooltip': 'The calculated mass of the proteoform in Daltons.'},
    {'title': 'Δ mass', 'field': 'delta_mass', 'sorter': 'number', **HIDDEN, **MASS,
     'headerTooltip': 'Precursor mass minus proteoform mass, in Daltons.'},
    {'title': 'No. of Matched Fragments', 'field': 'MatchingFragments', 'sorter': 'number',
     'headerTooltip': 'The number of fragment ions that match the protein sequence.'},
    {'title': 'Coverage (%)', 'field': 'Coverage(%)', 'sorter': 'number', **HIDDEN,
     'headerTooltip': 'Residues of the protein covered by the proteoform, in %.'},
    {'title': 'Cleavages (%)', 'field': 'Cleavages', 'sorter': 'number', **HIDDEN,
     'headerTooltip': 'Bonds of the proteoform explained by matched terminal fragments, in %.'},
    {'title': 'No. of Modifications', 'field': 'ModCount', 'sorter': 'number', **HIDDEN,
     'headerTooltip': 'The number of modifications identified in the protein.'},
    {'title': 'Localized Mods', 'field': 'LocalizedMods', 'sorter': 'string', **HIDDEN,
     'headerTooltip': 'Modifications (mass shifts) localized to a single residue, of all modifications.'},
    {'title': 'Modification sites', 'field': 'modification_sites', 'tooltip': True, **HIDDEN,
     'headerTooltip': 'Mass shift and residue of each modification, or the residue range of one that was not localized.'},
    {'title': 'No. of Tags', 'field': 'TagCount', 'sorter': 'number', **HIDDEN,
     'headerTooltip': 'The number of sequence tags associated with the proteoform match.'},
    {'title': 'Score', 'field': 'Score', 'sorter': 'number',
     'headerTooltip': 'A score indicating the confidence of the protein match (higher is better).'},
    {'title': 'Q-Value (Proteoform Level)', 'field': 'ProteoformLevelQvalue', 'sorter': 'number',
     **DASH_FOR_MISSING,
     'headerTooltip': 'The confidence value of the protein match at the proteoform level.'},
    {'title': 'Q-Value (Protein Level)', 'field': 'ProteinLevelQvalue', 'sorter': 'number',
     **DASH_FOR_MISSING, **HIDDEN,
     'headerTooltip': 'The confidence value of the protein match at the protein level: '
                      'the estimated share of false proteins among proteins scoring at least as well.'},
]


def settings(title: str = "Protein Table", with_qvalues: bool = True, table_cls=None,
             prsm: str = "protein", spectra=("pscan", "scan"), protein_set: str | None = None,
             **overrides) -> dict:
    """Constructor arguments; a click writes the PrSM to ``prsm`` and its
    spectrum to each of ``spectra``; a box of rows writes their proteins to
    ``protein_set``."""
    extra = threshold_filters(table_cls, ("ProteoformLevelQvalue", "ProteinLevelQvalue")) \
        if with_qvalues and table_cls is not None else {}
    return dict(
        column_definitions=COLUMNS, title=title, **extra,
        row_overview="Scan {Scan}: {accession}",
        index_field="index", go_to_fields=["Scan", "accession"],
        initial_sort=[{"column": "Score", "dir": "desc"}],
        toggle_filters=[{"label": "Best per spectrum", "column": "is_best", "group_column": "Scan"}],
        interactivity={prsm: "index", **{s: "scan_idx" for s in spectra}},
        **({"multi_select": {protein_set: "accession"}} if protein_set else {}),
        on_select=ON_SELECT, **BROWSE,
    ) | overrides
