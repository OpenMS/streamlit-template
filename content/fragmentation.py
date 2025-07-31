import io
import re
from typing import Tuple, Dict, Any, Optional, List

import plotly.graph_objects as go
import streamlit as st
import pyopenms as oms
import pandas as pd
import numpy as np

from src.common.common import page_setup, show_fig

params = page_setup()

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
    param.setValue("add_first_prefix_ion", "false")
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
    import re
    
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

def create_fragmentation_plot(result_data: Dict[str, Any]) -> go.Figure:
    """Create the fragmentation spectrum plot.
    
    Args:
        result_data (Dict[str, Any]): Results from spectrum generation
        
    Returns:
        go.Figure: Plotly figure object
    """
    df = result_data["fragments"]
    print(df)
    # Color map for ion types
    color_map = {
        'a': '#FF6B6B',  # Red
        'b': '#4ECDC4',  # Teal
        'c': '#45B7D1',  # Blue
        'x': '#96CEB4',  # Green
        'y': '#FFEAA7',  # Yellow
        'z': '#DDA0DD',  # Plum
        'unknown': '#95A5A6'  # Gray
    }
    
    fig = go.Figure()
    
    # Add traces for each ion type
    for ion_type in df['ion_type'].unique():
        ion_data = df[df['ion_type'] == ion_type]
        
        fig.add_trace(go.Scatter(
            x=ion_data['mz'],
            y=ion_data['intensity'],
            mode='markers+lines',
            name=ION_TYPES.get(ion_type, {}).get('name', ion_type),
            marker=dict(
                color=color_map.get(ion_type, '#95A5A6'),
                size=8
            ),
            line=dict(width=0),
            text=ion_data['annotation'],
            hovertemplate="<b>%{text}</b><br>" +
                         "m/z: %{x:.4f}<br>" +
                         "Intensity: %{y:.1e}<br>" +
                         "<extra></extra>"
        ))
        
        # Add stem lines
        for _, row in ion_data.iterrows():
            fig.add_shape(
                type="line",
                x0=row['mz'], y0=0,
                x1=row['mz'], y1=row['intensity'],
                line=dict(color=color_map.get(ion_type, '#95A5A6'), width=2)
            )
    
    fig.update_layout(
        title=f"Theoretical Fragment Spectrum: {result_data['sequence']}",
        xaxis_title="m/z",
        yaxis_title="Relative Intensity",
        hovermode='closest',
        showlegend=True,
        height=500
    )
    
    return fig

# UI Implementation
st.title("💥 Peptide Fragmentation Calculator")

st.markdown("""
Generate theoretical fragment ion spectra for peptide sequences using pyOpenMS.
Select ion types and charge states to customize the fragmentation pattern.
""")

