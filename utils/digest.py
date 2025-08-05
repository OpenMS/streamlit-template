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

                if peptide.size() > 0:  # Skip empty peptides
                    try:
                        # Calculate mass using AASequence
                        aa_seq = oms.AASequence(peptide)
                        mono_mass = aa_seq.getMonoWeight()
                        
                        # Create row data
                        peptide_string = peptide.toString()
                        
                        # Find all positions of this peptide in the original sequence
                        start_positions = []
                        end_positions = []
                        start_pos = 0
                        while True:
                            pos = sequence.find(peptide_string, start_pos)
                            if pos == -1:
                                break
                            start_positions.append(str(pos + 1))  # Convert to 1-based
                            end_positions.append(str(pos + len(peptide_string)))  # End position (1-based)
                            start_pos = pos + 1
                        
                        # Join positions with commas if multiple occurrences
                        start_str = ','.join(start_positions)
                        end_str = ','.join(end_positions)
                        
                        row_data = {
                            'Accession': accession,
                            'Description': description,
                            'Peptide Sequence': peptide_string,
                            'Length': len(peptide_string),
                            'Start': start_str,
                            'End': end_str,
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
        except Exception:
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


def filter_peptides_by_length(df: pd.DataFrame, min_length: int = None, max_length: int = None) -> pd.DataFrame:
    """
    Filter peptides by amino acid sequence length.
    
    Args:
        df: DataFrame with digest results
        min_length: Minimum peptide length (number of amino acids)
        max_length: Maximum peptide length (number of amino acids)
        
    Returns:
        Filtered DataFrame
    """
    filtered_df = df.copy()
    
    if min_length is not None:
        filtered_df = filtered_df[filtered_df['Peptide Sequence'].str.len() >= min_length]
    
    if max_length is not None:
        filtered_df = filtered_df[filtered_df['Peptide Sequence'].str.len() <= max_length]
    
    return filtered_df


def get_available_enzymes() -> List[str]:
    """
    Get list of available enzymes from pyOpenMS EnzymesDB.
    
    Returns:
        List of enzyme names
        
    Raises:
        RuntimeError: If pyOpenMS enzyme database cannot be loaded
    """
    try:
        # Get enzyme database
        enzyme_db = oms.ProteaseDB()
        enzymes = []
        enzyme_db.getAllNames(enzymes)       
        return enzymes
    except Exception as e:
        raise RuntimeError(f"Failed to load pyOpenMS enzyme database: {e}. Please ensure pyOpenMS is properly configured.") from e


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


def calculate_protein_coverage(df: pd.DataFrame, sequences: List[Tuple[str, str]]) -> Dict[str, Dict]:
    """
    Calculate coverage for each position in each protein sequence.
    
    Args:
        df: DataFrame with digest results
        sequences: List of (header, sequence) tuples
        
    Returns:
        Dictionary mapping accession to coverage info
    """
    coverage_data = {}
    
    # Create mapping from accession to sequence
    accession_to_sequence = {}
    for header, sequence in sequences:
        accession = extract_accession(header)
        accession_to_sequence[accession] = sequence
    
    # Initialize coverage arrays for each protein
    for accession, sequence in accession_to_sequence.items():
        coverage_data[accession] = {
            'sequence': sequence,
            'coverage': [0] * len(sequence),
            'description': ''
        }
    
    # Calculate coverage from digest results
    for _, row in df.iterrows():
        accession = row['Accession']
        if accession in coverage_data:
            # Get description from first occurrence
            if not coverage_data[accession]['description']:
                coverage_data[accession]['description'] = row['Description']
            
            # Parse start and end positions
            start_positions = row['Start'].split(',') if row['Start'] else []
            end_positions = row['End'].split(',') if row['End'] else []
            
            # Increment coverage for each occurrence of this peptide
            for start_str, end_str in zip(start_positions, end_positions):
                try:
                    start = int(start_str) - 1  # Convert to 0-based
                    end = int(end_str)  # End is already exclusive in 1-based
                    
                    # Increment coverage for all positions covered by this peptide
                    for pos in range(start, end):
                        if 0 <= pos < len(coverage_data[accession]['coverage']):
                            coverage_data[accession]['coverage'][pos] += 1
                except (ValueError, IndexError):
                    continue
    
    return coverage_data


def generate_coverage_html(accession: str, coverage_info: Dict) -> str:
    """
    Generate HTML for protein sequence with coverage coloring.
    
    Args:
        accession: Protein accession
        coverage_info: Coverage information dictionary
        
    Returns:
        HTML string for colored sequence
    """
    sequence = coverage_info['sequence']
    coverage = coverage_info['coverage']
    description = coverage_info['description']
    
    # Define colors for different coverage levels
    colors = {
        0: '#f0f0f0',  # Light gray for no coverage
        1: '#ffffcc',  # Light yellow for 1x coverage
        2: '#ffcc99',  # Light orange for 2x coverage
        3: '#ff9999',  # Light red for 3x coverage
        4: '#ff6666',  # Medium red for 4x coverage
    }
    
    html_parts = [f"<h4>{accession} - {description}</h4>"]
    html_parts.append("<div style='font-family: monospace; line-height: 1.8; word-wrap: break-word;'>")
    
    # Add coverage legend
    html_parts.append("<div style='margin-bottom: 10px; font-size: 12px;'>")
    html_parts.append("Coverage: ")
    for level, color in colors.items():
        if level <= 4:
            label = f"{level}x" if level < 4 else "4+x"
            html_parts.append(f"<span style='background-color: {color}; padding: 2px 6px; margin-right: 5px; border: 1px solid #ccc;'>{label}</span>")
    html_parts.append("</div>")
    
    # Generate colored sequence
    for i, aa in enumerate(sequence):
        if i < len(coverage):
            cov_level = min(coverage[i], 4)  # Cap at 4 for coloring
            color = colors.get(cov_level, colors[4])
        else:
            cov_level = 0  # Default coverage level for positions beyond coverage array
            color = colors[0]
        
        html_parts.append(f"<span style='background-color: {color}; padding: 1px;' title='Position {i+1}: {cov_level}x coverage'>{aa}</span>")
        
        # Add line breaks every 50 amino acids for readability
        if (i + 1) % 50 == 0:
            html_parts.append("<br>")
    
    html_parts.append("</div>")
    html_parts.append("<br>")
    
    return "".join(html_parts)
