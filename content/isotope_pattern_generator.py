import io
import re
from typing import Tuple, Dict, Any, Optional

import plotly.graph_objects as go
import streamlit as st
import pyopenms as oms
import pandas as pd
import numpy as np

from src.common.common import page_setup, show_fig
from src.isotope_pattern import (
    generate_isotope_pattern_from_formula,
    generate_isotope_pattern_from_sequence,
    generate_isotope_pattern_from_oligonucleotide,
    generate_isotope_pattern_from_mass,
)

params = page_setup()

pd.options.plotting.backend = "ms_plotly"

def create_isotope_plot(result_data: Dict[str, Any]) -> go.Figure:
    """Create the isotope pattern plot.
    
    Args:
        result_data (Dict[str, Any]): Results from pattern generation
        
    Returns:
        go.Figure: Plotly figure object
    """
    mzs = result_data["mzs"]
    intensities = result_data["intensities"]
    
    # Create dataframe
    df = pd.DataFrame({
        'mz': mzs,
        'intensity': intensities
    })

    # Color highlights
    df['color'] = 'black'
    df.iloc[np.argmax(df['intensity']), -1] = 'red'
    
    # Plot
    fig = go.Figure()
    fig = df[df['intensity'] != 0].plot(
        x="mz",
        y="intensity",
        kind="spectrum",
        peak_color='color',
        canvas=fig,
        show_plot=False,
        grid=False,
        annotate_top_n_peaks=1
    )
    
    considered = mzs[intensities > (0.001 * max(intensities))]
    fig.update_xaxes(range=[np.min(considered), np.max(considered)])
    fig.update_layout(
        title="Isotopic Envelope",
        xaxis_title="m/z",
        yaxis_title="Intensity"
    )
    
    return fig

# UI Implementation
st.title("📶 Isotopic Pattern Calculator")

st.markdown("""
**Generate theoretical isotopic envelopes** for molecules to understand mass spectrometric signatures and optimize analysis conditions.

This tool calculates isotopic distributions using pyOpenMS, helping you:
- **Predict MS peak patterns** for accurate mass measurements and peak assignment
- **Optimize MS parameters** by understanding peak spacing and intensity distributions
- **Validate experimental data** by comparing observed vs theoretical patterns
- **Design targeted experiments** by predicting isotopic signatures for specific molecules
""")

with st.expander("📚 **Understanding Isotopic Patterns**"):
    st.markdown("""
    **Natural Isotopes:**
    - Elements exist as multiple isotopes with different masses
    - **Carbon**: ¹²C (98.9%) and ¹³C (1.1%) - primary contributor to isotopic patterns
    - **Nitrogen**: ¹⁴N (99.6%) and ¹⁵N (0.4%) - important for peptides and nucleotides
    - **Sulfur**: ³²S (95.0%) and ³⁴S (4.2%) - significant contribution in proteins
    
    **Isotopic Envelope Shape:**
    - **Small molecules**: Simple patterns with M+1, M+2 peaks
    - **Large molecules**: Complex bell-shaped distributions
    - **Pattern width** increases with molecular size due to multiple isotopic combinations
    
    **Input Methods:**
    - **Mass Estimation**: Quick approximation for unknown compounds
    - **Elemental Formula**: Precise calculation for known molecular composition
    - **Peptide/Protein**: Automatic formula calculation from amino acid sequence
    - **Oligonucleotides**: DNA/RNA sequence support with automatic T→U conversion
    
    **Generator Options:**
    - **Coarse Generator**: Fast computation, suitable for most applications
    - **Fine Generator**: High precision for detailed isotopic analysis
    
    **Applications:**
    - **Peak assignment** in high-resolution mass spectrometry
    - **Charge state determination** through isotopic peak spacing
    - **Molecular formula confirmation** by pattern matching
    - **Method development** for accurate mass measurements
    """)

st.markdown("""
**Choose your input method:**
""")

# Input method selection
input_method = st.selectbox(
    "Select Input Method:",
    ["Mass (Da)", "Elemental Formula", "Peptide/Protein Sequence", "Oligonucleotide Sequence"],
    help="Choose how you want to specify your molecule"
)

# Generator selection (only for formula, sequence, and oligonucleotide)
if input_method in ["Elemental Formula", "Peptide/Protein Sequence", "Oligonucleotide Sequence"]:
    use_fine_generator = st.checkbox(
        "Use Fine Isotope Pattern Generator",
        value=False,
        help="""
        - **Coarse Generator** (Default): Faster computation, good for most applications
        - **Fine Generator**: More precise calculations, slower for large molecules
        """
    )
else:
    use_fine_generator = False

col1, col2 = st.columns([1, 1])

