import numpy as np
import pandas as pd
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pyopenms as poms

from src.plotting.MSExperimentPlotter import plotMSExperiment
from src.common.common import show_fig, display_large_dataframe

from typing import Union


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
    if st.session_state.view_tic:
        df = st.session_state.view_ms1.groupby("RT").sum().reset_index()
        fig.add_scatter(
            x=df["RT"],
            y=df["inty"],
            mode="lines",
            line=dict(color="#f24c5c", width=3),  # OpenMS red
            name="TIC",
            showlegend=True,
        )
    if st.session_state.view_bpc:
        df = st.session_state.view_ms1.groupby("RT").max().reset_index()
        fig.add_scatter(
            x=df["RT"],
            y=df["inty"],
            mode="lines",
            line=dict(color="#2d3a9d", width=3),  # OpenMS blue
            name="BPC",
            showlegend=True,
        )
    if st.session_state.view_eic:
        df = st.session_state.view_ms1
        target_value = st.session_state.view_eic_mz.strip().replace(",", ".")
        try:
            target_value = float(target_value)
            ppm_tolerance = st.session_state.view_eic_ppm
            tolerance = (target_value * ppm_tolerance) / 1e6

            # Filter the DataFrame
            df_eic = df[(df['mz'] >= target_value - tolerance) & (df['mz'] <= target_value + tolerance)]
            if not df_eic.empty:
                fig.add_scatter(
                    x=df_eic["RT"],
                    y=df_eic["inty"],
                    mode="lines",
                    line=dict(color="#f6bf26", width=3),
                    name="XIC",
                    showlegend=True,
                )
        except ValueError:
            st.error("Invalid m/z value for XIC provided. Please enter a valid number.")

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
def plot_ms_spectrum(spec, title, color):
    """
    Takes a pandas Series (spec) and generates a needle plot with m/z and intensity dimension.

    Args:
        spec: Pandas Series representing the mass spectrum with "mzarray" and "intarray" columns.
        title: Title of the plot.
        color: Color of the line in the plot.

    Returns:
        A Plotly Figure object representing the needle plot of the mass spectrum.
    """

    # Every Peak is represented by three dots in the line plot: (x, 0), (x, y), (x, 0)
    def create_spectra(x, y, zero=0):
        x = np.repeat(x, 3)
        y = np.repeat(y, 3)
        y[::3] = y[2::3] = zero
        return pd.DataFrame({"mz": x, "intensity": y})

    df = create_spectra(spec["mzarray"], spec["intarray"])
    fig = px.line(df, x="mz", y="intensity")
    fig.update_traces(line_color=color)
    fig.add_hline(0, line=dict(color="#DDDDDD"), line_width=3)
    fig.update_layout(
        showlegend=False,
        title_text=title,
        xaxis_title="m/z",
        yaxis_title="intensity",
        plot_bgcolor="rgb(255,255,255)",
        dragmode="select",
    )
    # add annotations
    top_indices = np.argsort(spec["intarray"])[-5:][::-1]
    for index in top_indices:
        mz = spec["mzarray"][index]
        i = spec["intarray"][index]
        fig.add_annotation(
            dict(
                x=mz,
                y=i,
                text=str(round(mz, 5)),
                showarrow=False,
                xanchor="left",
                font=dict(
                    family="Open Sans Mono, monospace",
                    size=12,
                    color=color,
                ),
            )
        )
    fig.layout.template = "plotly_white"
    # adjust x-axis limits to not cut peaks and annotations
    x_values = [trace.x for trace in fig.data]
    xmin = min([min(values) for values in x_values])
    xmax = max([max(values) for values in x_values])
    padding = 0.15 * (xmax - xmin)
    fig.update_layout(
        xaxis_range=[
            xmin - padding,
            xmax + padding,
        ]
    )
    return fig


