"""
Peptide M/Z Calculator Backend

This module provides backend functions for peptide mass spectrometry calculations
using pyOpenMS. It handles peptide sequence processing, modifications, and m/z calculations.
"""

from typing import Dict, Any, Tuple, Optional, Union, List
from dataclasses import dataclass
import re


def _get_pyopenms():
    """Lazy import of pyOpenMS to avoid loading issues.

    Returns:
        module: The pyopenms module.

    """
    import pyopenms as poms

    return poms


_mod_db_cache = None


def _get_pyopenms_mod_db():
    """Lazy import and cached initialization of pyOpenMS ModificationsDB.

    Returns:
        ModificationsDB: The cached ModificationsDB instance.

    """
    global _mod_db_cache
    if _mod_db_cache is None:
        poms = _get_pyopenms()
        _mod_db_cache = poms.ModificationsDB()
    return _mod_db_cache


ERROR_MESSAGES = {
    "empty_sequence": "Please enter a peptide sequence.",
    "invalid_amino_acid": "Invalid amino acid sequence. Please use only standard amino acid codes (A, C, D, E, F, G, H, I, K, L, M, N, P, Q, R, S, T, V, W, Y, X, U).",
    "invalid_sequence_length": "Please enter a valid peptide sequence.",
    "calculation_error": "Error during calculation: {error}",
    "unexpected_error": "An unexpected error occurred: {error}",
}


@dataclass
class SequenceAnalysis:
    """Data class for sequence analysis results"""

    modification: str = "None"
    modification_detected: bool = False
    charge: int = 2
    charge_detected: bool = False
    is_valid: bool = True
    clean_sequence: str = ""
    error_message: Optional[str] = None


def parse_square_bracket_modifications(sequence: str) -> Tuple[str, str]:
    """Parse peptide sequence with square bracket modifications and convert to pyOpenMS format.

    Args:
        sequence (str): The peptide sequence containing square bracket modifications.

    Returns:
        Tuple[str, str]: A tuple containing (clean_sequence, modified_sequence).
            clean_sequence is the sequence without modifications.
            modified_sequence is the sequence converted to pyOpenMS format.

    """
    poms = _get_pyopenms()
    mod_db = _get_pyopenms_mod_db()

    sequence = sequence.strip()

    if sequence.startswith("."):
        sequence = sequence[1:]

    def convert_modification(mod_text):
        """Convert modification text to OpenMS format using ModificationsDB.

        Args:
            mod_text (str): The modification text to convert.

        Returns:
            str: The converted modification in OpenMS format.

        """
        mod_text = mod_text.strip()

        # Check if it's a numeric mass delta (ProForma arbitrary mass shift)
        mass_delta_pattern = r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$"
        if re.match(mass_delta_pattern, mod_text):
            if not mod_text.startswith(("+", "-")):
                mod_text = "+" + mod_text
            return f"[{mod_text}]"

        # Try to find modification by UNIMOD accession
        if mod_text.upper().startswith("UNIMOD:"):
            mod_accession = mod_text.upper()
            try:
                mod = mod_db.getModification(mod_accession)
                return mod.getId()
            except Exception:
                unimod_parts = mod_text.split(":")
                if (
                    len(unimod_parts) == 2
                    and unimod_parts[1].replace(".", "", 1).isdigit()
                ):
                    mass_delta = float(unimod_parts[1])
                    return f"[{'+' if mass_delta >= 0 else ''}{mass_delta}]"
                return mod_text

        try:
            mod = mod_db.getModification(mod_text)
            return mod.getId()
        except Exception:
            pass

        return mod_text

    # Handle N-terminal modifications: [Acetyl]PEPTIDE or .[Acetyl]PEPTIDE
    n_term_pattern = r"^\.?\[([^\]]+)\]"
    n_term_match = re.search(n_term_pattern, sequence)
    n_term_mod = ""
    if n_term_match:
        mod_name = convert_modification(n_term_match.group(1))
        if mod_name.startswith("[") and mod_name.endswith("]"):
            n_term_mod = f".{mod_name}"
        else:
            n_term_mod = f".({mod_name})"
        sequence = re.sub(n_term_pattern, "", sequence)

    c_term_pattern = r"\.\[([^\]]+)\]$"
    c_term_match = re.search(c_term_pattern, sequence)
    c_term_mod = ""
    if c_term_match:
        mod_name = convert_modification(c_term_match.group(1))
        if mod_name.startswith("[") and mod_name.endswith("]"):
            c_term_mod = f"{mod_name}."
        else:
            c_term_mod = f"({mod_name})."
        sequence = re.sub(c_term_pattern, "", sequence)

    aa_mod_pattern = r"([A-Z])\[([^\]]+)\]"

    clean_sequence = re.sub(aa_mod_pattern, r"\1", sequence)

    def replace_aa_mod(match):
        aa = match.group(1)
        mod_text = match.group(2)

        if aa == "X":
            mass_delta_pattern = r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$"
            if re.match(mass_delta_pattern, mod_text.strip()):
                clean_mass = mod_text.strip()
                if clean_mass.startswith("+"):
                    clean_mass = clean_mass[1:]
                elif clean_mass.startswith("-"):
                    pass
                return f"{aa}[{clean_mass}]"

        converted_mod = convert_modification(mod_text)

        if converted_mod.startswith("[") and converted_mod.endswith("]"):
            return f"{aa}{converted_mod}"
        else:
            return f"{aa}({converted_mod})"

    modified_sequence = re.sub(aa_mod_pattern, replace_aa_mod, sequence)

    if n_term_mod:
        modified_sequence = n_term_mod + modified_sequence
    if c_term_mod:
        modified_sequence = modified_sequence + c_term_mod

    return clean_sequence, modified_sequence


