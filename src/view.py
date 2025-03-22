import numpy as np
import pandas as pd
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pyopenms as poms
from src.common.common import show_fig, display_large_dataframe
from typing import Union
from plotly.subplots import make_subplots


def get_df(file: Union[str, Path]) -> pd.DataFrame:
    """
    Load a Mass Spectrometry (MS) experiment from a given mzML file and return
    a pandas dataframe representation of the experiment.

    Args:
        file (Union[str, Path]): The path to the mzML file to load.

    Returns:
        pd.DataFrame: A pandas DataFrame with the following columns: "mslevel",
        "precursormz", "mzarray", and "intarray". The "mzarray" and "intarray"
        columns contain NumPy arrays with the m/z and intensity values for each
        spectrum in the mzML file, respectively.
    """
    exp = poms.MSExperiment()
    poms.MzMLFile().load(str(file), exp)
    df_spectra = exp.get_df()
    df_spectra["MS level"] = [spec.getMSLevel() for spec in exp]
    precs = []
    for spec in exp:
        p = spec.getPrecursors()
        if p:
            precs.append(p[0].getMZ())
        else:
            precs.append(np.nan)
    df_spectra["precursor m/z"] = precs

    # Drop spectra without peaks
    df_spectra = df_spectra[df_spectra["mzarray"].apply(lambda x: len(x) > 0)]

    df_spectra["max intensity m/z"] = df_spectra.apply(
        lambda x: x["mzarray"][x["intarray"].argmax()], axis=1
    )
    if not df_spectra.empty:
        st.session_state["view_spectra"] = df_spectra
    else:
        st.session_state["view_spectra"] = pd.DataFrame()
    exp_ms2 = poms.MSExperiment()
    exp_ms1 = poms.MSExperiment()
    for spec in exp:
        if spec.getMSLevel() == 1:
            exp_ms1.addSpectrum(spec)
        elif spec.getMSLevel() == 2:
            exp_ms2.addSpectrum(spec)
    if not exp_ms1.empty():
        st.session_state["view_ms1"] = exp_ms1.get_df(long=True)
    else:
        st.session_state["view_ms1"] = pd.DataFrame()
    if not exp_ms2.empty():
        st.session_state["view_ms2"] = exp_ms2.get_df(long=True)
    else:
        st.session_state["view_ms2"] = pd.DataFrame()


def plot_bpc_tic() -> go.Figure:
    """Plot the base peak and total ion chromatogram (TIC).

    Returns:
        A plotly Figure object containing the BPC and TIC plot.
    """
    fig = go.Figure()
    max_int = 0
    if st.session_state.view_tic:
        df = st.session_state.view_ms1.groupby("RT").sum().reset_index()
        df["type"] = "TIC"
        if df["inty"].max() > max_int:
            max_int = df["inty"].max()
        fig = df.plot(
            backend="ms_plotly",
            kind="chromatogram",
            x="RT",
            y="inty",
            by="type",
            color="#f24c5c",
            show_plot=False,
            grid=False,
            aggregate_duplicates=True,
        )
    if st.session_state.view_bpc:
        df = st.session_state.view_ms1.groupby("RT").max().reset_index()
        df["type"] = "BPC"
        if df["inty"].max() > max_int:
            max_int = df["inty"].max()
        fig = df.plot(
            backend="ms_plotly",
            kind="chromatogram",
            x="RT",
            y="inty",
            by="type",
            color="#2d3a9d",
            show_plot=False,
            grid=False,
            aggregate_duplicates=True,
        )
    if st.session_state.view_eic:
        df = st.session_state.view_ms1
        target_value = st.session_state.view_eic_mz.strip().replace(",", ".")
        try:
            target_value = float(target_value)
            ppm_tolerance = st.session_state.view_eic_ppm
            tolerance = (target_value * ppm_tolerance) / 1e6

            # Filter the DataFrame
            df_eic = df[
                (df["mz"] >= target_value - tolerance)
                & (df["mz"] <= target_value + tolerance)
            ].copy()
            if not df_eic.empty:
                df_eic.loc[:, "type"] = "XIC"
                if df_eic["inty"].max() > max_int:
                    max_int = df_eic["inty"].max()
                fig = df_eic.plot(
                    backend="ms_plotly",
                    kind="chromatogram",
                    x="RT",
                    y="inty",
                    by="type",
                    color="#f6bf26",
                    show_plot=False,
                    grid=False,
                    aggregate_duplicates=True,
                )
        except ValueError:
            st.error("Invalid m/z value for XIC provided. Please enter a valid number.")

    fig.update_yaxes(range=[0, max_int])
    fig.update_layout(
        title=f"{st.session_state.view_selected_file}",
        xaxis_title="retention time (s)",
        yaxis_title="intensity",
        plot_bgcolor="rgb(255,255,255)",
        height=500,
    )
    fig.layout.template = "plotly_white"
    return fig


