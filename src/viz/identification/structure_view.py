"""Structure view: the predicted 3D structure of the picked proteoform's
protein, its residues coloured by the fragments that cover them. Picking a
residue or fragment is shared with the sequence view.

Insight component: ``ProteinStructureView``. Columns as in
``identification.sequence_view`` (identified). The caller passes the structure
with ``set_structure``.
"""

from __future__ import annotations

COMPONENT = "ProteinStructureView"


def settings(settings=None, prsm: str = "protein", residue: str = "aa", fragment: str = "fragment",
             **overrides) -> dict:
    """Constructor arguments of the structure of the PrSM in ``prsm``."""
    return dict(
        filters={prsm: "proteoform_index"}, mass_column="MonoMass",
        aa_identifier=residue, fragment_identifier=fragment, settings=settings,
        empty_message="Select a proteoform in the protein table to show its structure.",
    ) | overrides