def validate_peptide_sequence_with_mods(sequence: str) -> Tuple[bool, str, str, int]:
    """Validate peptide sequence that may contain modifications and charge notation.

    Args:
        sequence (str): The peptide sequence to validate.

    Returns:
        Tuple[bool, str, str, int]: A tuple containing (is_valid, clean_sequence, openms_sequence, charge_state).
            is_valid indicates if the sequence is valid.
            clean_sequence is the sequence without modifications.
            openms_sequence is the OpenMS-formatted sequence.
            charge_state is the detected charge state.

    """
    try:
        clean_sequence, openms_sequence, charge_state = (
            parse_sequence_with_mods_and_charge(sequence)
        )

        valid_aa = set("ACDEFGHIKLMNPQRSTVWYXU")
        is_valid = all(aa in valid_aa for aa in clean_sequence if aa.isalpha())

        return is_valid, clean_sequence, openms_sequence, charge_state
    except Exception:
        return False, "", "", 1


def validate_peptide_sequence(sequence: str) -> tuple[bool, str]:
    """Validate peptide sequence contains only valid amino acids.

    Args:
        sequence (str): The peptide sequence to validate.

    Returns:
        tuple[bool, str]: A tuple containing (is_valid, clean_sequence).
            is_valid indicates if the sequence contains only valid amino acids.
            clean_sequence is the sequence without modifications.

    """
    import re

    try:
        clean_sequence, _ = parse_square_bracket_modifications(sequence)

        clean_sequence = re.sub(r"\(([^\)]+)\)", "", clean_sequence)

        if clean_sequence.startswith("."):
            clean_sequence = clean_sequence[1:]

        valid_aa = set("ACDEFGHIKLMNPQRSTVWYXU")
        is_valid = all(aa in valid_aa for aa in clean_sequence if aa.isalpha())
        return is_valid, clean_sequence
    except Exception:
        valid_aa = set("ACDEFGHIKLMNPQRSTVWYXU")
        sequence_clean = sequence.upper()
        sequence_clean = re.sub(r"\[([^\]]+)\]", "", sequence_clean)
        sequence_clean = re.sub(r"\(([^\)]+)\)", "", sequence_clean)
        if sequence_clean.startswith("."):
            sequence_clean = sequence_clean[1:]
        sequence_clean = "".join(c for c in sequence_clean if c.isalpha())
        return all(aa in valid_aa for aa in sequence_clean), sequence_clean


