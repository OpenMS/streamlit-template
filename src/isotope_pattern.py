"""
Isotope pattern computation with pyOpenMS, shared by the Streamlit page
(content/isotope_pattern_generator.py) and the Svelte app's server.
"""

import re
from typing import Tuple, Dict, Any, Optional

import pyopenms as oms
import numpy as np

# Initialize pattern generators
coarse_pattern_generator = oms.CoarseIsotopePatternGenerator()
fine_pattern_generator = oms.FineIsotopePatternGenerator()


def validate_elemental_formula(formula_str: str) -> Tuple[bool, str, Optional[oms.EmpiricalFormula]]:
    """Validate an elemental formula string using pyOpenMS.
    
    Args:
        formula_str (str): The elemental formula string (e.g., "C100H150N26O30S1")
        
    Returns:
        Tuple[bool, str, Optional[EmpiricalFormula]]: (is_valid, error_message, formula_object)
    """
    try:
        # Clean the formula string
        formula_str = formula_str.strip()
        if not formula_str:
            return False, "Formula cannot be empty", None
            
        # Try to parse with pyOpenMS
        empirical_formula = oms.EmpiricalFormula(formula_str)
                    
        return True, "", empirical_formula
        
    except Exception as e:
        return False, f"Invalid formula format: {str(e)}", None

def validate_peptide_sequence(sequence_str: str) -> Tuple[bool, str, Optional[str]]:
    """Validate a peptide/protein sequence.
    
    Args:
        sequence_str (str): The amino acid sequence
        
    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, error_message, clean_sequence)
    """
    try:
        # Clean the sequence
        sequence_str = sequence_str.strip().upper()
        if not sequence_str:
            return False, "Sequence cannot be empty", None
            
        # Remove common formatting characters
        clean_sequence = re.sub(r'[^ACDEFGHIKLMNPQRSTVWYXU]', '', sequence_str)
        
        if not clean_sequence:
            return False, "No valid amino acid letters found", None
            
        # Validate amino acids
        valid_aa = set("ACDEFGHIKLMNPQRSTVWYXU")
        invalid_chars = [aa for aa in clean_sequence if aa not in valid_aa]
        
        if invalid_chars:
            invalid_list = ", ".join(sorted(set(invalid_chars)))
            return False, f"Invalid amino acid(s): {invalid_list}", None
            
        return True, "", clean_sequence
        
    except Exception as e:
        return False, f"Error validating sequence: {str(e)}", None

def validate_oligonucleotide_sequence(sequence_str: str) -> Tuple[bool, str, Optional[str]]:
    """Validate an oligonucleotide (RNA) sequence
    
    Args:
        sequence_str (str): The nucleotide sequence
        
    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, error_message, sequence_str)
    """
    try:
        # Clean the sequence
        sequence_str = sequence_str.strip().upper()
        if not sequence_str:
            return False, "Sequence cannot be empty", None
            
        # Remove common formatting characters (spaces, numbers, newlines)
        clean_sequence = re.sub(r'[^ACGU]', '', sequence_str)
        
        if not clean_sequence:
            return False, "No valid nucleotide letters found", None
            
        # Validate nucleotides (A, C, G, U for RNA)
        valid_nucleotides = set("ACGU")
        invalid_chars = [nt for nt in clean_sequence if nt not in valid_nucleotides]
        
        if invalid_chars:
            invalid_list = ", ".join(sorted(set(invalid_chars)))
            return False, f"Invalid nucleotide(s): {invalid_list}. Valid nucleotides: A, C, G, U", None
                    
        return True, "", sequence_str
        
    except Exception as e:
        return False, f"Error validating oligonucleotide sequence: {str(e)}", None