@st.cache_resource
def plot_ms_spectrum(df, title, bin_peaks, num_x_bins):
    fig = df.plot(
        kind="spectrum",
        backend="ms_plotly",
        x="mz",
        y="intensity",
        color="#2d3a9d",
        title=title,
        show_plot=False,
        grid=False,
        bin_peaks=bin_peaks,
        num_x_bins=num_x_bins,
        aggregate_duplicates=True,
    )
    fig.update_layout(
        template="plotly_white", dragmode="select", plot_bgcolor="rgb(255,255,255)"
    )
    return fig


@st.fragment
def view_peak_map():
    df = st.session_state.view_ms1

    # ✅ Apply Box Selection Filtering
    if "view_peak_map_selection" in st.session_state:
        box = st.session_state.view_peak_map_selection.selection.box
        if box:
            df = st.session_state.view_ms1.copy()
            df = df[df["RT"] > box[0]["x"][0]]
            df = df[df["mz"] > box[0]["y"][1]]
            df = df[df["mz"] < box[0]["y"][0]]
            df = df[df["RT"] < box[0]["x"][1]]

    # ✅ Main 2D Peak Map Plot with Correct Y-Axis Label
    peak_map = df.plot(
        kind="peakmap",
        x="RT",
        y="mz",
        z="inty",
        xlabel="Retention Time (s)",    # ✅ X-axis label
        ylabel="m/z",                   # ✅ Y-axis label for main plot
        grid=False,
        show_plot=False,
        bin_peaks=True,
        backend="ms_plotly",
        aggregate_duplicates=True,
    )

    # ✅ Marginal TIC Plot with Correct Y-Axis Label
    df_tic = df.groupby("RT").sum().reset_index()

    marginal_tic = go.Figure()
    marginal_tic.add_trace(
        go.Scatter(
            x=df_tic["RT"],
            y=df_tic["inty"],
            mode="lines",
            line=dict(color="#f24c5c", width=2),
            name="TIC",
        )
    )

    marginal_tic.update_layout(
        height=200,
        margin=dict(l=0, r=0, t=0, b=0),
        plot_bgcolor="rgb(255,255,255)",
        xaxis=dict(title="Retention Time (s)"),     # ✅ X-axis label
        yaxis=dict(title="TIC")                     # ✅ Y-axis label for TIC plot
    )

    # ✅ Create subplots with peak map on top and TIC at the bottom
    combined_fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],                      # Peak map gets 70%, TIC gets 30%
        vertical_spacing=0.05
    )

    # ✅ Add main peak map to subplot (first row)
    for trace in peak_map.data:
        combined_fig.add_trace(trace, row=1, col=1)

    # ✅ Add marginal TIC plot (second row)
    for trace in marginal_tic.data:
        combined_fig.add_trace(trace, row=2, col=1)

    # ✅ Update layout with range slider only on the bottom x-axis
    combined_fig.update_layout(
        template="simple_white",
        dragmode="zoom",
        
        # ✅ Top x-axis (no range slider)
        xaxis=dict(
            showgrid=False,
            domain=[0, 1]
        ),
        
        # ✅ Bottom x-axis with range slider
        xaxis2=dict(
            title="Retention Time (s)",
            rangeslider=dict(visible=True),
            showgrid=False
        ),
        
        # ✅ Configure Y-axes
        yaxis=dict(title="m/z"),                      # Y-axis for peak map
        yaxis2=dict(title="TIC"),                     # Y-axis for TIC
        
        # ✅ Styling
        height=850,
        margin=dict(t=100, b=100),
        title=dict(
            text=st.session_state.view_selected_file,
            x=0.5,
            y=0.99,
            xanchor="center",
            yanchor="top",
            font=dict(size=18, family="Arial, sans-serif")
        )
    )

    # ✅ Display the Combined Plot
    c1, c2 = st.columns(2)

    with c1:
        st.info(
            "💡 Zoom in via rectangular selection for more details and 3D plot. "
            "Double click plot to zoom back out."
        )
        show_fig(
            combined_fig,
            f"peak_map_{st.session_state.view_selected_file}",
            selection_session_state_key="view_peak_map_selection",
        )

    # ✅ 3D Peak Map (without range slider)
    with c2:
        if df.shape[0] < 2500:
            peak_map_3D = df.plot(
                kind="peakmap",
                plot_3d=True,
                backend="ms_plotly",
                x="RT",
                y="mz",
                z="inty",
                zlabel="Intensity",
                xlabel="Retention Time (s)",
                ylabel="m/z",
                title="",
                show_plot=False,
                grid=False,
                bin_peaks=st.session_state.spectrum_bin_peaks,
                num_x_bins=st.session_state.spectrum_num_bins,
                height=650,
                width=900,
                aggregate_duplicates=True,
            )

            # ✅ Update 3D plot layout (without range slider)
            peak_map_3D.update_layout(
                scene=dict(
                    xaxis=dict(title="Retention Time (s)"),
                    yaxis=dict(title="m/z"),
                    zaxis=dict(title="Intensity"),
                    dragmode="orbit"
                )
            )

            st.plotly_chart(peak_map_3D, use_container_width=True)            