def apply_modification(sequence: str, modification: str) -> str:
    """Apply the selected modification to the peptide sequence.

    Args:
        sequence (str): The peptide sequence to modify.
        modification (str): The modification to apply (e.g., "Oxidation (M)", "None").

    Returns:
        str: The modified sequence in OpenMS format.

    """
    if modification == "None":
        return sequence

    # Pre-defined mapping to avoid ModificationsDB lookups
    mod_mapping = {
        "Oxidation (M)": {"id": "Oxidation", "aa": "M"},
        "Carbamidomethyl (C)": {"id": "Carbamidomethyl", "aa": "C"},
        "Carboxymethyl (C)": {"id": "Carboxymethyl", "aa": "C"},
        "Phosphorylation (S/T/Y)": {"id": "Phospho", "aa": ["S", "T", "Y"]},
        "Acetylation (N-term)": {"id": "Acetyl", "terminal": "N"},
        "Methylation (K/R)": {"id": "Methyl", "aa": ["K", "R"]},
        "Deamidation (N/Q)": {"id": "Deamidated", "aa": ["N", "Q"]},
    }

    if modification in mod_mapping:
        mod_info = mod_mapping[modification]
        mod_id = mod_info["id"]

        if "aa" in mod_info:
            target_aas = (
                mod_info["aa"] if isinstance(mod_info["aa"], list) else [mod_info["aa"]]
            )
            modified_sequence = sequence
            for aa in target_aas:
                if aa in modified_sequence:
                    return modified_sequence.replace(aa, f"{aa}({mod_id})", 1)
            return sequence

        elif "terminal" in mod_info:
            if mod_info["terminal"] == "N":
                return f".({mod_id}){sequence}"
            elif mod_info["terminal"] == "C":
                return f"{sequence}({mod_id})."
            return sequence

    return sequence


def calculate_peptide_mz_range(
    sequence: str,
    charge_range: Tuple[int, int],
    modification: Union[str, List[str]] = "None",
) -> Dict[str, Any]:
    """Calculate m/z ratios for multiple charge states.

    Args:
        sequence (str): The peptide sequence
        charge_range (Tuple[int, int]): Min and max charge states (inclusive)
        modification (Union[str, List[str]]): Modification(s) to apply

    Returns:
        Dict containing results for all charge states
    """
    min_charge, max_charge = charge_range
    charge_results = {}

    for charge in range(min_charge, max_charge + 1):
        result = calculate_peptide_mz(sequence, charge, modification)
        charge_results[charge] = result

    base_result = charge_results[min_charge]
    return {
        **base_result,
        "charge_results": charge_results,
        "charge_range": charge_range,
    }


