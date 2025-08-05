"""
In Silico Protein Digest Page

This module provides functionality for performing in silico protein digestion
using pyOpenMS. Users can input protein sequences in FASTA format and get
peptide lists with mass calculations.
"""

import streamlit as st
import sys
from pathlib import Path

# Add utils to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.fasta import validate_fasta_input
from utils.digest import perform_digest, get_digest_statistics, get_available_enzymes, filter_peptides_by_length, calculate_protein_coverage, generate_coverage_html

# Default values
DEFAULT_ENZYME = "Trypsin"
DEFAULT_MISSED_CLEAVAGES = 0  # Changed from 2 to 0
DEFAULT_MAX_CHARGES = 5
DEFAULT_MIN_PEPTIDE_LENGTH = 6
DEFAULT_MAX_PEPTIDE_LENGTH = 50


def main():
    """Main function for the digest page."""
    st.title("✂️ In Silico Protein Digest")
    
    st.markdown("""
    **Simulate enzymatic protein digestion computationally** to predict peptides for mass spectrometry analysis.
    
    This tool uses pyOpenMS to perform theoretical protein digestion with various proteases, helping you:
    - **Plan MS experiments** by predicting which peptides will be generated
    - **Optimize digestion conditions** by testing different enzymes and parameters
    - **Analyze protein coverage** and identify potential issues before experimental work
    - **Generate theoretical peptide lists** with accurate mass-to-charge ratios
    """)
    
    with st.expander("📚 **How In Silico Digestion Works**"):
        st.markdown("""
        **Enzymatic Cleavage Simulation:**
        - Enzymes cut proteins at specific amino acid sequences (cleavage sites)
        - **Trypsin** cuts after K (lysine) and R (arginine), except when followed by P (proline)
        - **Pepsin** cuts preferentially at F, L, W, Y amino acids under acidic conditions
        - **Chymotrypsin** cuts after F, W, Y, L amino acids
        
        **Missed Cleavages:**
        - Real digestion is not 100% efficient - some cleavage sites are missed
        - Allows prediction of longer peptides that contain uncleaved sites
        - Important for comprehensive coverage analysis
        
        **Applications:**
        - **Bottom-up proteomics** experiment planning
        - **Peptide mapping** for protein characterization
        - **Method development** for LC-MS/MS workflows
        - **Quality control** for digestion efficiency assessment
        """)
    
    # Input form section
    with st.form("digest_form"):
        st.subheader("Input Parameters")
        
        # FASTA input
        default_sequence = """>sp|Q9UPY3|DICER_HUMAN Endoribonuclease Dicer OS=Homo sapiens OX=9606 GN=DICER1 PE=1 SV=3
MKSPALQPLSMAGLQLMTPASSPMGPFFGLPWQQEAIHDNIYTPRKYQVELLEAALDHNT
IVCLNTGSGKTFIAVLLTKELSYQIRGDFSRNGKRTVFLVNSANQVAQQVSAVRTHSDLK
VGEYSNLEVNASWTKERWNQEFTKHQVLIMTCYVALNVLKNGYLSLSDINLLVFDECHLA
ILDHPYREIMKLCENCPSCPRILGLTASILNGKCDPEELEEKIQKLEKILKSNAETATDL
VVLDRYTSQPCEIVVDCGPFTDRSGLYERLLMELEEALNFINDCNISVHSKERDSTLISK
QILSDCRAVLVVLGPWCADKVAGMMVRELQKYIKHEQEELHRKFLLFTDTFLRKIHALCE
EHFSPASLDLKFVTPKVIKLLEILRKYKPYERQQFESVEWYNNRNQDNYVSWSDSEDDDE
DEEIEEKEKPETNFPSPFTNILCGIIFVERRYTAVVLNRLIKEAGKQDPELAYISSNFIT
GHGIGKNQPRNKQMEAEFRKQEEVLRKFRAHETNLLIATSIVEEGVDIPKCNLVVRFDLP
TEYRSYVQSKGRARAPISNYIMLADTDKIKSFEEDLKTYKAIEKILRNKCSKSVDTGETD
IDPVMDDDDVFPPYVLRPDDGGPRVTINTAIGHINRYCARLPSDPFTHLAPKCRTRELPD
GTFYSTLYLPINSPLRASIVGPPMSCVRLAERVVALICCEKLHKIGELDDHLMPVGKETV
KYEEELDLHDEEETSVPGRPGSTKRRQCYPKAIPECLRDSYPRPDQPCYLYVIGMVLTTP
LPDELNFRRRKLYPPEDTTRCFGILTAKPIPQIPHFPVYTRSGEVTISIELKKSGFMLSL
QMLELITRLHQYIFSHILRLEKPALEFKPTDADSAYCVLPLNVVNDSSTLDIDFKFMEDI
EKSEARIGIPSTKYTKETPFVFKLEDYQDAVIIPRYRNFDQPHRFYVADVYTDLTPLSKF
PSPEYETFAEYYKTKYNLDLTNLNQPLLDVDHTSSRLNLLTPRHLNQKGKALPLSSAEKR
KAKWESLQNKQILVPELCAIHPIPASLWRKAVCLPSILYRLHCLLTAEELRAQTASDAGV
GVRSLPADFRYPNLDFGWKKSIDSKSFISISNSSSAENDNYCKHSTIVPENAAHQGANRT
SSLENHDQMSVNCRTLLSESPGKLHVEVSADLTAINGLSYNQNLANGSYDLANRDFCQGN
QLNYYKQEIPVQPTTSYSIQNLYSYENQPQPSDECTLLSNKYLDGNANKSTSDGSPVMAV
MPGTTDTIQVLKGRMDSEQSPSIGYSSRTLGPNPGLILQALTLSNASDGFNLERLEMLGD
SFLKHAITTYLFCTYPDAHEGRLSYMRSKKVSNCNLYRLGKKKGLPSRMVVSIFDPPVNW
LPPGYVVNQDKSNTDKWEKDEMTKDCMLANGKLDEDYEEEDEEEESLMWRAPKEEADYED
DFLEYDQEHIRFIDNMLMGSGAFVKKISLSPFSTTDSAYEWKMPKKSSLGSMPFSSFDED
FDYSSWDAMCYLDPSKAVEEDDFVVGFWNPSEENCGVDTGKQSISYDLHTEQCIADKSIA
DCVEALLGCYLTSCGERAAQLFLCSLGLKVLPVIKRTDREKALCPTRENFNSQQKNLSVS
CAAASVASSRSSVLKDSEYGCLKIPPRCMFDHPDADKTLNHLISGFENFEKKINYRFKNK
AYLLQAFTHASYHYNTITDCYQRLEFLGDAILDYLITKHLYEDPRQHSPGVLTDLRSALV
NNTIFASLAVKYDYHKYFKAVSPELFHVIDDFVQFQLEKNEMQGMDSELRRSEEDEEKEE
DIEVPKAMGDIFESLAGAIYMDSGMSLETVWQVYYPMMRPLIEKFSANVPRSPVRELLEM
EPETAKFSPAERTYDGKVRVTVEVVGKGKFKGVGRSYRIAKSAAARRALRSLKANQPQVP
NS"""

        fasta_input = st.text_area(
            "Paste protein sequences in FASTA format",
            value=default_sequence,
            height=200,
            help="Default sequence: DICER_HUMAN protein for demonstration"
        )
        
        # Get available enzymes
        try:
            available_enzymes = get_available_enzymes()
            # convert bytes to str if necessary
            available_enzymes = [enzyme.decode() if isinstance(enzyme, bytes) else enzyme for enzyme in available_enzymes]
            
        except Exception as e:
            st.error(f"❌ Cannot load enzyme database: {e}")
            st.error("Please ensure pyOpenMS is properly configured before using the digest functionality.")
            st.stop()
        
        # Enzyme selection
        enzyme_index = 0
        if DEFAULT_ENZYME in available_enzymes:
            enzyme_index = available_enzymes.index(DEFAULT_ENZYME)
        
        enzyme = st.selectbox(
            "Enzyme",
            options=available_enzymes,
            index=enzyme_index,
            help="Select the enzyme for protein digestion"
        )
        
        # Parameters
        col1, col2 = st.columns(2)
        
        with col1:
            missed_cleavages = st.number_input(
                "Max missed cleavages",
                min_value=0,
                max_value=10,
                value=DEFAULT_MISSED_CLEAVAGES,
                help="Maximum number of missed cleavages allowed"
            )
        
        with col2:
            max_charges = st.number_input(
                "Max charge state (N)",
                min_value=1,
                max_value=10,
                value=DEFAULT_MAX_CHARGES,
                help="Maximum charge state to calculate [M + nH]"
            )
        
        # Peptide length filtering
        st.subheader("Peptide Length Filtering")
        col3, col4 = st.columns(2)
        
        with col3:
            min_peptide_length = st.number_input(
                "Min peptide length (AA)",
                min_value=1,
                max_value=100,
                value=DEFAULT_MIN_PEPTIDE_LENGTH,
                help="Minimum peptide length in amino acids"
            )
        
        with col4:
            max_peptide_length = st.number_input(
                "Max peptide length (AA)",
                min_value=1,
                max_value=200,
                value=DEFAULT_MAX_PEPTIDE_LENGTH,
                help="Maximum peptide length in amino acids"
            )
        
        # Submit button
        submit = st.form_submit_button("🧬 Digest Proteins", type="primary")
    
    # Process form submission
    if submit:
        if not fasta_input.strip():
            st.error("❌ Please provide FASTA sequences to digest.")
            return
        
        # Show progress
        with st.spinner("🔬 Performing in silico digest..."):
            # Validate FASTA input
            is_valid, error_message, sequences = validate_fasta_input(fasta_input)
            
            if not is_valid:
                st.error(f"❌ FASTA validation failed: {error_message}")
                return
            
            if not sequences:
                st.error("❌ No valid sequences found in the input.")
                return
            
            # Show input summary
            st.success(f"✅ Successfully parsed {len(sequences)} protein sequence(s)")
            
            # Progress bar
            progress_bar = st.progress(0, text="Initializing digest...")
            
            try:
                # Perform digest
                progress_bar.progress(30, text="Performing enzymatic digest...")
                
                df_results = perform_digest(
                    sequences=sequences,
                    enzyme=enzyme,
                    missed_cleavages=missed_cleavages,
                    max_charges=max_charges
                )
                
                progress_bar.progress(60, text="Applying peptide length filters...")
                
                # Apply peptide length filtering
                df_results = filter_peptides_by_length(
                    df_results,
                    min_length=min_peptide_length,
                    max_length=max_peptide_length
                )
                
                progress_bar.progress(80, text="Processing results...")
                
                if df_results.empty:
                    st.warning("⚠️ No peptides were generated from the digest or all peptides were filtered out. Try adjusting the parameters or check your input sequences.")
                    progress_bar.empty()
                    return
                
                progress_bar.progress(100, text="Complete!")
                progress_bar.empty()
                
                # Display results
                st.subheader("📊 Digest Results")
                
                # Summary statistics
                stats = get_digest_statistics(df_results)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Peptides", f"{stats['total_peptides']:,}")
                with col2:
                    st.metric("Unique Proteins", stats['unique_proteins'])
                with col3:
                    st.metric("Avg Length", f"{stats['avg_peptide_length']:.1f} AA")
                with col4:
                    st.metric("Mass Range", f"{stats['mass_range'][0]:.0f}-{stats['mass_range'][1]:.0f} Da")
                
                # Results table
                st.dataframe(
                    df_results,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Accession": st.column_config.TextColumn("Accession", width="small"),
                        "Description": st.column_config.TextColumn("Description", width="large"),
                        "Peptide Sequence": st.column_config.TextColumn("Peptide Sequence", width="medium"),
                        "Length": st.column_config.NumberColumn("Length", help="Peptide length in amino acids"),
                        "Start": st.column_config.TextColumn("Start", width="small", help="1-based start position(s) in protein sequence"),
                        "End": st.column_config.TextColumn("End", width="small", help="1-based end position(s) in protein sequence"),
                        "[M]": st.column_config.NumberColumn("[M]", format="%.4f"),
                    }
                )
                
                # Protein Coverage Visualization
                st.subheader("🎨 Protein Coverage Visualization")
                st.markdown("""
                **Sequence Coverage Analysis:** Each amino acid is colored based on how many peptides cover that position.
                Hover over amino acids to see exact coverage counts.
                """)
                
                # Calculate coverage for each protein
                coverage_data = calculate_protein_coverage(df_results, sequences)
                
                # Display coverage for each protein
                for accession, coverage_info in coverage_data.items():
                    coverage_html = generate_coverage_html(accession, coverage_info)
                    st.markdown(coverage_html, unsafe_allow_html=True)
                
                # Download section
                st.subheader("⬇️ Download Results")
                
                # Generate TSV
                tsv_data = df_results.to_csv(sep="\t", index=False)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📄 Download as TSV",
                        data=tsv_data,
                        file_name=f"digest_results_{enzyme}_{missed_cleavages}mc.tsv",
                        mime="text/tab-separated-values",
                        help="Download results as tab-separated values file"
                    )
                
                with col2:
                    csv_data = df_results.to_csv(index=False)
                    st.download_button(
                        label="📄 Download as CSV",
                        data=csv_data,
                        file_name=f"digest_results_{enzyme}_{missed_cleavages}mc.csv",
                        mime="text/csv",
                        help="Download results as comma-separated values file"
                    )
                
                # Additional information
                with st.expander("ℹ️ Digest Parameters Used"):
                    st.write(f"**Enzyme:** {enzyme}")
                    st.write(f"**Max missed cleavages:** {missed_cleavages}")
                    st.write(f"**Max charge states:** {max_charges}")
                    st.write(f"**Input sequences:** {len(sequences)}")
                
            except Exception as e:
                progress_bar.empty()
                st.exception(f"❌ An error occurred during digest: {str(e)}")
                st.error("Please check your input and try again. If the problem persists, try with a simpler enzyme like Trypsin.")


if __name__ == "__main__":
    
    main()
main()