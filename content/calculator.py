"""
Main page for the Peptide m/z Calculator App.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
import streamlit as st
import pandas as pd

from src.common.common import page_setup, v_space

# importing backend functions for peptide calculations
from src.peptide_calculator import (
    validate_peptide_sequence,
    apply_modification,
    calculate_peptide_mz,
    calculate_peptide_mz_range,
    get_supported_modifications,
    get_square_bracket_examples,
    parse_square_bracket_modifications,
    parse_sequence_with_mods_and_charge,
    detect_modification_from_sequence,
    analyze_peptide_sequence,
    SequenceAnalysis,
    get_cached_modifications,
    get_cached_examples,
    ERROR_MESSAGES,
)


# Configuration constants
class Config:
    DEFAULT_CHARGE = 2
    MAX_CHARGE = 100
    MIN_CHARGE = 1
    DEFAULT_SEQUENCE = "PEPTIDEC[+57.021464]"
    VALID_AMINO_ACIDS = "ARNDCEQGHILKMFPSTWYV X U"


@st.cache_data(ttl=3600)
def cached_modifications():
    """Cache supported modifications to improve performance"""
    return get_cached_modifications()


@st.cache_data(ttl=3600)
def cached_examples():
    """Cache square bracket examples to improve performance"""
    return get_cached_examples()


# Initialize session state for better state management
if "last_sequence" not in st.session_state:
    st.session_state["last_sequence"] = ""
if "calculation_in_progress" not in st.session_state:
    st.session_state["calculation_in_progress"] = False
if "last_analysis" not in st.session_state:
    st.session_state["last_analysis"] = SequenceAnalysis()

# Page setup
page_setup(page="main")

# Hero section && logo
col1, col2, col3 = st.columns([0.5, 2, 1])
with col2:
    st.markdown(
        """
    <div style="text-align: center; padding: 0.5rem 0;">
        <h1 style="font-size: 2rem; margin-bottom: 0.2rem;">👋 Welcome to the Peptide M/Z Calculator</h1>
        <p style="font-size: 1rem; color: #666; margin-bottom: 0.5rem;">
            Theoretical mass-to-charge ratio calculations for proteomics research
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )
with col3:
    st.image("assets/openms_transparent_bg_logo.svg", width=150)

# working explanation
st.markdown(
    """
This calculator determines the mass-to-charge (m/z) ratio of peptides based on their amino acid sequence, 
charge state, and modifications. It uses the pyOpenMS library for theoretical mass spectrometry calculations.
"""
)

with st.expander("❓ How to use", expanded=False):
    st.markdown(
        """
**How to use:**
1.  **Enter Sequence:** Type your peptide sequence (e.g., `PEPTIDE`).
2.  **Add Static Modifications (Optional):** Include static modifications in brackets (e.g., `M[Oxidation]`, `C[+57.021464]`) or UNIMOD notation (e.g., `C[UNIMOD:4]`).
3.  **Specify Charge (Optional):** Add a slash and the charge number to your sequence (e.g., `PEPTIDE/2`).
4.  **Auto-Detect:** Modifications and charge are automatically recognized.
5.  **Calculate:** Click "Calculate m/z".
        """
    )