def calculate_peptide_mz(
    sequence: str, charge_state: int, modification: Union[str, List[str]] = "None"
) -> Dict[str, Any]:
    """Calculate the m/z ratio and related properties for a peptide.

    Args:
        sequence (str): The peptide sequence. Can contain modifications in square brackets
                        and/or charge notation (e.g., "PEPTIDE/2", "M[Oxidation]PEPTIDE/3").
        charge_state (int): The charge state - will be overridden if charge notation is found.
        modification (Union[str, List[str]]): Additional modification(s) to apply from dropdown.
                                            Can be a single modification string or a list of modifications.
                                            Defaults to "None".

    Returns:
        Dict[str, Any]: A dictionary containing calculation results including:
            - mz_ratio: The calculated m/z ratio
            - monoisotopic_mass: The monoisotopic mass in Da
            - molecular_formula: The molecular formula
            - original_sequence: The clean amino acid sequence
            - modified_sequence: The sequence with modifications
            - charge_state: The final charge state used
            - charge_source: Where the charge state came from
            - modification: The applied modification
            - sequence_length: Length of the sequence
            - aa_composition: Amino acid composition dictionary
            - success: Boolean indicating successful calculation

    Raises:
        ValueError: If sequence is empty, charge state is invalid, or sequence contains invalid characters.

    """
    if not sequence.strip():
        raise ValueError("Peptide sequence cannot be empty")

    if charge_state < 1:
        raise ValueError("Charge state must be a positive integer")

    poms = _get_pyopenms()

    sequence_no_charge, extracted_charge = parse_charge_notation(sequence)

    # Try direct PyOpenMS parsing first for ProForma sequences
    proforma_direct = False
    clean_sequence = None
    openms_sequence = None

    try:
        test_seq = poms.AASequence.fromString(sequence_no_charge)

        clean_sequence = re.sub(r"\[([^\]]+)\]", "", sequence_no_charge)
        clean_sequence = re.sub(r"\(([^\)]+)\)", "", clean_sequence)
        if clean_sequence.startswith("."):
            clean_sequence = clean_sequence[1:]
        openms_sequence = sequence_no_charge
        proforma_direct = True
    except Exception:
        clean_sequence, openms_sequence, _ = parse_sequence_with_mods_and_charge(
            sequence
        )
        proforma_direct = False

    final_charge_state = extracted_charge if extracted_charge > 1 else charge_state
    charge_source = (
        "From sequence notation" if extracted_charge > 1 else "From input parameter"
    )

    # Validate amino acids
    valid_aa = set("ACDEFGHIKLMNPQRSTVWYXU")
    invalid_chars = [aa for aa in clean_sequence if aa.isalpha() and aa not in valid_aa]
    if invalid_chars:
        invalid_list = ", ".join(sorted(set(invalid_chars)))
        raise ValueError(
            f"Invalid amino acid(s) found in sequence: {invalid_list}. Valid amino acids are: A, C, D, E, F, G, H, I, K, L, M, N, P, Q, R, S, T, V, W, Y, X, U"
        )

    non_alpha_chars = [c for c in clean_sequence if not c.isalpha()]
    if non_alpha_chars:
        non_alpha_list = ", ".join(sorted(set(non_alpha_chars)))
        raise ValueError(
            f"Invalid character(s) found in sequence: {non_alpha_list}. Sequence should contain only amino acid letters. Did you mean to use charge notation (e.g., /2)?"
        )

    if not all(aa in valid_aa for aa in clean_sequence if aa.isalpha()):
        raise ValueError(f"Invalid amino acids found in sequence: {clean_sequence}")

    if proforma_direct:
        modified_sequence_str = openms_sequence
        applied_modification = "ProForma arbitrary mass deltas (direct parsing)"
    elif openms_sequence != clean_sequence:
        modified_sequence_str = openms_sequence
        applied_modification = "From sequence notation (converted)"

        if isinstance(modification, list):
            if modification:
                for mod in modification:
                    modified_sequence_str = apply_modification(
                        modified_sequence_str, mod
                    )
                applied_modification += " + " + ", ".join(modification)
        else:
            if modification != "None":
                modified_sequence_str = apply_modification(
                    modified_sequence_str, modification
                )
                applied_modification += " + " + modification
    else:
        if isinstance(modification, list):
            if modification:
                modified_sequence_str = clean_sequence
                for mod in modification:
                    modified_sequence_str = apply_modification(
                        modified_sequence_str, mod
                    )
                applied_modification = ", ".join(modification)
            else:
                modified_sequence_str = clean_sequence
                applied_modification = "None"
        else:
            modified_sequence_str = apply_modification(clean_sequence, modification)
            applied_modification = modification

    try:
        aa_sequence_obj = poms.AASequence.fromString(modified_sequence_str)
    except Exception as e:
        raise ValueError(
            f"Failed to parse modified sequence '{modified_sequence_str}': {str(e)}"
        )

    mz_ratio = aa_sequence_obj.getMZ(final_charge_state)
    mono_weight = aa_sequence_obj.getMonoWeight()
    formula = aa_sequence_obj.getFormula()

    standardized_modified_sequence = aa_sequence_obj.toString()

    # Calculate amino acid composition
    aa_composition = {}
    for aa_char in clean_sequence:
        if aa_char.isalpha():
            aa_composition[aa_char] = aa_composition.get(aa_char, 0) + 1

    return {
        "mz_ratio": mz_ratio,
        "monoisotopic_mass": mono_weight,
        "molecular_formula": formula.toString(),
        "original_sequence": clean_sequence,
        "modified_sequence": standardized_modified_sequence,
        "charge_state": final_charge_state,
        "charge_source": charge_source,
        "modification": applied_modification,
        "sequence_length": len(clean_sequence),
        "aa_composition": aa_composition,
        "success": True,
    }


