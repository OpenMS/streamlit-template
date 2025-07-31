"""
Peptide M/Z Calculator Backend

This module provides backend functions for peptide mass spectrometry calculations
using pyOpenMS AASequence.fromString() directly with minimal parsing overhead.
"""

import re
from typing import Dict, Any, Tuple, Optional, List, Union
import pyopenms as poms


def calculate_peptide_mz(sequence: str, charge_state: int) -> Dict[str, Any]:
    """Calculate m/z ratio for a peptide using AASequence.fromString() directly.
    
    Args:
        sequence: Peptide sequence string (AASequence.fromString() compatible)
        charge_state: Charge state for m/z calculation
        
    Returns:
        Dictionary with calculation results
        
    Raises:
        ValueError: If sequence is invalid or charge state is invalid
    """
    sequence = sequence.strip()
    if not sequence:
        raise ValueError("Peptide sequence cannot be empty")
    
    if charge_state < 1:
        raise ValueError("Charge state must be a positive integer")
    
    try:
        # Use AASequence.fromString() directly - it supports many formats natively
        aa_sequence = poms.AASequence.fromString(sequence)
    except Exception as e:
        raise ValueError(f"Invalid sequence format: {str(e)}")
    
    # Calculate properties
    mz_ratio = aa_sequence.getMZ(charge_state)
    mono_weight = aa_sequence.getMonoWeight()
    formula = aa_sequence.getFormula()
    
    # Get the standardized string representation
    standardized_sequence = aa_sequence.toString()
    
    # Extract clean amino acid sequence for composition
    unmodified_aa_sequence = aa_sequence.toUnmodifiedString()

    # Calculate amino acid composition
    aa_composition = {}
    for aa in unmodified_aa_sequence:
        aa_composition[aa] = aa_composition.get(aa, 0) + 1
    
    return {
        "mz_ratio": mz_ratio,
        "monoisotopic_mass": mono_weight,
        "molecular_formula": formula.toString(),
        "original_sequence": unmodified_aa_sequence,
        "modified_sequence": standardized_sequence,
        "charge_state": charge_state,
        "sequence_length": len(unmodified_aa_sequence),
        "aa_composition": aa_composition,
        "success": True,
    }

def calculate_peptide_mz_range(
    sequence: str, 
    charge_range: Tuple[int, int]
) -> Dict[str, Any]:
    """Calculate m/z ratios for multiple charge states.
    
    Args:
        sequence: Peptide sequence string
        charge_range: Tuple of (min_charge, max_charge) inclusive
        
    Returns:
        Dictionary containing results for all charge states
    """
    min_charge, max_charge = charge_range
    charge_results = {}
    
    # Calculate for each charge state
    for charge in range(min_charge, max_charge + 1):
        result = calculate_peptide_mz(sequence, charge)
        charge_results[charge] = result
    
    # Use first result as base and add charge_results
    base_result = charge_results[min_charge]
    return {
        **base_result,
        "charge_results": charge_results,
        "charge_range": charge_range,
    }


def validate_sequence(sequence: str) -> Tuple[bool, str]:
    """Validate if sequence can be parsed by AASequence.fromString().
    
    Args:
        sequence: Sequence string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not sequence.strip():
        return False, "Sequence cannot be empty"
        
    try:
        poms.AASequence.fromString(sequence.strip())
        return True, ""
    except Exception as e:
        return False, f"Invalid sequence format: {str(e)}"