@st.fragment
def view_peak_map():
    df = st.session_state.view_ms1
    if "view_peak_map_selection" in st.session_state:
        box = st.session_state.view_peak_map_selection.selection.box
        if box:
            df = st.session_state.view_ms1.copy()
            df = df[df["RT"] > box[0]["x"][0]]
            df = df[df["mz"] > box[0]["y"][1]]
            df = df[df["mz"] < box[0]["y"][0]]
            df = df[df["RT"] < box[0]["x"][1]]
    peak_map = plotMSExperiment(
        df, plot3D=False, title=st.session_state.view_selected_file
    )
    c1, c2 = st.columns(2)
    with c1:
        st.info(
            "💡 Zoom in via rectangular selection for more details and 3D plot. Double click plot to zoom back out."
        )
        show_fig(
            peak_map,
            f"peak_map_{st.session_state.view_selected_file}",
            selection_session_state_key="view_peak_map_selection",
        )
    with c2:
        if df.shape[0] < 2500:
            peak_map_3D = plotMSExperiment(df, plot3D=True, title="")
            st.pyplot(peak_map_3D, use_container_width=True)


@st.fragment
def view_spectrum():
    cols = st.columns([0.34, 0.66])
    with cols[0]:
        df = st.session_state.view_spectra.copy()
        df["spectrum ID"] = df.index + 1
        event = display_large_dataframe(
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
        rows = event.selection.rows
    with cols[1]:
        if rows:
            df = st.session_state.view_spectra.iloc[rows[0]]
            if "view_spectrum_selection" in st.session_state:
                box = st.session_state.view_spectrum_selection.selection.box
                if box:
                    mz_min, mz_max = sorted(box[0]["x"])
                    mask = (df["mzarray"] > mz_min) & (df["mzarray"] < mz_max)
                    df["intarray"] = df["intarray"][mask]
                    df["mzarray"] = df["mzarray"][mask]

            if df["mzarray"].size > 0:
                title = f"{st.session_state.view_selected_file}  spec={rows[0]+1}  mslevel={df['MS level']}"
                if df["precursor m/z"] > 0:
                    title += f" precursor m/z: {round(df['precursor m/z'], 4)}"
                fig = plot_ms_spectrum(df, title, "#2d3a9d")
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
        "Extracted Ion Chromatogram (EIC/XIC)", True, key="view_eic", help="Plot extracted ion chromatogram with specified m/z."
    )
    cols[3].text_input(
        "XIC m/z",
        "235.1189",
        help="m/z for XIC calculation.",
        key="view_eic_mz",
    )
    cols[4].number_input(
        "XIC ppm tolerance",
        0.1, 50.0, 10.0, 1.0,
        help="Tolerance for XIC calculation (ppm).",
        key="view_eic_ppm"
    )
    fig = plot_bpc_tic()
    show_fig(fig, f"BPC-TIC-{st.session_state.view_selected_file}")

@st.cache_resource
def plot_ms2_spectrum(spec, title, color):
    """
    Takes a pandas Series (spec) and generates a needle plot with m/z and intensity dimension, also annotate ions.

    Args:
        spec: Pandas Series representing the mass spectrum with 
              "mzarray" {ions m/z ratio}, "intarray" {ion intensities} and "anotarray" {ions annotation} columns.
        title: Title of the plot.
        color: Color of the line in the plot.

    Returns:
        A Plotly Figure object representing the needle plot of the mass spectrum.
    """

    # Every Peak is represented by three dots in the line plot: (x, 0), (x, y), (x, 0)
    def create_spectra(x, y, zero=0):
        x = np.repeat(x, 3)
        y = np.repeat(y, 3)
        y[::3] = y[2::3] = zero
        return pd.DataFrame({"mz": x, "intensity": y})

    df = create_spectra(spec["mzarray"], spec["intarray"])
    fig = px.line(df, x="mz", y="intensity")
    fig.update_traces(line_color=color,  line_width=1)
    fig.update_layout(
        showlegend=True,
        title_text=title,
        xaxis_title="m/z",
        yaxis_title="intensity",
        plot_bgcolor="rgb(255,255,255)",
    )
    fig.layout.template = "plotly_white"
    fig.update_yaxes(fixedrange=True)

    # Annotate every line with a string
    for mz, intensity, annotation in zip(spec["mzarray"], spec["intarray"], spec["anotarray"]):
        if intensity < 0.3:
            yshift_ = 60  # Adjust this value for peaks with high intensity
        else:
            yshift_ = 20  # Adjust this value for peaks with low intensity

        # change the annotation colour according to ion-type
        if "MI" in annotation:
            annotation_color = '#ff0000' 
        elif "y" in annotation:
            annotation_color = 'green' 
        elif "[M" in annotation:
            annotation_color = 'darkmagenta'
        else:
            annotation_color = 'blue'  # Default color for other annotations

        #add annotations
        fig.add_annotation(
            x=mz,
            y=intensity,
            text=annotation,
            showarrow=False,
            arrowhead=1,
            arrowcolor=color,
            font=dict(size=12, color=annotation_color),
            xshift=0,
            yshift=yshift_,
            textangle=90 #verticle
        )

    return fig