@st.fragment
def view_spectrum():
    cols = st.columns([0.34, 0.66])
    with cols[0]:
        df = st.session_state.view_spectra.copy()
        df["spectrum ID"] = df.index + 1
        index = display_large_dataframe(
            df,
            column_order=[
                "spectrum ID",
                "RT",
                "MS level",
                "max intensity m/z",
                "precursor m/z",
            ],
            selection_mode="single-row",
            on_select="rerun",
            use_container_width=True,
            hide_index=True,
        )
    with cols[1]:
        if index is not None:
            df = st.session_state.view_spectra.iloc[index]
            if "view_spectrum_selection" in st.session_state:
                box = st.session_state.view_spectrum_selection.selection.box
                if box:
                    mz_min, mz_max = sorted(box[0]["x"])
                    mask = (df["mzarray"] > mz_min) & (df["mzarray"] < mz_max)
                    df["intarray"] = df["intarray"][mask]
                    df["mzarray"] = df["mzarray"][mask]

            if df["mzarray"].size > 0:
                title = f"{st.session_state.view_selected_file}  spec={index+1}  mslevel={df['MS level']}"
                if df["precursor m/z"] > 0:
                    title += f" precursor m/z: {round(df['precursor m/z'], 4)}"

                df_selected = pd.DataFrame(
                    {
                        "mz": df["mzarray"],
                        "intensity": df["intarray"],
                    }
                )
                df_selected["RT"] = df["RT"]
                df_selected["MS level"] = df["MS level"]
                df_selected["precursor m/z"] = df["precursor m/z"]
                df_selected["max intensity m/z"] = df["max intensity m/z"]

                fig = plot_ms_spectrum(
                    df_selected,
                    title,
                    st.session_state.spectrum_bin_peaks,
                    st.session_state.spectrum_num_bins,
                )

                show_fig(fig, title.replace(" ", "_"), True, "view_spectrum_selection")
            else:
                st.session_state.pop("view_spectrum_selection")
                st.rerun()
        else:
            st.info("💡 Select rows in the spectrum table to display plot.")


@st.fragment()
def view_bpc_tic():
    cols = st.columns(5)
    cols[0].checkbox(
        "Total Ion Chromatogram (TIC)", True, key="view_tic", help="Plot TIC."
    )
    cols[1].checkbox(
        "Base Peak Chromatogram (BPC)", True, key="view_bpc", help="Plot BPC."
    )
    cols[2].checkbox(
        "Extracted Ion Chromatogram (EIC/XIC)",
        True,
        key="view_eic",
        help="Plot extracted ion chromatogram with specified m/z.",
    )
    cols[3].text_input(
        "XIC m/z",
        "235.1189",
        help="m/z for XIC calculation.",
        key="view_eic_mz",
    )
    cols[4].number_input(
        "XIC ppm tolerance",
        0.1,
        50.0,
        10.0,
        1.0,
        help="Tolerance for XIC calculation (ppm).",
        key="view_eic_ppm",
    )
    fig = plot_bpc_tic()
    
    fig.update_layout(
        xaxis=dict(
            rangeslider=dict(visible=True),         # Range slider for x-axis zoom
            rangeselector=dict(                     # Zoom buttons
                buttons=list([
                    dict(count=1, label="1s", step="second", stepmode="backward"),
                    dict(count=10, label="10s", step="second", stepmode="backward"),
                    dict(count=1, label="1m", step="minute", stepmode="backward"),
                    dict(step="all")
                ])
            )
        ),
        margin=dict(l=0, r=0, t=0, b=0),           # Remove margins for full-width display
        height=700,                                # Increase height for better visualization
        hovermode="x unified",                     # Unified hover tooltip
        modebar=dict(
            orientation='h',                       # Horizontal toolbar
            bgcolor='rgba(255,255,255,0.7)',       # Toolbar background color
        )
    )

    # Display full-width chromatogram
    st.plotly_chart(fig, use_container_width=True)
