"""
Theoretical fragment spectra with pyOpenMS, shared by the Streamlit page
(content/fragmentation.py) and the Svelte app's server.
"""

import re
from typing import Tuple, Dict, Any, Optional, List

import pyopenms as oms
import pandas as pd

# Ion type configuration
ION_TYPES = {
    'a': {'name': 'a-ions', 'description': 'N-terminal ions (peptide bond + loss of CO)', 'param': 'add_a_ions'},
    'b': {'name': 'b-ions', 'description': 'N-terminal ions (peptide bond cleavage)', 'param': 'add_b_ions'},
    'c': {'name': 'c-ions', 'description': 'N-terminal ions (N-Cα bond cleavage)', 'param': 'add_c_ions'},
    'x': {'name': 'x-ions', 'description': 'C-terminal ions (N-Cα bond + addition of CO)', 'param': 'add_x_ions'},
    'y': {'name': 'y-ions', 'description': 'C-terminal ions (peptide bond cleavage)', 'param': 'add_y_ions'},
    'z': {'name': 'z-ions', 'description': 'C-terminal ions (N-Cα bond cleavage)', 'param': 'add_z_ions'}
}

def validate_peptide_sequence(sequence_str: str) -> Tuple[bool, str, Optional[str]]:
    """Validate a peptide sequence for fragmentation.
    
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
            
        # Check minimum length for fragmentation
        if len(clean_sequence) < 2:
            return False, "Sequence must be at least 2 amino acids long for fragmentation", None
            
        # Validate amino acids
        valid_aa = set("ACDEFGHIKLMNPQRSTVWYXU")
        invalid_chars = [aa for aa in clean_sequence if aa not in valid_aa]
        
        if invalid_chars:
            invalid_list = ", ".join(sorted(set(invalid_chars)))
            return False, f"Invalid amino acid(s): {invalid_list}", None
            
        return True, "", clean_sequence
        
    except Exception as e:
        return False, f"Error validating sequence: {str(e)}", None

def configure_spectrum_generator(ion_types: List[str], max_charge: int = 2) -> oms.TheoreticalSpectrumGenerator:
    """Configure the TheoreticalSpectrumGenerator with selected ion types.
    
    Args:
        ion_types (List[str]): List of ion type keys to enable
        max_charge (int): Maximum charge state to consider
        
    Returns:
        oms.TheoreticalSpectrumGenerator: Configured generator
    """
    tsg = oms.TheoreticalSpectrumGenerator()
    param = oms.Param()
    
    # Disable all ion types first
    for ion_key, ion_info in ION_TYPES.items():
        param.setValue(ion_info['param'], "false")
    
    # Enable selected ion types
    for ion_type in ion_types:
        if ion_type in ION_TYPES:
            param.setValue(ION_TYPES[ion_type]['param'], "true")
    
    # Set other parameters
    param.setValue("add_first_prefix_ion", "true")
    param.setValue("add_losses", "false")  # Disable neutral losses for simplicity
    param.setValue("add_metainfo", "true")
    param.setValue("add_isotopes", "false")  # Disable isotopes for cleaner spectra
    param.setValue("max_isotope", 2)
    param.setValue("rel_loss_intensity", 0.1)
    
    tsg.setParameters(param)
    return tsg

def generate_theoretical_spectrum(sequence_str: str, ion_types: List[str], charges: List[int]) -> Dict[str, Any]:
    """Generate theoretical fragment spectrum for a peptide sequence.
    
    Args:
        sequence_str (str): The amino acid sequence
        ion_types (List[str]): List of ion types to include
        charges (List[int]): List of charge states to consider
        
    Returns:
        Dict[str, Any]: Results dictionary with fragment data
    """
    try:
        # Validate sequence
        is_valid, error_msg, clean_sequence = validate_peptide_sequence(sequence_str)
        if not is_valid:
            return {"success": False, "error": error_msg}
        
        if not ion_types:
            return {"success": False, "error": "Please select at least one ion type"}
        
        if not charges:
            return {"success": False, "error": "Please select at least one charge state"}
        
        # Create AASequence object
        aa_sequence = oms.AASequence.fromString(clean_sequence)
        
        # Configure spectrum generator
        max_charge = max(charges)
        tsg = configure_spectrum_generator(ion_types, max_charge)
        
        # Generate spectra for each charge state
        all_fragments = []
        
        for charge in charges:
            spectrum = oms.MSSpectrum()
            tsg.getSpectrum(spectrum, aa_sequence, charge, charge)
            
            # Extract peak data with annotations from StringDataArrays
            mzs = spectrum.get_peaks()[0]
            intensities = spectrum.get_peaks()[1]
            
            # Get annotations from StringDataArrays
            annotations = []
            if spectrum.getStringDataArrays():
                annotations = list(spectrum.getStringDataArrays()[0])
                annotations = [ann.decode('utf-8') if isinstance(ann, bytes) else ann for ann in annotations]
            
            # If no annotations available, create empty list
            if not annotations:
                annotations = [''] * len(mzs)
            
            for mz, intensity, annotation in zip(mzs, intensities, annotations):
                # Parse ion information from annotation
                ion_info = parse_ion_annotation(annotation, mz, clean_sequence)
                
                all_fragments.append({
                    'mz': mz,
                    'intensity': intensity,
                    'charge': charge,
                    'ion_type': ion_info.get('ion_type', 'unknown'),
                    'fragment_number': ion_info.get('fragment_number', 0),
                    'sequence': ion_info.get('fragment_sequence', ''),
                    'annotation': annotation if annotation else f'm/z {mz:.4f}'
                })
        
        # Convert to DataFrame
        df = pd.DataFrame(all_fragments)
        df = df.sort_values(['ion_type', 'fragment_number', 'charge'])
        
        return {
            "success": True,
            "fragments": df,
            "sequence": clean_sequence,
            "ion_types": ion_types,
            "charges": charges,
            "input_value": sequence_str
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error generating spectrum: {str(e)}"}

def parse_ion_annotation(annotation, mz: float, peptide_sequence: str = '') -> Dict[str, Any]:
    """Parse ion annotation string from pyOpenMS to extract ion information.
    
    Args:
        annotation: The annotation from StringDataArrays (str or bytes)
        mz (float): The m/z value
        peptide_sequence (str): The full peptide sequence
        
    Returns:
        Dict[str, Any]: Parsed ion information
    """
    # Handle bytes objects from pyOpenMS
    if isinstance(annotation, bytes):
        annotation = annotation.decode('utf-8')
    
    # Convert to string if needed
    annotation = str(annotation) if annotation is not None else ''
    
    if not annotation:
        return {
            'ion_type': 'unknown',
            'fragment_number': 0,
            'fragment_sequence': '',
            'annotation': f'm/z {mz:.4f}'
        }
    
    # Parse annotation like "b3+", "y5++", etc.
    
    # Match pattern: ion_type + number + charges
    match = re.match(r'([abcxyz])(\d+)(\+*)', annotation)
    if match:
        ion_type = match.group(1)
        fragment_number = int(match.group(2))
        charges = len(match.group(3))
        
        # Calculate fragment sequence
        fragment_sequence = ''
        if peptide_sequence and fragment_number > 0:
            if ion_type in ['a', 'b', 'c']:  # N-terminal ions
                if fragment_number <= len(peptide_sequence):
                    fragment_sequence = peptide_sequence[:fragment_number]
            elif ion_type in ['x', 'y', 'z']:  # C-terminal ions
                if fragment_number <= len(peptide_sequence):
                    fragment_sequence = peptide_sequence[-fragment_number:]
        
        return {
            'ion_type': ion_type,
            'fragment_number': fragment_number,
            'fragment_sequence': fragment_sequence,
            'annotation': annotation
        }
    
    # If parsing fails, return unknown
    return {
        'ion_type': 'unknown',
        'fragment_number': 0,
        'fragment_sequence': '',
        'annotation': annotation
    }

def annotate_fragment(mz: float, aa_sequence: oms.AASequence, charge: int, ion_types: List[str]) -> Dict[str, Any]:
    """Annotate a fragment peak with ion type and fragment number.
    
    Args:
        mz (float): The m/z value of the fragment
        aa_sequence (oms.AASequence): The original sequence
        charge (int): The charge state
        ion_types (List[str]): Enabled ion types
        
    Returns:
        Dict[str, Any]: Annotation information
    """
    sequence_str = aa_sequence.toString()
    sequence_length = len(sequence_str)
    
    # Calculate theoretical masses for different fragment types
    for ion_type in ion_types:
        if ion_type in ['a', 'b', 'c']:  # N-terminal ions
            for i in range(1, sequence_length):
                fragment_seq = sequence_str[:i]
                fragment_aa_seq = oms.AASequence.fromString(fragment_seq)
                
                # Calculate theoretical m/z for this ion type
                theoretical_mz = calculate_ion_mz(fragment_aa_seq, ion_type, charge)
                
                # Check if this matches our observed m/z (within tolerance)
                if abs(mz - theoretical_mz) < 0.01:  # 0.01 Da tolerance
                    return {
                        'ion_type': ion_type,
                        'fragment_number': i,
                        'fragment_sequence': fragment_seq,
                        'annotation': f'{ion_type}{i}{"+" * charge}'
                    }
        
        elif ion_type in ['x', 'y', 'z']:  # C-terminal ions
            for i in range(1, sequence_length):
                fragment_seq = sequence_str[-i:]
                fragment_aa_seq = oms.AASequence.fromString(fragment_seq)
                
                # Calculate theoretical m/z for this ion type
                theoretical_mz = calculate_ion_mz(fragment_aa_seq, ion_type, charge)
                
                # Check if this matches our observed m/z (within tolerance)
                if abs(mz - theoretical_mz) < 0.01:  # 0.01 Da tolerance
                    return {
                        'ion_type': ion_type,
                        'fragment_number': i,
                        'fragment_sequence': fragment_seq,
                        'annotation': f'{ion_type}{i}{"+" * charge}'
                    }
    
    # Default annotation if no match found
    return {
        'ion_type': 'unknown',
        'fragment_number': 0,
        'fragment_sequence': '',
        'annotation': f'm/z {mz:.4f}{"+" * charge}'
    }

def calculate_ion_mz(fragment_sequence: oms.AASequence, ion_type: str, charge: int) -> float:
    """Calculate theoretical m/z for a fragment ion.
    
    Args:
        fragment_sequence (oms.AASequence): The fragment sequence
        ion_type (str): The ion type (a, b, c, x, y, z)
        charge (int): The charge state
        
    Returns:
        float: Theoretical m/z value
    """
    mass = fragment_sequence.getMonoWeight()
    
    # Apply ion type specific mass adjustments
    if ion_type == 'a':
        mass -= 27.994915  # -CO
    elif ion_type == 'b':
        mass += 0.0  # No adjustment
    elif ion_type == 'c':
        mass += 17.026549  # +NH3
    elif ion_type == 'x':
        mass += 25.980218  # +CO -H
    elif ion_type == 'y':
        mass += 18.010565  # +H2O
    elif ion_type == 'z':
        mass += 0.984016  # +H -NH2
    
    # Add protons for charge
    mass += charge * 1.007276
    
    return mass / charge