@st.cache_resource
def plot_ms2_spectrum_full(spec, title, base_color):
    """
    Takes a pandas Series (spec) and generates a needle plot with m/z and intensity dimension, also annotates ions.
    
    Args:
        spec: Pandas Series representing the mass spectrum with 
              "mzarray" {ions m/z ratio}, "intarray" {ion intensities} and "anotarray" {ions annotation} columns.
        title: Title of the plot.
        base_color: Base color for the line.

    Returns:
        A Plotly Figure object representing the needle plot of the mass spectrum.
    """
    
    # Every Peak is represented by three dots in the line plot: (x, 0), (x, y), (x, 0)
    def create_spectra(x, y, zero=0):
        x = np.repeat(x, 3)
        y = np.repeat(y, 3)
        y[::3] = y[2::3] = zero
        return pd.DataFrame({"mz": x, "intensity": y})

    df = create_spectra(spec["mzarray"], spec["intarray"])

    # Create a scatter plot with the base color
    fig = go.Figure()

    # Add base line with a meaningful name
    fig.add_trace(go.Scatter(
        x=df["mz"], y=df["intensity"], 
        mode='lines', 
        line=dict(color=base_color, width=1),
        name='Peaks'  
    ))

    # Annotate every line with a string if annotation exists
    for mz, intensity, annotation in zip(spec["mzarray"], spec["intarray"], spec["anotarray"]):
        if pd.isna(annotation) or annotation.strip() == "":
            continue  # Skip annotation if it's missing or empty

        if intensity < 0.3:
            yshift_ = 60  # Adjust this value for peaks with high intensity
        else:
            yshift_ = 20  # Adjust this value for peaks with low intensity

        # Change the annotation color according to ion-type
        if "MI" in annotation:
            annotation_color = '#ff0000'  # Red for MI
        elif "y" in annotation:
            annotation_color = 'green'  # Green for y
        elif "[M" in annotation:
            annotation_color = 'darkmagenta'  # Dark Magenta for M
        else:
            annotation_color = 'blue'  # Default color for other annotations

        # Add annotation
        fig.add_annotation(
            x=mz,
            y=intensity,
            text=annotation,
            showarrow=False,
            arrowhead=1,
            arrowcolor=annotation_color,
            font=dict(size=12, color=annotation_color),
            xshift=0,
            yshift=yshift_,
            textangle=90  # Vertical
        )

        # Add a vertical line at the position of the peak with the annotation color
        fig.add_trace(go.Scatter(
            x=[mz, mz],
            y=[0, intensity],
            mode='lines',
            line=dict(color=annotation_color, width=1),
            showlegend=False
        ))

    fig.update_layout(
        showlegend=True,
        title_text=title,
        xaxis_title="m/z",
        yaxis_title="intensity",
        plot_bgcolor="rgb(255,255,255)",
    )
    fig.layout.template = "plotly_white"
    fig.update_yaxes(fixedrange=True)

    return fig
