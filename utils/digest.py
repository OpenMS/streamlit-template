"""
Protein digestion utilities using pyOpenMS.
"""
import pandas as pd
from typing import List, Tuple, Dict, Any
import pyopenms as oms
from .fasta import extract_accession, extract_description


import os


def perform_digest(sequences: List[Tuple[str, str]], enzyme: str, missed_cleavages: int, max_charges: int) -> pd.DataFrame:
    """
    Perform in silico protein digestion using pyOpenMS.
    
    Args:
        sequences: List of (header, sequence) tuples
        enzyme: Enzyme name for digestion
        missed_cleavages: Maximum number of missed cleavages
        max_charges: Maximum charge state to calculate
        
    Returns:
        pandas DataFrame with digest results
    """
    results = []
    
    # Set up the digestion
    digest = oms.ProteaseDigestion()
    digest.setEnzyme(enzyme)
    digest.setMissedCleavages(missed_cleavages)
    
    for header, sequence in sequences:
        accession = extract_accession(header)
        description = extract_description(header)
        try:
            # Use the correct pyOpenMS digest method with string input
            peptide_strings = []
            seq = oms.AASequence.fromString(sequence)
            digest.digest(seq, peptide_strings)

            #for peptide_seq in peptide_strings:
            #    os.write(1, f"Generated peptide: {peptide_seq}\n".encode())
            for i, peptide in enumerate(peptide_strings):
                os.write(1, f"Peptide {i+1}: {peptide}\n".encode())

                if peptide.size() > 0:  # Skip empty peptides
                    try:
                        # Calculate mass using AASequence
                        aa_seq = oms.AASequence(peptide)
                        mono_mass = aa_seq.getMonoWeight()
                        
                        # Create row data
                        row_data = {
                            'Accession': accession,
                            'Description': description,
                            'Peptide Sequence': peptide.toString(),
                            '[M]': round(mono_mass, 4)
                        }
                        
                        # Add charged masses [M + zH]
                        for charge in range(1, max_charges + 1):
                            charged_mass = (mono_mass + charge * 1.007276) / charge
                            row_data[f'[M + {charge}H]'] = round(charged_mass, 4)
                        
                        results.append(row_data)
                    except Exception:
                        # Skip problematic peptides
                        continue
        except Exception as e:
            # If digest fails, skip this sequence
            continue
    
    return pd.DataFrame(results)


def calculate_mass_with_charge(mono_mass: float, charge: int) -> float:
    """
    Calculate mass-to-charge ratio for a given monoisotopic mass and charge.
    
    Args:
        mono_mass: Monoisotopic mass
        charge: Charge state
        
    Returns:
        Mass-to-charge ratio
    """
    proton_mass = 1.007276  # Mass of a proton
    return (mono_mass + charge * proton_mass) / charge


def get_digest_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate statistics for the digest results.
    
    Args:
        df: DataFrame with digest results
        
    Returns:
        Dictionary with statistics
    """
    if df.empty:
        return {
            'total_peptides': 0,
            'unique_proteins': 0,
            'avg_peptide_length': 0,
            'mass_range': (0, 0)
        }
    
    stats = {
        'total_peptides': len(df),
        'unique_proteins': df['Accession'].nunique(),
        'avg_peptide_length': df['Peptide Sequence'].str.len().mean(),
        'mass_range': (df['[M]'].min(), df['[M]'].max())
    }
    
    return stats


def filter_peptides_by_mass(df: pd.DataFrame, min_mass: float = None, max_mass: float = None) -> pd.DataFrame:
    """
    Filter peptides by mass range.
    
    Args:
        df: DataFrame with digest results
        min_mass: Minimum mass threshold
        max_mass: Maximum mass threshold
        
    Returns:
        Filtered DataFrame
    """
    filtered_df = df.copy()
    
    if min_mass is not None:
        filtered_df = filtered_df[filtered_df['[M]'] >= min_mass]
    
    if max_mass is not None:
        filtered_df = filtered_df[filtered_df['[M]'] <= max_mass]
    
    return filtered_df


def get_available_enzymes() -> List[str]:
    """
    Get list of available enzymes from pyOpenMS.
    
    Returns:
        List of enzyme names
    """
    try:
        # Get enzyme database
        enzyme_db = oms.ProteaseDB()
        enzymes = []
        
        # Get all enzyme names
        for enzyme_name in enzyme_db.getAllNames():
            enzymes.append(enzyme_name.decode() if isinstance(enzyme_name, bytes) else enzyme_name)
        
        return sorted(enzymes)
    except Exception:
        # Fallback to predefined list if pyOpenMS method fails
        from .config import OPENMS_SUPPORTED_ENZYMES
        return OPENMS_SUPPORTED_ENZYMES


def validate_enzyme(enzyme_name: str) -> bool:
    """
    Validate if an enzyme is supported by pyOpenMS.
    
    Args:
        enzyme_name: Name of the enzyme
        
    Returns:
        True if enzyme is supported, False otherwise
    """
    try:
        digest = oms.ProteaseDigestion()
        digest.setEnzyme(enzyme_name)
        return True
    except Exception:
        return False


def create_digest_summary(df: pd.DataFrame) -> str:
    """
    Create a text summary of the digest results.
    
    Args:
        df: DataFrame with digest results
        
    Returns:
        Summary text
    """
    if df.empty:
        return "No peptides generated from the digest."
    
    stats = get_digest_statistics(df)
    
    summary = f"""
    **Digest Summary:**
    - Total peptides: {stats['total_peptides']:,}
    - Unique proteins: {stats['unique_proteins']}
    - Average peptide length: {stats['avg_peptide_length']:.1f} amino acids
    - Mass range: {stats['mass_range'][0]:.2f} - {stats['mass_range'][1]:.2f} Da
    """
    
    return summary