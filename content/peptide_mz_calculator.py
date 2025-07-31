"""
Peptide m/z Calculator App.
"""

import streamlit as st
import pandas as pd
from pathlib import Path

from src.common.common import page_setup, v_space

# Import backend functions
from src.peptide_mz_calculator import (
    calculate_peptide_mz_range,
    validate_sequence,
)

# Page setup
page_setup(page="main")

# Hero section & logo
col1, col2, col3 = st.columns([0.5, 2, 1])
with col2:
    st.markdown(
        """
    <div style="text-align: center; padding: 0.5rem 0;">
        <h1 style="font-size: 2rem; margin-bottom: 0.2rem;">⚖️ Peptide m/z Calculator</h1>
        <p style="font-size: 1rem; color: #666; margin-bottom: 0.5rem;">
            Calculate theoretical mass-to-charge ratios (m/z) for peptides with and without modifications.
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

# Description
st.markdown(
    """
**Calculate precise theoretical m/z values** for peptides.

"""
)

# Expandable help sections
with st.expander("📚 **Understanding AASequence Format**"):
    st.markdown("""

    **💡 Format Tips:**
    - Use parentheses for modifications: `(Oxidation)`, `(Carbamidomethyl)`
    - Use dots for terminal modifications: `.(Acetyl)`, `(Amidated).`
    - Use square brackets for mass deltas: `[+15.995]`, `[-18.010]`
    - UNIMOD format: `[UNIMOD:4]` for standardized modifications

    **Examples:**
    - `PEPTIDE`: Basic amino acid sequence
    - `M(Oxidation)PEPTIDE`: Methionine oxidation modification
    - `C(Carbamidomethyl)PEPTIDE`: Carbamidomethyl cysteine modification
    - `.(Acetyl)PEPTIDE`: N-terminal acetylation
    - `PEPTIDE(Amidated).`: C-terminal amidation
    - `PEPTIDE[+15.995]`: Mass delta modification
    - `M[+15.994915]PEPTIDE`: Specific mass delta on methionine
    - `ALSSC[UNIMOD:4]VVDEEQDVER`: UNIMOD modification notation
    - `M(Oxidation)PEPTIDE/3`: Modified sequence with charge state
    - `PEPS(Phospho)TIDE`: Phosphorylation modification
    - `.(Acetyl)M(Oxidation)PEPTIDE`: Multiple modifications

    """)

    

st.markdown("---")

# Input section
col1_input, col2_input = st.columns([3, 1])

with col1_input:
    # Sequence input
    sequence_input = st.text_input(
        "Peptide Sequence",
        value="M(Oxidation)PEPTIDE",
        help="""Enter peptide sequence in AASequence format. Examples:
        • PEPTIDE - Basic sequence
        • M(Oxidation)PEPTIDE - Oxidized methionine
        • C(Carbamidomethyl)PEPTIDE - Carbamidomethyl cysteine
        • .(Acetyl)PEPTIDE - N-terminal acetylation""",
        placeholder="e.g., M(Oxidation)PEPTIDE, C(Carbamidomethyl)PEPTIDE",
    )

with col2_input:
    # Charge range inputs
    st.markdown("**Charge State Range**")

    default_charge = 2

    charge_col1, charge_col2 = st.columns(2)
    with charge_col1:
        min_charge = st.number_input(
            "Min", 
            min_value=1, 
            max_value=20, 
            value=default_charge,
            step=1
        )
    with charge_col2:
        max_charge = st.number_input(
            "Max", 
            min_value=1, 
            max_value=20, 
            value=min(default_charge + 2, 6),
            step=1
        )
    
    # Ensure valid range
    if min_charge > max_charge:
        st.error("Min charge must be ≤ Max charge")
        min_charge = max_charge

# Calculate button
calculate_btn = st.button(
    "🧮 Calculate m/z", 
    type="primary", 
    use_container_width=True
)

st.markdown("---")

# Results section
if calculate_btn:
    if not sequence_input.strip():
        st.error("Please enter a peptide sequence.")
    else:
        # Validate sequence
        is_valid, error_msg = validate_sequence(sequence_input)
        
        if not is_valid:
            st.error(f"Invalid sequence: {error_msg}")
        else:
            try:
                with st.spinner("Calculating m/z ratios..."):
                    results = calculate_peptide_mz_range(
                        sequence_input, 
                        (min_charge, max_charge)
                    )
                
                st.success("✅ Calculation Complete!")
                
                # Results display
                result_col1, result_col2 = st.columns(2)
                
                with result_col1:
                    st.markdown("### 📊 m/z Results")
                    
                    charge_results = results.get("charge_results", {})
                    charge_states = sorted(charge_results.keys())
                    
                    # Display results
                    if len(charge_states) <= 5:
                        # Simple list for few charge states
                        for charge in charge_states:
                            charge_data = charge_results[charge]
                            mz_value = charge_data['mz_ratio']
                            st.markdown(f"**Charge +{charge}:** {mz_value:.6f}")
                    else:
                        # Table for many charge states
                        table_data = []
                        for charge in charge_states:
                            charge_data = charge_results[charge]
                            table_data.append({
                                "Charge": f"+{charge}",
                                "m/z": f"{charge_data['mz_ratio']:.6f}"
                            })
                        
                        df = pd.DataFrame(table_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    st.markdown(f"**Monoisotopic Mass:** {results['monoisotopic_mass']:.6f} Da")
                
                with result_col2:
                    st.markdown("### 🧪 Sequence Information")
                    st.markdown(f"**Input Sequence:** {sequence_input}")
                    st.markdown(f"**Standardized Sequence:** {results['modified_sequence']}")
                    st.markdown(f"**Molecular Formula:** {results['molecular_formula']}")
                    st.markdown(f"**Length:** {results['sequence_length']} amino acids")
                
                # Additional details
                with st.expander("📋 Additional Details"):
                    # Amino acid composition
                    aa_composition = results["aa_composition"]
                    if aa_composition:
                        st.markdown("**Amino Acid Composition:**")
                        composition_text = ", ".join([
                            f"{aa}: {count}"
                            for aa, count in sorted(aa_composition.items())
                        ])
                        st.markdown(composition_text)
                        
            except Exception as e:
                st.error(f"Calculation error: {str(e)}")
                
                st.markdown("""
                **Common Issues:**
                - Use correct AASequence format: `M(Oxidation)PEPTIDE`
                - Check modification names: `(Carbamidomethyl)`, `(Oxidation)`
                - Verify amino acid codes (standard 20 + X, U)
                - Use dots for terminal mods: `.(Acetyl)PEPTIDE`
                """)

# About section
st.markdown("---")
with st.expander("ℹ️ **About This Peptide m/z Calculator**"):
    st.markdown("""
    **AASequence Format Support:**
    - Uses PyOpenMS `AASequence.fromString()` directly
    - No complex parsing or format conversion
    - Native support for modifications and charge notation
    - Standardized output format
    
    **Supported Amino Acids:**
    Standard 20 amino acids (A, R, N, D, C, E, Q, G, H, I, L, K, M, F, P, S, T, W, Y, V) plus X (any) and U (selenocysteine)
    
    **Modification Format:**
    - Named modifications: `(Oxidation)`, `(Carbamidomethyl)`, `(Phospho)`
    - Terminal modifications: `.(Acetyl)PEPTIDE`, `PEPTIDE(Amidated).`
    - Mass deltas: `[+15.994915]`, `[-18.010565]`
    - UNIMOD notation: `[UNIMOD:4]`, `[UNIMOD:35]`
    
    """)