def generate_isotope_pattern_from_formula(formula_str: str, use_fine_generator: bool = False) -> Dict[str, Any]:
    """Generate isotope pattern from elemental formula using specified generator.
    
    Args:
        formula_str (str): The elemental formula string
        use_fine_generator (bool): Whether to use FineIsotopePatternGenerator (default: False)
        
    Returns:
        Dict[str, Any]: Results dictionary with mzs, intensities, and metadata
    """
    try:
        # Validate formula
        is_valid, error_msg, empirical_formula = validate_elemental_formula(formula_str)
        if not is_valid:
            return {"success": False, "error": error_msg}
        
        # Select generator
        generator = fine_pattern_generator if use_fine_generator else coarse_pattern_generator
        generator_name = "Fine" if use_fine_generator else "Coarse"
        
        # Generate isotope pattern
        isotope_distribution = empirical_formula.getIsotopeDistribution(generator)
        avg_weight = empirical_formula.getAverageWeight()
        distribution = isotope_distribution.getContainer()
        
        # Extract data
        mzs = np.array([p.getMZ() for p in distribution])
        intensities = np.array([p.getIntensity() for p in distribution])
        
        # Calculate masses
        monoisotopic_mass = empirical_formula.getMonoWeight()
        average_mass = empirical_formula.getAverageWeight()
        
        return {
            "success": True,
            "mzs": mzs,
            "intensities": intensities,
            "monoisotopic_mass": monoisotopic_mass,
            "average_mass": average_mass,
            "formula": formula_str,
            "source_type": f"Elemental Formula ({generator_name})",
            "input_value": formula_str,
            "generator": generator_name
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error generating pattern from formula: {str(e)}"}

def generate_isotope_pattern_from_sequence(sequence_str: str, use_fine_generator: bool = False) -> Dict[str, Any]:
    """Generate isotope pattern from peptide/protein sequence using specified generator.
    
    Args:
        sequence_str (str): The amino acid sequence
        use_fine_generator (bool): Whether to use FineIsotopePatternGenerator (default: False)
        
    Returns:
        Dict[str, Any]: Results dictionary with mzs, intensities, and metadata
    """
    try:
        # Validate sequence
        is_valid, error_msg, clean_sequence = validate_peptide_sequence(sequence_str)
        if not is_valid:
            return {"success": False, "error": error_msg}
        
        # Create AASequence object
        aa_sequence = oms.AASequence.fromString(clean_sequence)
        
        # Get empirical formula from sequence
        empirical_formula = aa_sequence.getFormula()
        
        # Select generator
        generator = fine_pattern_generator if use_fine_generator else coarse_pattern_generator
        generator_name = "Fine" if use_fine_generator else "Coarse"
        
        # Generate isotope pattern
        isotope_distribution = empirical_formula.getIsotopeDistribution(generator)
        avg_weight = aa_sequence.getAverageWeight()
        
        distribution = isotope_distribution.getContainer()
        
        # Extract data
        mzs = np.array([p.getMZ() for p in distribution])
        intensities = np.array([p.getIntensity() for p in distribution])
        
        # Calculate masses
        monoisotopic_mass = aa_sequence.getMonoWeight()
        average_mass = aa_sequence.getAverageWeight()
        
        # Handle formula string conversion (pyOpenMS version compatibility)
        formula_str = empirical_formula.toString()
        if isinstance(formula_str, bytes):
            formula_str = formula_str.decode('utf-8')
        
        return {
            "success": True,
            "mzs": mzs,
            "intensities": intensities,
            "monoisotopic_mass": monoisotopic_mass,
            "average_mass": average_mass,
            "formula": formula_str,
            "sequence": clean_sequence,
            "source_type": f"Peptide/Protein Sequence ({generator_name})",
            "input_value": sequence_str,
            "generator": generator_name
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error generating pattern from sequence: {str(e)}"}

def generate_isotope_pattern_from_oligonucleotide(sequence_str: str, use_fine_generator: bool = False) -> Dict[str, Any]:
    """Generate isotope pattern from oligonucleotide (DNA/RNA) sequence using specified generator.
    
    Args:
        sequence_str (str): The nucleotide sequence (DNA will be converted to RNA)
        use_fine_generator (bool): Whether to use FineIsotopePatternGenerator (default: False)
        
    Returns:
        Dict[str, Any]: Results dictionary with mzs, intensities, and metadata
    """
    try:
        # Validate sequence (converts DNA to RNA automatically)
        is_valid, error_msg, rna_sequence = validate_oligonucleotide_sequence(sequence_str)
        if not is_valid:
            return {"success": False, "error": error_msg}
        
        # Check if conversion happened
        original_clean = re.sub(r'[^ACGTUN]', '', sequence_str.strip().upper())
        conversion_note = ""
        if 'T' in original_clean:
            conversion_note = " (DNA converted to RNA: T→U)"
        
        # Create NASequence object (for nucleic acids - RNA only)
        na_sequence = oms.NASequence.fromString(rna_sequence)
        
        # Get empirical formula from sequence
        empirical_formula = na_sequence.getFormula()
        
        # Select generator
        generator = fine_pattern_generator if use_fine_generator else coarse_pattern_generator
        generator_name = "Fine" if use_fine_generator else "Coarse"
        
        # Generate isotope pattern
        isotope_distribution = empirical_formula.getIsotopeDistribution(generator)
        avg_weight = na_sequence.getAverageWeight()
        
        distribution = isotope_distribution.getContainer()
        
        # Extract data
        mzs = np.array([p.getMZ() for p in distribution])
        intensities = np.array([p.getIntensity() for p in distribution])
        
        # Calculate masses
        monoisotopic_mass = na_sequence.getMonoWeight()
        average_mass = na_sequence.getAverageWeight()
        
        # Handle formula string conversion (pyOpenMS version compatibility)
        formula_str = empirical_formula.toString()
        if isinstance(formula_str, bytes):
            formula_str = formula_str.decode('utf-8')
        
        return {
            "success": True,
            "mzs": mzs,
            "intensities": intensities,
            "monoisotopic_mass": monoisotopic_mass,
            "average_mass": average_mass,
            "formula": formula_str,
            "sequence": rna_sequence,
            "original_sequence": original_clean,
            "conversion_note": conversion_note,
            "source_type": f"Oligonucleotide Sequence ({generator_name}){conversion_note}",
            "input_value": sequence_str,
            "generator": generator_name
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error generating pattern from oligonucleotide: {str(e)}"}

def generate_isotope_pattern_from_mass(target_mass: float) -> Dict[str, Any]:
    """Generate isotope pattern from mass using CoarseIsotopePatternGenerator (existing method).
    
    Args:
        target_mass (float): The target mass in Da
        
    Returns:
        Dict[str, Any]: Results dictionary with mzs, intensities, and metadata
    """
    try:
        if target_mass <= 0:
            return {"success": False, "error": "Mass must be greater than 0"}
        
        # Start with most_intense_mass == avg_mass (existing algorithm)
        start = coarse_pattern_generator.estimateFromPeptideWeight(target_mass).getMostAbundant().getMZ()
        
        # Extend to the right
        right_samples = []
        right_samples_avg = []
        for delta in np.arange(0, 20, 0.2):
            current_sample = coarse_pattern_generator.estimateFromPeptideWeight(
                target_mass + delta
            ).getMostAbundant().getMZ()
            right_samples.append(current_sample)
            right_samples_avg.append(target_mass + delta)

            # Stop extension if result gets worse than base case
            if abs(current_sample - target_mass) > abs(start - target_mass):
                break
        
        # Extend to the left
        left_samples = []
        left_samples_avg = []
        for delta in np.arange(0, 20, 0.2):
            current_sample = coarse_pattern_generator.estimateFromPeptideWeight(
                target_mass - delta
            ).getMostAbundant().getMZ()
            left_samples.append(current_sample)
            left_samples_avg.append(target_mass - delta)

            # Stop extension if result gets worse than base case
            if abs(current_sample - target_mass) > abs(start - target_mass):
                break
        
        # Combine samples
        samples = np.array(left_samples + [start] + right_samples)
        samples_avg = np.array(left_samples_avg + [target_mass] + right_samples_avg)
        
        # Determine best fit
        best_pos = np.argmin(np.abs(samples - target_mass))
        best_avg = samples_avg[best_pos]
        
        # Compute distribution of best fit
        distribution_obj = coarse_pattern_generator.estimateFromPeptideWeight(best_avg)
        distribution = distribution_obj.getContainer()
        mzs = np.array([p.getMZ() for p in distribution])
        intensities = np.array([p.getIntensity() for p in distribution])
        monoisotopic = np.min(mzs)  # Monoisotopic isotope = lightest

        # Recompute average
        best_avg = np.sum(mzs * intensities)

        # Adjust distribution
        delta = distribution_obj.getMostAbundant().getMZ() - target_mass
        mzs -= delta
        best_avg -= delta
        monoisotopic -= delta
        
        return {
            "success": True,
            "mzs": mzs,
            "intensities": intensities,
            "monoisotopic_mass": monoisotopic,
            "average_mass": best_avg,
            "formula": "Estimated from mass",
            "source_type": "Mass Estimation",
            "input_value": f"{target_mass:.2f} Da"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error generating pattern from mass: {str(e)}"}