with col1:
    result_data = None
    
    if input_method == "Mass (Da)":
        target_mass = st.number_input(
            "Input most abundant/intense peak [Da]:",
            min_value=0.0,
            value=20000.0,
            help="""
            The most intense (or most abundant) peak is the isotope peak 
            with the highest abundance in the protein's mass spectrum. It 
            represents the most common isotopic composition and serves as 
            the reference point for reconstructing the full isotopic envelope.
            """
        )
        
        if st.button('Compute Isotopic Envelope'):
            with st.spinner('Computing from mass...'):
                result_data = generate_isotope_pattern_from_mass(target_mass)
    
    elif input_method == "Elemental Formula":
        formula_input = st.text_input(
            "Elemental Formula:",
            value="C100H150N26O30S1",
            help="""
            Enter the molecular formula using standard notation.
            Examples: C100H150N26O30S1, C6H12O6, C43H66N12O12S2
            """
        )
        
        if st.button('Compute Isotopic Envelope'):
            generator_type = "fine" if use_fine_generator else "coarse"
            with st.spinner(f'Computing from formula using {generator_type} generator...'):
                result_data = generate_isotope_pattern_from_formula(formula_input, use_fine_generator)
    
    elif input_method == "Peptide/Protein Sequence":
        sequence_input = st.text_area(
            "Amino Acid Sequence:",
            value="PEPTIDE",
            height=100,
            help="""
            Enter the peptide or protein sequence using single-letter amino acid codes.
            Examples: PEPTIDE, MKLNFSLRLRR, ACDEFGHIKLMNPQRSTVWY
            """
        )
        
        if st.button('Compute Isotopic Envelope'):
            generator_type = "fine" if use_fine_generator else "coarse"
            with st.spinner(f'Computing from sequence using {generator_type} generator...'):
                result_data = generate_isotope_pattern_from_sequence(sequence_input, use_fine_generator)
    
    elif input_method == "Oligonucleotide Sequence":
        oligonucleotide_input = st.text_area(
            "Nucleotide Sequence:",
            value="AUCGAUCG",
            height=100,
            help="""
            RNA sequence using standard nucleotide codes.
            Valid nucleotides: A (adenine), C (cytosine), G (guanine), U (uracil), N (any)
            Examples: AUCGAUCG, AAAUUUCCCGGG
            """
        )
        
        if st.button('Compute Isotopic Envelope'):
            generator_type = "fine" if use_fine_generator else "coarse"
            with st.spinner(f'Computing from oligonucleotide using {generator_type} generator...'):
                result_data = generate_isotope_pattern_from_oligonucleotide(oligonucleotide_input, use_fine_generator)

with col2:
    if result_data:
        if result_data["success"]:
            # Display results
            st.write(f"**Source:** {result_data['source_type']}")
            st.write(f"**Input:** {result_data['input_value']}")
            if "generator" in result_data:
                st.write(f"**Generator:** {result_data['generator']} Isotope Pattern Generator")
            if "formula" in result_data:
                st.write(f"**Molecular Formula:** {result_data['formula']}")
            if "sequence" in result_data:
                st.write(f"**Sequence:** {result_data['sequence']}")
                # Show conversion info for oligonucleotides
                if "original_sequence" in result_data and "conversion_note" in result_data:
                    if result_data["conversion_note"]:
                        st.write(f"**Original Sequence:** {result_data['original_sequence']}")
                        st.info(f"DNA sequence converted to RNA for processing{result_data['conversion_note']}")
            st.write(f"**Monoisotopic Mass:** {result_data['monoisotopic_mass']:.5f} Da")
            st.write(f"**Average Mass:** {result_data['average_mass']:.5f} Da")
        else:
            st.error(f"Error: {result_data['error']}")

# Display plot and download options
if result_data and result_data["success"]:
    # Create and display plot
    fig = create_isotope_plot(result_data)
    show_fig(fig, 'Isotopic Envelope')
    
    # Prepare download data
    df_out = pd.DataFrame({
        'mz': result_data["mzs"],
        'intensity': result_data["intensities"],
        'color': ['red' if i == np.argmax(result_data["intensities"]) else 'black' 
                 for i in range(len(result_data["mzs"]))]
    })
    
    # Create download files
    tsv_buffer = io.StringIO()
    df_out.to_csv(tsv_buffer, sep='\t', index=False)
    tsv_buffer.seek(0)
    tsv_file = tsv_buffer.getvalue()
    
    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:
        df_out.to_excel(writer, index=False, sheet_name="MS Data")
    xlsx_buffer.seek(0)
    xlsx_file = xlsx_buffer.getvalue()
    
    # Download buttons
    tsv_col, excel_col, _ = st.columns(3)
    
    @st.fragment
    def tsv_download():
        st.download_button(
            label="Download TSV file",
            file_name=f'Isotopic_Envelope_{result_data["source_type"].replace("/", "_").replace(" ", "_")}.tsv',
            data=tsv_file
        )
    
    with tsv_col:
        tsv_download()
    
    @st.fragment
    def xlsx_download():
        st.download_button(
            label="Download Excel file",
            file_name=f'Isotopic_Envelope_{result_data["source_type"].replace("/", "_").replace(" ", "_")}.xlsx',
            data=xlsx_file
        )
    
    with excel_col:
        xlsx_download()