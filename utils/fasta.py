"""
FASTA parsing and validation utilities.
"""
import re
from typing import List, Tuple, Optional


def parse_fasta(fasta_text: str) -> List[Tuple[str, str]]:
    """
    Parse FASTA text into a list of (header, sequence) tuples.
    
    Args:
        fasta_text: Raw FASTA text input
        
    Returns:
        List of tuples containing (header, sequence)
        
    Raises:
        ValueError: If FASTA format is invalid
    """
    if not fasta_text.strip():
        return []
    
    sequences = []
    lines = fasta_text.strip().split('\n')
    current_header = None
    current_sequence = []
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('>'):
            # Save previous sequence if exists
            if current_header is not None:
                seq = ''.join(current_sequence)
                if seq:
                    sequences.append((current_header, seq))
                else:
                    raise ValueError(f"Empty sequence found for header: {current_header}")
            
            # Start new sequence
            current_header = line[1:]  # Remove '>' prefix
            current_sequence = []
        else:
            if current_header is None:
                raise ValueError(f"Line {line_num}: Sequence data found before header")
            current_sequence.append(line.upper())
    
    # Add the last sequence
    if current_header is not None:
        seq = ''.join(current_sequence)
        if seq:
            sequences.append((current_header, seq))
        else:
            raise ValueError(f"Empty sequence found for header: {current_header}")
    
    if not sequences:
        raise ValueError("No valid FASTA sequences found")
    
    return sequences


def validate_protein_sequence(sequence: str) -> bool:
    """
    Validate that a sequence contains only valid amino acid characters.
    
    Args:
        sequence: Protein sequence string
        
    Returns:
        True if valid, False otherwise
    """
    # Valid amino acid single letter codes
    valid_aa = set('ACDEFGHIKLMNPQRSTVWY')
    return all(aa in valid_aa for aa in sequence.upper())


def extract_accession(header: str) -> str:
    """
    Extract accession number from FASTA header.
    
    Args:
        header: FASTA header line (without '>')
        
    Returns:
        Accession number or original header if no standard format found
    """
    # Try to extract accession from common formats
    # UniProt format: sp|P12345|PROT_HUMAN or tr|A0A123B4C5|A0A123B4C5_HUMAN
    uniprot_match = re.match(r'(sp|tr)\|([^|]+)\|', header)
    if uniprot_match:
        return uniprot_match.group(2)
    
    # NCBI format: gi|123456|ref|NP_123456.1| or ref|NP_123456.1|
    ncbi_match = re.match(r'(?:gi\|\d+\|)?(?:ref\|)?([^|]+)', header)
    if ncbi_match:
        return ncbi_match.group(1)
    
    # Generic format: take first word
    first_word = header.split()[0] if header.split() else header
    return first_word


def extract_description(header: str) -> str:
    """
    Extract description from FASTA header.
    
    Args:
        header: FASTA header line (without '>')
        
    Returns:
        Description part of the header
    """
    # For UniProt format, description comes after the second |
    uniprot_match = re.match(r'(sp|tr)\|[^|]+\|[^|\s]+\s*(.*)', header)
    if uniprot_match:
        return uniprot_match.group(2).strip()
    
    # For other formats, try to extract everything after first space
    parts = header.split(' ', 1)
    if len(parts) > 1:
        return parts[1].strip()
    
    return header


def validate_fasta_input(fasta_text: str) -> Tuple[bool, Optional[str], List[Tuple[str, str]]]:
    """
    Validate FASTA input and return parsed sequences if valid.
    
    Args:
        fasta_text: Raw FASTA text input
        
    Returns:
        Tuple of (is_valid, error_message, sequences)
    """
    try:
        sequences = parse_fasta(fasta_text)
        
        # Validate each sequence
        for header, sequence in sequences:
            if not validate_protein_sequence(sequence):
                invalid_chars = set(sequence.upper()) - set('ACDEFGHIKLMNPQRSTVWY')
                return False, f"Invalid amino acids found in sequence '{extract_accession(header)}': {', '.join(sorted(invalid_chars))}", []
        
        return True, None, sequences
        
    except ValueError as e:
        return False, str(e), []