# Advanced notation
with st.expander("📝 Advanced Notation Examples", expanded=False):
    st.markdown("**Supported sequence formats:**")
    examples = cached_examples()

    modification_examples = {}
    charge_examples = {}
    unimod_examples = {}

    for seq, desc in examples.items():
        if "UNIMOD" in seq:
            unimod_examples[seq] = desc
        elif any(charge in seq for charge in ["/2", "/3", "2", "3"]):
            charge_examples[seq] = desc
        else:
            modification_examples[seq] = desc

    st.markdown("**🧬 UNIMOD Notation (Standardized):**")
    for seq, desc in unimod_examples.items():
        st.markdown(f"• {seq} - {desc}")

    st.markdown("**🎯 ProForma Arbitrary Mass Shifts (NEW!):**")
    st.markdown("• `LGEPDYIPSQQDILLAR[+42.0106]` - Peptide with +42.0106 Da mass shift")
    st.markdown("• `EM[+15.9949]EVEES[-79.9663]PEK` - Multiple arbitrary mass deltas")
    st.markdown("• `PEPTIDE[+14.0157]` - Methylation-like mass shift")
    st.markdown("• `PEPTIDES[+79.9663]` - Phosphorylation-like mass shift")

    st.markdown("**🔬 Modification Notation:**")
    for seq, desc in modification_examples.items():
        st.markdown(f"• {seq} - {desc}")

    st.markdown("**⚡ Charge State Notation:**")
    for seq, desc in charge_examples.items():
        st.markdown(f"• {seq} - {desc}")

    st.markdown(
        """
    **💡 Pro Tips:**
    - ProForma arbitrary mass shifts like `[+42.0106]` are supported!
    - UNIMOD notation provides standardized modification references
    - Leading dots (.) are automatically handled and represent N-terminus
    - Combine modification and charge notation: M[UNIMOD:35]PEPTIDE/2
    - Case-insensitive UNIMOD IDs: [unimod:4] = [UNIMOD:4]
    - Auto-detection updates both dropdown and charge fields
    
    **Square Bracket Tips:**
    - Use arbitrary mass deltas: `[+15.9949]`, `[-79.9663]`, `[+367.0537]`
    - Use [ModificationName] after amino acids: M[Oxidation]
    - For N-terminal: [Acetyl]PEPTIDE or .[Acetyl]PEPTIDE
    - For C-terminal: PEPTIDE[Amidated] or PEPTIDE.[Amidated]
    - Multiple modifications: .[Acetyl]M[Oxidation]PEPTIDE[Amidated]
    - **Auto-updates modification dropdown** for better user experience
    
    **Charge Notation Tips:**
    - Add /charge at the end: PEPTIDE/2, SEQUENCE/3
    - Add trailing number: PEPTIDE2, SEQUENCE3
    - **Auto-updates charge state input field** for better user experience
    - Can combine with modifications: M[Oxidation]PEPTIDE/2 or M[Oxidation]PEPTIDE3
    """
    )

st.markdown("---")

col1_calc, col2_calc = st.columns([2, 1])

with col1_calc:
    # Input with sample data
    # Corrected extra parenthesis in help text
    peptide_sequence = st.text_input(
        "Peptide Sequence",
        value=Config.DEFAULT_SEQUENCE,
        help="""Enter the peptide sequence. Examples:
        • PEPTIDE - Basic sequence
        • M[Oxidation]PEPTIDE - Named modification
        • C[+57.021464]PEPTIDE - Mass delta
        • PEPTIDE/2 - With charge notation
        • [Acetyl]PEPTIDE - N-terminal modification
        • M[UNIMOD:35]PEPTIDE - UNIMOD notation""",
        placeholder="e.g., PEPTIDE, M[Oxidation]PEPTIDE, C[+57.021464]PEPTIDE, PEPTIDE/2",
    )

    # analyze sequence only if it has changed to avoid unnecessary processing
    analysis = SequenceAnalysis()
    if peptide_sequence.strip() and peptide_sequence != st.session_state.last_sequence:
        analysis = analyze_peptide_sequence(peptide_sequence)
        st.session_state.last_sequence = peptide_sequence
        st.session_state.last_analysis = analysis
    elif peptide_sequence.strip():
        # Use cached analysis if sequence hasn't changed
        analysis = st.session_state.last_analysis

    # Display info if modification is detected from sequence
    if analysis.modification_detected:
        st.info(
            f"🧪 Modification '{analysis.modification}' detected from sequence notation"
        )

    # Get the raw list of modifications from the cache
    raw_modification_list = cached_modifications()

    # Filter to only include specific modifications
    allowed_modifications = [
        "Carbamidomethyl (C)",
        "Acetylation (N-term)",
    ]
    filtered_modifications = [
        mod for mod in raw_modification_list if mod in allowed_modifications
    ]

    modification_options = list(set(filtered_modifications))

    # Modification selection with auto-updated value
    default_modifications = []
    if analysis.modification_detected and analysis.modification in modification_options:
        default_modifications = [analysis.modification]
    elif (
        not analysis.modification_detected
        and "Carbamidomethyl (C)" in modification_options
    ):
        default_modifications = ["Carbamidomethyl (C)"]

    st.markdown("**Static Modifications (Optional)**")
    st.caption("Select one or more common modifications to apply to the peptide.")

    modifications = []

    col1, col2 = st.columns(2)

    with col1:
        carbamidomethyl_default = "Carbamidomethyl (C)" in default_modifications
        carbamidomethyl_selected = st.checkbox(
            "Carbamidomethyl (C)",
            value=carbamidomethyl_default,
            key="carbamidomethyl_checkbox",
        )
        if carbamidomethyl_selected:
            modifications.append("Carbamidomethyl (C)")

    with col2:
        if "Acetylation (N-term)" in modification_options:
            acetylation_default = "Acetylation (N-term)" in default_modifications
            acetylation_selected = st.checkbox(
                "Acetylation (N-term)",
                value=acetylation_default,
                key="acetylation_checkbox",
            )
            if acetylation_selected:
                modifications.append("Acetylation (N-term)")