def get_supported_modifications() -> list:
    """Get a list of supported peptide modifications.

    Returns:
        list: A list of supported modification names including "None".

    """
    common_modifications = [
        "None",
        "Oxidation (M)",
        "Carbamidomethyl (C)",
        "Carboxymethyl (C)",
        "Phosphorylation (S/T/Y)",
        "Acetylation (N-term)",
        "Methylation (K/R)",
        "Deamidation (N/Q)",
    ]

    return common_modifications


def get_modification_info() -> Dict[str, str]:
    """Get detailed information about supported modifications.

    Returns:
        Dict[str, str]: A dictionary mapping modification names to their detailed descriptions
                        including mass delta and target information.

    """
    poms = _get_pyopenms()
    mod_db = _get_pyopenms_mod_db()
    info_dict = {"None": "No modification applied"}

    common_mods_ids = [
        "Oxidation",
        "Carbamidomethyl",
        "Phospho",
        "Acetyl",
        "Methyl",
        "Deamidated",
        "Amidated",
    ]

    for mod_id in common_mods_ids:
        try:
            mod = mod_db.getModification(mod_id)
            full_name = mod.getFullName()
            diff_mono_mass = mod.getDiffMonoMass()

            specificity = mod.getTermSpecificity()
            target_info_desc = ""
            if specificity == poms.ResidueModification.ANYWHERE:
                target_info_desc = "anywhere"
            elif specificity == poms.ResidueModification.N_TERM:
                target_info_desc = "N-terminus"
            elif specificity == poms.ResidueModification.C_TERM:
                target_info_desc = "C-terminus"
            else:
                target_aas = []
                for res in mod.getOrigin():
                    if res.isalpha():
                        target_aas.append(res)
                if target_aas:
                    target_info_desc = (
                        f"on {', '.join(sorted(set(target_aas)))} residues"
                    )

            description = f"{full_name} ({target_info_desc}, {'+' if diff_mono_mass >= 0 else ''}{diff_mono_mass:.6f} Da)"

            # Construct key name to match get_supported_modifications
            key_name_parts = [full_name]
            if specificity == poms.ResidueModification.N_TERM:
                key_name_parts.append("(N-term)")
            elif specificity == poms.ResidueModification.C_TERM:
                key_name_parts.append("(C-term)")
            elif specificity == poms.ResidueModification.ANYWHERE:
                pass
            else:
                target_aas = []
                for res in mod.getOrigin():
                    if res.isalpha():
                        target_aas.append(res)
                if target_aas:
                    key_name_parts.append(f" ({'/'.join(sorted(set(target_aas)))})")

            info_dict["".join(key_name_parts)] = description

        except Exception:
            pass
    return info_dict


