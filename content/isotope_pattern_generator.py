import io
import re
from typing import Tuple, Dict, Any, Optional

import plotly.graph_objects as go
import streamlit as st
import pyopenms as oms
import pandas as pd
import numpy as np

from src.common.common import page_setup, show_fig

params = page_setup()

# Initialize pattern generators
coarse_pattern_generator = oms.CoarseIsotopePatternGenerator()
fine_pattern_generator = oms.FineIsotopePatternGenerator()

pd.options.plotting.backend = "ms_plotly"

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
    """Validate an oligonucleotide (DNA/RNA) sequence and convert DNA to RNA.
    
    Args:
        sequence_str (str): The nucleotide sequence
        
    Returns:
        Tuple[bool, str, Optional[str]]: (is_valid, error_message, rna_sequence)
    """
    try:
        # Clean the sequence
        sequence_str = sequence_str.strip().upper()
        if not sequence_str:
            return False, "Sequence cannot be empty", None
            
        # Remove common formatting characters (spaces, numbers, newlines)
        clean_sequence = re.sub(r'[^ACGTUN]', '', sequence_str)
        
        if not clean_sequence:
            return False, "No valid nucleotide letters found", None
            
        # Validate nucleotides (A, C, G, T, U for RNA, N for any)
        valid_nucleotides = set("ACGTUN")
        invalid_chars = [nt for nt in clean_sequence if nt not in valid_nucleotides]
        
        if invalid_chars:
            invalid_list = ", ".join(sorted(set(invalid_chars)))
            return False, f"Invalid nucleotide(s): {invalid_list}. Valid nucleotides: A, C, G, T, U, N", None
        
        # Convert DNA to RNA (T -> U) since pyOpenMS NASequence only supports RNA
        rna_sequence = clean_sequence.replace('T', 'U')
            
        return True, "", rna_sequence
        
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
st.title("Isotopic Envelope Calculator")

st.markdown("""
Calculate isotopic patterns from four different input types:
- **Mass (Da)**: Estimate pattern from molecular weight
- **Elemental Formula**: Precise calculation from molecular composition
- **Peptide/Protein Sequence**: Calculate from amino acid sequence
- **Oligonucleotide Sequence**: Calculate from DNA/RNA nucleotide sequence
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
            value="ATCGATCG",
            height=100,
            help="""
            Enter the DNA or RNA sequence using standard nucleotide codes.
            Valid nucleotides: A (adenine), T (thymine), C (cytosine), G (guanine), U (uracil), N (any)
            Examples: ATCGATCG, AAAUUUCCCGGG, ATCGNTCG
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