with col2_calc:
    # Display info if charge is detected from sequence
    if analysis.charge_detected:
        st.info(f"🔗 Charge state {analysis.charge} detected from sequence notation")

    if analysis.charge_detected:
        charge_range = st.slider(
            "Charge State Range",
            min_value=Config.MIN_CHARGE,
            max_value=Config.MAX_CHARGE,
            value=(analysis.charge, analysis.charge),
            step=1,
            help="Charge state detected from sequence notation. Range is fixed to detected value.",
            key="charge_input",
        )
    else:
        charge_range = st.slider(
            "Charge State Range",
            min_value=Config.MIN_CHARGE,
            max_value=Config.MAX_CHARGE,
            value=(2, 4),
            step=1,
            help="Select the charge state range to calculate m/z ratios for multiple charge states.",
            key="charge_input",
        )

    calculate_button = st.button(
        (
            "🧮 Calculate m/z"
            if not st.session_state.calculation_in_progress
            else "⏳ Calculating..."
        ),
        type="primary",
        use_container_width=True,
        disabled=st.session_state.calculation_in_progress,
    )

st.markdown("---")

if calculate_button:
    if not peptide_sequence.strip():
        st.error(ERROR_MESSAGES["empty_sequence"])
    else:
        st.session_state.calculation_in_progress = True

        current_analysis = analyze_peptide_sequence(peptide_sequence)

        if not current_analysis.is_valid:
            st.error(
                current_analysis.error_message or ERROR_MESSAGES["invalid_amino_acid"]
            )
            st.session_state.calculation_in_progress = False
        elif len(current_analysis.clean_sequence) == 0:
            st.error(ERROR_MESSAGES["invalid_sequence_length"])
            st.session_state.calculation_in_progress = False
        else:
            try:
                with st.spinner("Calculating m/z ratios..."):
                    results = calculate_peptide_mz_range(
                        peptide_sequence, charge_range, modifications
                    )

                st.success("✅ Calculation Successful!")

                # result columns
                result_col1, result_col2 = st.columns(2)

                with result_col1:
                    st.markdown("### 📊 m/z Results")

                    charge_results = results.get("charge_results", {})
                    charge_states = sorted(charge_results.keys())

                    if len(charge_states) <= 5:
                        for charge_state in charge_states:
                            charge_data = charge_results[charge_state]
                            charge_display = f"**Charge +{charge_state}:** {charge_data['mz_ratio']:.6f}"
                            if (
                                charge_data.get("charge_source")
                                == "From sequence notation"
                            ):
                                charge_display += " 🔗"
                            st.markdown(charge_display)
                    else:
                        st.markdown("**m/z Values by Charge State:**")

                        table_data = []
                        for charge_state in charge_states:
                            charge_data = charge_results[charge_state]
                            table_data.append(
                                {
                                    "Charge": f"+{charge_state}",
                                    "m/z": f"{charge_data['mz_ratio']:.6f}",
                                }
                            )

                        df = pd.DataFrame(table_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)

                        if len(charge_states) > 20:
                            st.caption(
                                f"Showing {len(charge_states)} charge states (scroll table to see all)"
                            )

                    st.markdown(
                        f"**Monoisotopic Mass:** {results['monoisotopic_mass']:.6f} Da (uncharged)"
                    )

                with result_col2:
                    st.markdown("### 🧪 Sequence Information")
                    st.markdown(
                        f"**Original Sequence:** {results['original_sequence']}"
                    )
                    st.markdown(
                        f"**Modified Sequence:** {results['modified_sequence']}"
                    )
                    st.markdown(
                        f"**Molecular Formula:** {results['molecular_formula']}"
                    )

                # additional info
                with st.expander("📋 Additional Information"):
                    st.markdown(
                        f"**Sequence Length:** {results['sequence_length']} amino acids"
                    )
                    st.markdown(f"**Applied Modification:** {results['modification']}")
                    if results.get("charge_source"):
                        st.markdown(f"**Charge Source:** {results['charge_source']}")

                    aa_composition = results["aa_composition"]
                    if aa_composition:
                        st.markdown("**Amino Acid Composition:**")
                        composition_text = ", ".join(
                            [
                                f"{aa}: {count}"
                                for aa, count in sorted(aa_composition.items())
                            ]
                        )
                        st.markdown(f"{composition_text}")

            except ValueError as e:
                st.error(ERROR_MESSAGES["calculation_error"].format(error=str(e)))
            except Exception as e:
                st.error(ERROR_MESSAGES["unexpected_error"].format(error=str(e)))

                st.markdown(
                    """
                **Common issues:**
                - Invalid amino acid codes in sequence
                - Unsupported modification syntax
                - Invalid charge state
                - Modification not recognized by OpenMS
                
                **Troubleshooting:**
                - Try without modifications first
                - Use only standard amino acid codes
                - Check sequence for special characters
                """
                )
            finally:
                st.session_state.calculation_in_progress = False