# Documentation section
with st.expander("📚 Documentation", expanded=False):
    st.markdown("""
    ## Overview
    
    The Peptide Fragmentation Calculator generates theoretical fragment ion spectra for peptide sequences using the
    powerful **pyOpenMS** library. This tool simulates what would happen when a peptide is fragmented in a mass
    spectrometer, providing essential information for mass spectrometry analysis and peptide identification.
    
    ## Peptide Fragmentation Theory
    
    When peptides are subjected to collision-induced dissociation (CID) or higher-energy collisional dissociation (HCD)
    in a mass spectrometer, they fragment primarily along the peptide backbone. The fragmentation produces two series
    of ions:
    
    - **N-terminal ions**: Contain the N-terminus of the original peptide
    - **C-terminal ions**: Contain the C-terminus of the original peptide
    
    ### Ion Types Explained
    
    #### N-terminal Fragment Ions
    - **a-ions**: Result from cleavage of the C-N bond with loss of CO (carbonyl group)
      - Formula: [M + H - CO]⁺ where M is the N-terminal fragment mass
      - Less commonly observed in standard CID conditions
    
    - **b-ions**: Result from cleavage of the peptide bond (amide bond)
      - Formula: [M + H]⁺ where M is the N-terminal fragment mass
      - Most abundant N-terminal ions in CID spectra
    
    - **c-ions**: Result from cleavage of the N-Cα bond with retention of NH₃
      - Formula: [M + H + NH₃]⁺ where M is the N-terminal fragment mass
      - More common in ETD (electron transfer dissociation) conditions
    
    #### C-terminal Fragment Ions
    - **x-ions**: Result from cleavage of the N-Cα bond with addition of CO
      - Formula: [M + H + CO - H]⁺ where M is the C-terminal fragment mass
      - Less commonly observed
    
    - **y-ions**: Result from cleavage of the peptide bond with addition of H₂O
      - Formula: [M + H + H₂O]⁺ where M is the C-terminal fragment mass
      - Most abundant C-terminal ions in CID spectra
    
    - **z-ions**: Result from cleavage of the N-Cα bond with loss of NH₂
      - Formula: [M + H - NH₂]⁺ where M is the C-terminal fragment mass
      - More common in ETD conditions
    
    ## Usage Instructions
    
    ### 1. Enter Peptide Sequence
    - Use standard single-letter amino acid codes (A, C, D, E, F, G, H, I, K, L, M, N, P, Q, R, S, T, V, W, Y)
    - Extended codes (X, U) are also supported
    - Minimum sequence length: 2 amino acids
    - Example: `PEPTIDE`, `SAMPLESEQUENCE`, `ACDEFGHIK`
    
    ### 2. Select Ion Types
    - Choose which fragment ion types to include in the spectrum
    - **Recommended for CID/HCD**: b-ions and y-ions (default selection)
    - **For ETD analysis**: Add c-ions and z-ions
    - **Comprehensive analysis**: Select all ion types
    
    ### 3. Choose Charge States
    - Select the charge states to consider (1+ to 5+)
    - **Typical choice**: 1+ and 2+ for most peptides
    - **For longer peptides**: Include higher charge states (3+, 4+)
    - Higher charge states produce fragments at lower m/z values
    
    ### 4. Interpret Results
    
    #### Spectrum Plot
    - **X-axis**: m/z (mass-to-charge ratio)
    - **Y-axis**: Relative intensity (theoretical, normalized)
    - **Colors**: Different colors represent different ion types
    - **Hover**: Shows detailed information for each peak
    
    #### Fragment Table
    - **Ion Type**: The type of fragment ion (a, b, c, x, y, z)
    - **Fragment**: The fragment number (position from terminus)
    - **Charge**: The charge state of the fragment
    - **m/z**: The theoretical mass-to-charge ratio
    - **Sequence**: The amino acid sequence of the fragment
    
    ## Technical Details
    
    ### Algorithm
    - Uses pyOpenMS `TheoreticalSpectrumGenerator` class
    - Calculates exact monoisotopic masses for fragments
    - Applies ion-type specific mass corrections
    - Supports multiple charge states simultaneously
    
    ### Mass Calculations
    The theoretical m/z values are calculated using:
    ```
    m/z = (fragment_mass + ion_type_correction + charge × proton_mass) / charge
    ```
    
    Where:
    - `fragment_mass`: Exact monoisotopic mass of the amino acid sequence
    - `ion_type_correction`: Ion-specific mass adjustment (see ion types above)
    - `proton_mass`: 1.007276 Da
    - `charge`: The charge state (1, 2, 3, etc.)
    
    ### Parameters
    - **Isotopes**: Disabled for cleaner spectra (monoisotopic peaks only)
    - **Neutral losses**: Disabled by default for simplicity
    - **Mass accuracy**: Calculated to 4 decimal places
    - **Intensity**: Relative theoretical intensities (not experimental)
    
    ## Example Workflows
    
    ### Basic Peptide Analysis
    1. Enter sequence: `PEPTIDE`
    2. Select: b-ions and y-ions
    3. Charge states: 1+ and 2+
    4. Expected fragments: b₁-b₆, y₁-y₆ ions
    
    ### Comprehensive Fragmentation
    1. Enter sequence: `SAMPLESEQUENCE`
    2. Select: All ion types
    3. Charge states: 1+, 2+, 3+
    4. Results: Complete fragmentation pattern
    
    ### ETD Simulation
    1. Enter sequence: `PEPTIDE`
    2. Select: c-ions and z-ions
    3. Charge states: 1+ and 2+
    4. Results: ETD-like fragmentation pattern
    
    ## Troubleshooting
    
    ### Common Issues
    
    **"Sequence cannot be empty"**
    - Solution: Enter a valid amino acid sequence
    
    **"Invalid amino acid(s): X"**
    - Solution: Check for typos or non-standard amino acid codes
    - Use only standard single-letter codes
    
    **"Sequence must be at least 2 amino acids long"**
    - Solution: Enter a longer peptide sequence
    - Single amino acids cannot be fragmented
    
    **"Please select at least one ion type"**
    - Solution: Check at least one ion type checkbox
    
    **"Please select at least one charge state"**
    - Solution: Select at least one charge state from the dropdown
    
    ### Performance Notes
    - Longer sequences (>20 amino acids) may take longer to process
    - Higher charge states increase computation time
    - All ion types selected will generate more fragments
    
    ## Applications
    
    ### Mass Spectrometry Method Development
    - Design targeted MS/MS experiments
    - Optimize fragmentation conditions
    - Predict optimal precursor charge states
    
    ### Peptide Identification
    - Compare experimental spectra with theoretical fragments
    - Validate peptide sequence assignments
    - Understand fragmentation efficiency
    
    ### Educational Purposes
    - Learn peptide fragmentation patterns
    - Understand ion nomenclature
    - Explore charge state effects
    
    ## References and Further Reading
    
    ### Key Publications
    1. **Roepstorff, P. & Fohlman, J.** (1984). Proposal for a common nomenclature for sequence ions in mass spectra of peptides. *Biomed. Mass Spectrom.* 11, 601.
    
    2. **Senko, M.W. et al.** (1995). Determination of monoisotopic masses and ion populations for large biomolecules from resolved isotopic distributions. *J. Am. Soc. Mass Spectrom.* 6, 229-233.
    
    3. **Hunt, D.F. et al.** (1986). Protein sequencing by tandem mass spectrometry. *Proc. Natl. Acad. Sci. USA* 83, 6233-6237.
    
    ### Software and Tools
    - **pyOpenMS**: Open-source mass spectrometry library ([www.openms.de](https://www.openms.de))
    - **NIST Mass Spectral Database**: Reference spectra and fragmentation patterns
    - **Protein Prospector**: Online MS tools from UCSF
    
    ### Educational Resources
    - **Mass Spectrometry: A Textbook** by Jürgen H. Gross
    - **Introduction to Mass Spectrometry** by J. Throck Watson
    - Online tutorials at [www.massspecpedia.com](http://www.massspecpedia.com)
    
    ---
    
    💡 **Tip**: Start with the default settings (b-ions and y-ions, charges 1+ and 2+) for most peptides,
    then customize based on your specific analytical needs.
    """)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Input Parameters")
    
    # Peptide sequence input
    sequence_input = st.text_area(
        "Peptide Sequence:",
        value="PEPTIDE",
        height=100,
        help="""Enter the peptide sequence using single-letter amino acid codes:
        
• Standard amino acids: A, C, D, E, F, G, H, I, K, L, M, N, P, Q, R, S, T, V, W, Y
• Extended codes: X (any amino acid), U (selenocysteine)
• Minimum length: 2 amino acids for fragmentation
• Spaces and non-letter characters will be automatically removed

Examples: PEPTIDE, ACDEFGHIK, SAMPLESEQUENCE"""
    )
    
    # Ion type selection
    st.write("**Ion Types:**")
    st.caption("Select which fragment ion types to include in the theoretical spectrum")
    ion_types = []
    
    col_ions1, col_ions2 = st.columns(2)
    
    with col_ions1:
        st.markdown("**N-terminal ions:**")
        if st.checkbox("a-ions", help="""a-ions: N-terminal fragments with CO loss
        
• Formation: Cleavage at peptide bond + loss of CO (28 Da)
• Formula: [M + H - CO]⁺
• Abundance: Low in CID, moderate in high-energy conditions
• Mass shift: -27.99 Da from corresponding b-ion"""):
            ion_types.append('a')
        if st.checkbox("b-ions", value=True, help="""b-ions: Most common N-terminal fragments
        
• Formation: Direct cleavage at peptide bond (amide bond)
• Formula: [M + H]⁺ where M = N-terminal fragment mass
• Abundance: High in CID/HCD spectra (dominant N-terminal series)
• Nomenclature: b₁, b₂, b₃... numbered from N-terminus"""):
            ion_types.append('b')
        if st.checkbox("c-ions", help="""c-ions: N-terminal fragments with NH₃ retention
        
• Formation: Cleavage at N-Cα bond + retention of NH₃
• Formula: [M + H + NH₃]⁺
• Abundance: High in ETD/ECD, low in CID
• Mass shift: +17.03 Da from corresponding b-ion"""):
            ion_types.append('c')
    
    with col_ions2:
        st.markdown("**C-terminal ions:**")
        if st.checkbox("x-ions", help="""x-ions: C-terminal fragments with CO addition
        
• Formation: Cleavage at N-Cα bond + addition of CO
• Formula: [M + H + CO - H]⁺
• Abundance: Low in most fragmentation methods
• Mass shift: +25.98 Da from corresponding y-ion"""):
            ion_types.append('x')
        if st.checkbox("y-ions", value=True, help="""y-ions: Most common C-terminal fragments
        
• Formation: Cleavage at peptide bond + addition of H₂O
• Formula: [M + H + H₂O]⁺ where M = C-terminal fragment mass
• Abundance: High in CID/HCD spectra (dominant C-terminal series)
• Nomenclature: y₁, y₂, y₃... numbered from C-terminus"""):
            ion_types.append('y')
        if st.checkbox("z-ions", help="""z-ions: C-terminal fragments with NH₂ loss
        
• Formation: Cleavage at N-Cα bond + loss of NH₂
• Formula: [M + H - NH₂]⁺
• Abundance: High in ETD/ECD, low in CID
• Mass shift: +0.98 Da from corresponding y-ion"""):
            ion_types.append('z')
    
    # Charge state selection
    charges = st.multiselect(
        "Charge States:",
        options=[1, 2, 3, 4, 5],
        default=[1, 2],
        help="""Select charge states to include in the theoretical spectrum:
        
• 1+: Singly charged fragments (most common for short peptides)
• 2+: Doubly charged fragments (common for longer peptides)
• 3+ and higher: Multiple charges (for long peptides, lower m/z values)

Higher charge states:
- Produce fragments at lower m/z ratios
- Are more common with longer peptide sequences
- May improve fragmentation coverage
- Require higher precursor charge states"""
    )
    
    # Generate button
    if st.button('Generate Fragment Spectrum', type='primary'):
        with st.spinner('Generating theoretical spectrum...'):
            result_data = generate_theoretical_spectrum(sequence_input, ion_types, charges)