def get_square_bracket_examples() -> Dict[str, str]:
    """Get examples of square bracket modification notation and charge notation.

    Returns:
        Dict[str, str]: A dictionary mapping example sequences to their descriptions.

    """
    return {
        "M[Oxidation]PEPTIDE": "Methionine oxidation at position 1",
        "PEPTIDEC[Carbamidomethyl]": "Carbamidomethylated cysteine at C-terminus",
        "[Acetyl]PEPTIDE": "N-terminal acetylation",
        "PEPTIDE[Amidated]": "C-terminal amidation",
        "PEPS[Phospho]TIDE": "Phosphorylated serine",
        ".[Acetyl]M[Oxidation]PEPTIDE": "N-terminal acetyl + methionine oxidation",
        "PEPTIDEM[Oxidation]": "C-terminal methionine oxidation",
        ".LLVLPKFGM[+15.9949]LMLGPDDFR": "Leading dot + mass delta modification",
        "ALSSC[UNIMOD:4]VVDEEQDVER": "UNIMOD:4 (Carbamidomethyl) modification",
        "M[UNIMOD:35]PEPTIDE": "UNIMOD:35 (Oxidation) modification",
        "PEPS[UNIMOD:21]TIDE": "UNIMOD:21 (Phospho) modification",
        "[UNIMOD:1]PEPTIDE": "UNIMOD:1 (N-terminal Acetyl) modification",
        "VAEINPSNGGTT/2": "Peptide with charge state 2 (slash notation)",
        "VAEINPSNGGTT2": "Peptide with charge state 2 (trailing number)",
        "M[Oxidation]PEPTIDE/3": "Modified peptide with charge state 3",
        "QVVPC[+57.021464]STSER/2": "Mass delta modification with charge state 2",
        "ALSSC[UNIMOD:4]VVDEEQDVER/2": "UNIMOD notation with charge state 2",
        "LGEPDYIPSQQDILLAR[+42.0106]": "ProForma arbitrary mass shift +42.0106 Da",
        "EM[+15.9949]EVEES[-79.9663]PEK": "Multiple arbitrary mass shifts",
        "RTAAX[+367.0537]WT": "Large arbitrary mass shift +367.0537 Da",
        "PEPTIDE[+100.0]": "Simple arbitrary mass shift +100.0 Da",
        "K[+28.0313]PEPTIDER[-10.0086]": "Multiple arbitrary shifts on different residues",
        "SEQUENCE[+0.9840]": "Small arbitrary mass shift",
        "LGEPDYIPSQQDILLAR[+42.0106]/2": "Arbitrary mass shift with charge notation",
        "PEPTIDE[+1.5e2]": "Scientific notation mass shift",
        "SEQUENCE[-18.0106]": "Negative arbitrary mass shift (water loss)",
    }


def validate_openms_sequence(sequence: str) -> bool:
    """Validate if a sequence string is compatible with pyOpenMS AASequence.

    Args:
        sequence (str): The sequence string to validate.

    Returns:
        bool: True if the sequence is compatible with pyOpenMS, False otherwise.

    """
    try:
        poms = _get_pyopenms()
        poms.AASequence.fromString(sequence)
        return True
    except Exception:
        return False


def parse_charge_notation(sequence: str) -> Tuple[str, int]:
    """Parse peptide sequence with charge notation and extract charge state.

    Supports both /charge and trailing number formats.

    Args:
        sequence (str): The peptide sequence that may contain charge notation.

    Returns:
        Tuple[str, int]: A tuple containing (sequence_without_charge, charge_state).
            sequence_without_charge is the sequence with charge notation removed.
            charge_state is the extracted charge state (1 if none found).

    """
    sequence = sequence.strip()

    leading_dot = ""
    if sequence.startswith("."):
        leading_dot = "."
        sequence = sequence[1:]

    # Try /charge format first
    slash_charge_pattern = r"/(\d+)$"
    slash_match = re.search(slash_charge_pattern, sequence)

    if slash_match:
        charge_state = int(slash_match.group(1))
        if 1 <= charge_state <= 20:
            sequence_without_charge = re.sub(slash_charge_pattern, "", sequence)
            return leading_dot + sequence_without_charge, charge_state

    # Try trailing number as charge
    trailing_number_pattern = r"(\d+)$"
    number_match = re.search(trailing_number_pattern, sequence)

    if number_match:
        charge_state = int(number_match.group(1))
        if 1 <= charge_state <= 20:
            sequence_without_charge = re.sub(trailing_number_pattern, "", sequence)
            return leading_dot + sequence_without_charge, charge_state

    return leading_dot + sequence, 1