# info ( will shift most of this part in documentation later on kept it for now , because was useful during development )
st.markdown("---")
with st.expander("ℹ️ About this Calculator"):
    st.markdown(
        f"""
    **Supported Amino Acids:**
    {', '.join(Config.VALID_AMINO_ACIDS)}
    
    **Modification Formats:**
    - **Square brackets:** M[Oxidation]PEPTIDE, [Acetyl]PEPTIDE, PEPTIDE[Amidated]
    - **UNIMOD notation:** ALSSC[UNIMOD:4]VVDEEQDVER, M[UNIMOD:35]PEPTIDE (standardized IDs)
    - **Mass deltas:** C[+57.021464]PEPTIDE, M[+15.994915]PEPTIDE
    - **ProForma arbitrary mass shifts:** LGEPDYIPSQQDILLAR[+42.0106], EM[+15.9949]EVEES[-79.9663]PEK
    - **Scientific notation:** PEPTIDE[+1.5e2], SEQUENCE[-5.25e1] (ProForma standard)
    - **Leading dot support:** .LLVLPKFGM[+15.9949]LMLGPDDFR (N-terminal indicator)
    - **Dropdown selection:** Applies to all applicable residues in the sequence
    - **Auto-detection:** Dropdown auto-updates when modifications are detected
    - **OpenMS notation:** Also supports native AA(ModificationName) format
    - **N-terminal:** [Acetyl]PEPTIDE or .[Acetyl]PEPTIDE
    - **C-terminal:** PEPTIDE.[Amidated] (dot required for true C-terminal mods)
    
    **Charge Notation:**
    - **Slash format:** PEPTIDE/2, SEQUENCE/3, M[Oxidation]PEPTIDE/2
    - **Trailing number:** PEPTIDE2, SEQUENCE3, QVVPC[+57.021464]STSER3
    - **Auto-detection:** Input field auto-updates when charge is detected
    - Can be combined with any modification format
    
    **Calculation Method:**
    - Uses pyOpenMS AASequence class for theoretical mass calculations
    - Monoisotopic masses are used for all calculations
    - m/z ratio is calculated as: (Monoisotopic Mass + Charge x Proton Mass) / Charge
    
    **References:**
    - pyOpenMS Documentation: https://pyopenms.readthedocs.io/
    - OpenMS Website : https://www.openms.de/
    """
    )