with col2:
    st.subheader("Results")
    
    # Initialize result_data if button hasn't been pressed
    if 'result_data' not in locals():
        result_data = None
    
    if result_data:
        if result_data["success"]:
            # Display basic info
            st.write(f"**Sequence:** {result_data['sequence']}")
            st.write(f"**Ion Types:** {', '.join([ION_TYPES[ion]['name'] for ion in result_data['ion_types']])}")
            st.write(f"**Charge States:** {', '.join(map(str, result_data['charges']))}")
            st.write(f"**Total Fragments:** {len(result_data['fragments'])}")
            
            # Summary by ion type
            if len(result_data['fragments']) > 0:
                summary = result_data['fragments'].groupby('ion_type').size()
                st.write("**Fragments by Ion Type:**")
                for ion_type, count in summary.items():
                    ion_name = ION_TYPES.get(ion_type, {}).get('name', ion_type)
                    st.write(f"- {ion_name}: {count}")
        else:
            st.error(f"Error: {result_data['error']}")

# Display plot and data table
if 'result_data' in locals() and result_data and result_data["success"]:
    # Create and display plot
    fig = create_fragmentation_plot(result_data)
    show_fig(fig, 'Fragment Spectrum')
    
    # Display fragment table
    st.subheader("Fragment Ion Table")
    
    # Format the dataframe for display
    display_df = result_data['fragments'].copy()
    display_df['m/z'] = display_df['mz'].round(4)
    display_df['Ion Type'] = display_df['ion_type'].map(lambda x: ION_TYPES.get(x, {}).get('name', x))
    display_df['Fragment'] = display_df['fragment_number']
    display_df['Charge'] = display_df['charge'].astype(str) + '+'
    display_df['Sequence'] = display_df['sequence']
    #display_df['Intensity'] = display_df['intensity'].apply(lambda x: f"{x:.2e}")
    
    # Select columns for display
    display_columns = ['Ion Type', 'Fragment', 'Charge', 'm/z', 
        #'Intensity', 
        'Sequence']
    st.dataframe(display_df[display_columns], use_container_width=True)
    
    # Download options
    st.subheader("Export Options")
    
    # Prepare download data
    csv_buffer = io.StringIO()
    display_df[display_columns].to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    csv_data = csv_buffer.getvalue()
    
    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:
        display_df[display_columns].to_excel(writer, index=False, sheet_name="Fragment Ions")
    xlsx_buffer.seek(0)
    xlsx_data = xlsx_buffer.getvalue()
    
    col_csv, col_xlsx = st.columns(2)
    
    with col_csv:
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"fragments_{result_data['sequence']}.csv",
            mime="text/csv"
        )
    
    with col_xlsx:
        st.download_button(
            label="Download Excel",
            data=xlsx_data,
            file_name=f"fragments_{result_data['sequence']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