def parse_sequence_with_mods_and_charge(sequence: str) -> Tuple[str, str, int]:
    """Parse peptide sequence with both modifications and charge notation.

    Args:
        sequence (str): The peptide sequence containing modifications and/or charge notation.

    Returns:
        Tuple[str, str, int]: A tuple containing (clean_sequence, modified_sequence, charge_state).
            clean_sequence is the sequence without modifications.
            modified_sequence is the OpenMS-formatted sequence.
            charge_state is the extracted charge state.

    """
    sequence_no_charge, charge_state = parse_charge_notation(sequence)
    clean_sequence, modified_sequence = parse_square_bracket_modifications(
        sequence_no_charge
    )

    return clean_sequence, modified_sequence, charge_state


def detect_modification_from_sequence(sequence: str) -> str:
    """Detect the primary modification type from a peptide sequence.

    Uses ModificationsDB for accurate mass delta matching.

    Args:
        sequence (str): The peptide sequence to analyze for modifications.

    Returns:
        str: The detected modification name matching dropdown options, or "None" if no modification detected.

    """
    if not re.search(r"[\[\(]", sequence):
        return "None"

    try:
        clean_sequence, openms_sequence = parse_square_bracket_modifications(sequence)
    except Exception:
        return "None"

    if clean_sequence == openms_sequence:
        return "None"

    # Pattern matching for common modifications (converted to OpenMS format)
    modification_patterns = {
        r"\(Oxidation\)": "Oxidation (M)",
        r"\(Carbamidomethyl\)": "Carbamidomethyl (C)",
        r"\(Phospho\)": "Phosphorylation (S/T/Y)",
        r"^\.\(Acetyl\)": "Acetylation (N-term)",
        r"\(Methyl\)": "Methylation (K/R)",
        r"\(Deamidated\)": "Deamidation (N/Q)",
    }

    for pattern, dropdown_name in modification_patterns.items():
        if re.search(pattern, openms_sequence):
            return dropdown_name

    # Check for mass deltas using ModificationsDB
    mass_delta_match = re.search(
        r"\[([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\]", openms_sequence
    )
    if mass_delta_match:
        try:
            mass_delta = float(mass_delta_match.group(1))
            detected_mod = _match_mass_delta_to_modification(mass_delta)
            if detected_mod != "None":
                return detected_mod
        except ValueError:
            pass

    return "None"


def _match_mass_delta_to_modification(
    mass_delta: float, tolerance: float = 0.01
) -> str:
    """Match a mass delta to a known modification using ModificationsDB.

    Args:
        mass_delta (float): The mass delta to match against known modifications.
        tolerance (float): Mass tolerance in Da for matching. Defaults to 0.01.

    Returns:
        str: The dropdown modification name if found, "None" otherwise.

    """
    try:
        mod_db = _get_pyopenms_mod_db()
        poms = _get_pyopenms()

        # modification names and their known mass deltas
        known_mods = {
            "Carbamidomethyl (C)": [57.021464, 57.0214, 57.02, 57.0],
            "Oxidation (M)": [15.994915, 15.9949, 15.99, 16.0],
            "Phosphorylation (S/T/Y)": [79.966331, 79.9663, 79.97, 80.0],
            "Acetylation (N-term)": [42.010565, 42.0106, 42.01, 42.0],
            "Methylation (K/R)": [14.015650, 14.0157, 14.02, 14.0],
            "Deamidation (N/Q)": [0.984016, 0.9840, 0.98, 1.0],
        }

        # directly check known modifications first
        for mod_name, masses in known_mods.items():
            for known_mass in masses:
                if abs(mass_delta - known_mass) <= tolerance:
                    return mod_name

        # if not found, check ModificationsDB
        mod_id_to_dropdown = {
            "Oxidation": "Oxidation (M)",
            "Carbamidomethyl": "Carbamidomethyl (C)",
            "Phospho": "Phosphorylation (S/T/Y)",
            "Acetyl": "Acetylation (N-term)",
            "Methyl": "Methylation (K/R)",
            "Deamidated": "Deamidation (N/Q)",
        }

        for mod_id in mod_id_to_dropdown.keys():
            try:
                mod = mod_db.getModification(mod_id)
                mod_mass = mod.getDiffMonoMass()

                if abs(mass_delta - mod_mass) <= tolerance:
                    return mod_id_to_dropdown[mod_id]

            except Exception:
                continue

    except Exception:
        pass

    return "None"


