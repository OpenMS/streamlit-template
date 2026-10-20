"""
pyOpenMS toolbox: m/z calculator, in silico digest, isotope patterns and
fragment ions. Each route calls the same Streamlit-free functions as the
Streamlit page it mirrors.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/tools")


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, np.ndarray):
        return [_clean(x) for x in v.tolist()]
    if isinstance(v, pd.DataFrame):
        return {"columns": [str(c) for c in v.columns], "rows": [[_clean(x) for x in r] for r in v.itertuples(index=False, name=None)]}
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


class MzRequest(BaseModel):
    sequence: str
    min_charge: int = 1
    max_charge: int = 4


@router.post("/mz")
def mz(body: MzRequest) -> dict:
    from src.peptide_mz_calculator import calculate_peptide_mz_range, validate_sequence

    ok, err = validate_sequence(body.sequence)
    if not ok:
        raise HTTPException(400, err)
    if body.min_charge < 1 or body.max_charge < body.min_charge:
        raise HTTPException(400, "Charge range must be positive and ascending")
    try:
        return _clean(calculate_peptide_mz_range(body.sequence, (body.min_charge, body.max_charge)))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/enzymes")
def enzymes() -> list[str]:
    from utils.digest import get_available_enzymes

    return get_available_enzymes()


class DigestRequest(BaseModel):
    fasta: str
    enzyme: str = "Trypsin"
    missed_cleavages: int = 2
    max_charges: int = 4
    min_length: int = 6
    max_length: int = 50


@router.post("/digest")
def digest(body: DigestRequest) -> dict:
    from utils.digest import (
        calculate_protein_coverage,
        filter_peptides_by_length,
        get_digest_statistics,
        perform_digest,
    )
    from utils.fasta import validate_fasta_input

    ok, err, sequences = validate_fasta_input(body.fasta)
    if not ok:
        raise HTTPException(400, err or "Invalid FASTA")
    if not sequences:
        raise HTTPException(400, "No valid sequences found in the input.")
    df = perform_digest(sequences, body.enzyme, body.missed_cleavages, body.max_charges)
    df = filter_peptides_by_length(df, body.min_length, body.max_length)
    stats = get_digest_statistics(df) if not df.empty else {}
    coverage = calculate_protein_coverage(df, sequences) if not df.empty else {}
    return _clean({"n_sequences": len(sequences), "stats": stats, "table": df, "coverage": coverage})


class IsotopeRequest(BaseModel):
    method: str  # formula | peptide | oligonucleotide | mass
    value: str
    fine: bool = False


@router.post("/isotope")
def isotope(body: IsotopeRequest) -> dict:
    from src import isotope_pattern as ip

    if body.method == "formula":
        r = ip.generate_isotope_pattern_from_formula(body.value, body.fine)
    elif body.method == "peptide":
        r = ip.generate_isotope_pattern_from_sequence(body.value, body.fine)
    elif body.method == "oligonucleotide":
        r = ip.generate_isotope_pattern_from_oligonucleotide(body.value, body.fine)
    elif body.method == "mass":
        try:
            mass = float(body.value)
        except ValueError:
            raise HTTPException(400, "Mass must be a number")
        r = ip.generate_isotope_pattern_from_mass(mass)
    else:
        raise HTTPException(400, f"Unknown input method {body.method!r}")
    if not r.get("success"):
        raise HTTPException(400, r.get("error", "Could not compute the pattern"))
    return _clean(r)


class FragmentRequest(BaseModel):
    sequence: str
    ion_types: list[str] = ["b", "y"]
    charges: list[int] = [1]


@router.get("/ion-types")
def ion_types() -> dict:
    from src.fragmentation import ION_TYPES

    return ION_TYPES


@router.post("/fragment")
def fragment(body: FragmentRequest) -> dict:
    from src.fragmentation import generate_theoretical_spectrum

    r = generate_theoretical_spectrum(body.sequence, body.ion_types, body.charges)
    if not r.get("success"):
        raise HTTPException(400, r.get("error", "Could not generate the spectrum"))
    return _clean(r)
