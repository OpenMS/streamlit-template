import io

import plotly.graph_objects as go
import streamlit as st
import pyopenms as oms
import pandas as pd
import numpy as np

from src.common.common import page_setup, show_fig

params = page_setup()

pattern_generator = oms.CoarseIsotopePatternGenerator()

pd.options.plotting.backend = "ms_plotly"

st.title("Calculate Isotopic Envelope")

col1, _ = st.columns(2)

with col1:

    target_base_peak = st.number_input(
        "Input most abundant/intense peak [Da]:", min_value=0.0, value=20000.0,
        help=
        """
        The most intense (or most abundant) peak is the isotope peak 
        with the highest abundance in the protein’s mass spectrum. It 
        represents the most common isotopic composition and serves as 
        the reference point for reconstructing the full isotopic envelope.
        """
    )
    if st.button('Compute Isotopic Envelope'):
        with st.spinner('Computing...'):

            # Start with most_intense_mass == avg_mass
            start = pattern_generator.estimateFromPeptideWeight(
                target_base_peak
            ).getMostAbundant().getMZ()
            
            # Extend to the right
            right_samples = []
            right_samples_avg = []
            for delta in np.arange(0, 20, 0.2):
                current_sample = pattern_generator.estimateFromPeptideWeight(
                    target_base_peak + delta
                ).getMostAbundant().getMZ()
                right_samples.append(current_sample)
                right_samples_avg.append(target_base_peak + delta)

                # Stop extension if result gets worse than base case
                if (
                    abs(current_sample-target_base_peak) > 
                    abs(start-target_base_peak)
                ):
                    break
            
            # Extend to the left
            left_samples = []
            left_samples_avg = []
            for delta in np.arange(0, 20, 0.2):
                current_sample = pattern_generator.estimateFromPeptideWeight(
                    target_base_peak-delta
                ).getMostAbundant().getMZ()
                left_samples.append(current_sample)
                left_samples_avg.append(target_base_peak - delta)

                # Stop extension if result gets worse than base case
                if (
                    abs(current_sample-target_base_peak) > 
                    abs(start-target_base_peak)
                ):
                    break
            
            # Combine samples
            samples = np.array(left_samples + [start] + right_samples)
            samples_avg = np.array(left_samples_avg + [target_base_peak] + right_samples_avg)
            
            # Determine best fit
            best_pos = np.argmin(np.abs(samples-target_base_peak))
            best_avg = samples_avg[best_pos]
            best_intensity = samples[best_pos]

            # Compute distribution of best fit
            distribution_obj = pattern_generator.estimateFromPeptideWeight(
                best_avg
            )
            distribution = distribution_obj.getContainer()
            mzs = np.array([p.getMZ() for p in distribution])
            intensities = np.array([p.getIntensity() for p in distribution])
            monoisotopic = np.min(mzs) # Monoisotopic isotope = lightest

            # Recompute average
            best_avg = np.sum(mzs * intensities)

            # Adjust distribution
            delta = distribution_obj.getMostAbundant().getMZ() - target_base_peak
            mzs -= delta
            best_avg -= delta
            monoisotopic -= delta

            # Output fit
            st.write(f'Average Mass: {best_avg:.5f} Da')
            st.write(f'Monoisotopic Mass: {monoisotopic:.5f} Da')

            # Create dataframe
            df = pd.DataFrame({
                'mz' : mzs,
                'intensity' : intensities
            })

            # Color highlights
            df['color'] = 'black'
            df.iloc[np.argmax(df['intensity']),-1] = 'red'
            # Plot
            fig = go.Figure()
            fig = df[df['intensity'] != 0].plot(
                x="mz",
                y="intensity",
                kind="spectrum",
                peak_color='color',
                #annotation_color='color',
                canvas=fig,
                show_plot=False,
                grid=False,
                annotate_top_n_peaks=1
            )
            considered = mzs[intensities > (0.001*max(intensities))]
            fig.update_xaxes(range=[np.min(considered), np.max(considered)])
            fig.update_layout(
                title="Isotopic Envelope",
                xaxis_title="m/z",
                yaxis_title="Intensity"
            )
            show_fig(fig, 'Isotopic Envelope')

            # Output dataframe
            # df_out = df.loc[:, ['mz', 'intensity']]
            df_out = df

            # Create a TSV file object in memory
            tsv_buffer = io.StringIO()
            df_out.to_csv(tsv_buffer, sep='\t', index=False)

            # Retrieve the TSV file object
            tsv_buffer.seek(0)
            tsv_file = tsv_buffer.getvalue()

            # Create an in-memory Excel file
            xlsx_buffer = io.BytesIO()
            with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:
                df_out.to_excel(writer, index=False, sheet_name="MS Data")

            # Retrieve the Excel file object
            xlsx_buffer.seek(0)
            xlsx_file = xlsx_buffer.getvalue()
            

            tsv_col, excel_col, _= st.columns(3)

            @st.fragment
            def tsv_download():
                st.download_button(
                    label="Download tsv file", 
                    file_name='Isotopic Envelope.tsv', 
                    data=tsv_file
                )
            
            with tsv_col:
                tsv_download()

            @st.fragment
            def xlsx_download():
                st.download_button(
                    label="Download excel file", 
                    file_name='Isotopic Envelope.xlsx', 
                    data=xlsx_file
                )

            with excel_col:
                xlsx_download()