def parse_proforma_sequence(sequence: str) -> Tuple[str, str, bool]:
    """Parse ProForma-style sequence, trying direct PyOpenMS parsing first.

    Args:
        sequence (str): The ProForma-style peptide sequence to parse.

    Returns:
        Tuple[str, str, bool]: A tuple containing (clean_sequence, converted_sequence, proforma_direct).
            clean_sequence is the sequence without modifications.
            converted_sequence is the converted or original sequence.
            proforma_direct indicates if direct PyOpenMS parsing was successful.

    """
    sequence = sequence.strip()
    if sequence.startswith("."):
        sequence = sequence[1:]

    poms = _get_pyopenms()

    # Try direct PyOpenMS parsing for ProForma-style arbitrary mass shifts
    try:
        test_seq = poms.AASequence.fromString(sequence)

        clean_sequence = re.sub(r"\[([^\]]+)\]", "", sequence)
        return clean_sequence, sequence, True
    except Exception:
        pass

    # Fall back to traditional conversion
    clean_sequence, converted_sequence = parse_square_bracket_modifications(sequence)
    return clean_sequence, converted_sequence, False


def analyze_peptide_sequence(sequence: str) -> SequenceAnalysis:
    """Unified sequence analysis function that detects modifications and charge state.

    Args:
        sequence (str): The peptide sequence to analyze.

    Returns:
        SequenceAnalysis: A dataclass containing analysis results including:
            - modification: Detected modification name
            - modification_detected: Boolean indicating if modification was found
            - charge: Detected or default charge state
            - charge_detected: Boolean indicating if charge was found in sequence
            - is_valid: Boolean indicating if sequence is valid
            - clean_sequence: The sequence without modifications
            - error_message: Error message if validation failed

    """
    analysis = SequenceAnalysis()

    if not sequence or not sequence.strip():
        analysis.is_valid = False
        analysis.error_message = ERROR_MESSAGES["empty_sequence"]
        return analysis

    try:
        _, _, extracted_charge = parse_sequence_with_mods_and_charge(sequence)
        if extracted_charge > 1:
            analysis.charge = extracted_charge
            analysis.charge_detected = True

        detected_modification = detect_modification_from_sequence(sequence)
        if detected_modification != "None":
            analysis.modification = detected_modification
            analysis.modification_detected = True

        is_valid, clean_sequence = validate_peptide_sequence(sequence)
        analysis.is_valid = is_valid
        analysis.clean_sequence = clean_sequence

        if not is_valid:
            analysis.error_message = ERROR_MESSAGES["invalid_amino_acid"]
        elif len(clean_sequence) == 0:
            analysis.error_message = ERROR_MESSAGES["invalid_sequence_length"]
            analysis.is_valid = False

    except Exception as e:
        analysis.is_valid = False
        analysis.error_message = ERROR_MESSAGES["unexpected_error"].format(error=str(e))

    return analysis


def get_cached_modifications():
    """Get supported modifications list for caching.

    Returns:
        list: A list of supported modification names from get_supported_modifications().

    """
    return get_supported_modifications()


def get_cached_examples():
    """Get square bracket examples for caching.

    Returns:
        Dict[str, str]: A dictionary of example sequences and descriptions from get_square_bracket_examples().

    """
    return get_square_bracket_examples()
