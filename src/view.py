import numpy as np
import pandas as pd
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pyopenms as poms

from typing import Union

@st.cache_data
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
    df = exp.get_df()
    # MSlevel for each scan
    df.insert(0, "mslevel", [spec.getMSLevel() for spec in exp])
    # Precursor m/z for each scan
    df.insert(
        0,
        "precursormz",
        [
            spec.getPrecursors()[0].getMZ() if spec.getPrecursors() else 0
            for spec in exp
        ],
    )
    if not df.empty:
        return df
    return pd.DataFrame()


@st.cache_resource
def plot_2D_map(df_ms1: pd.DataFrame, df_ms2: pd.DataFrame, cutoff: int) -> go.Figure:
    """
    Plots a 2D peak map.

    This function takes two dataframes (`df_ms1` and `df_ms2`) and a cutoff value (`cutoff`) as input, and
    returns a plotly Figure object containing a 2D peak map.

    Args:
        df_ms1 (pd.DataFrame): A pandas DataFrame containing the MS1 peak information.
        df_ms2 (pd.DataFrame): A pandas DataFrame containing the MS2 peak information.
        cutoff (int): The cutoff threshold for the intensity filter.

    Returns
    -------
    fig : plotly.graph_objs._figure.Figure
        The plotly Figure object containing the 2D peak map.
    """
    fig = go.Figure()
    # Get all intensities in a 1D array
    ints = np.concatenate([df_ms1.loc[index, "intarray"] for index in df_ms1.index])
    # Keep intensities over cutoff threshold
    int_filter = ints > cutoff
    ints = ints[int_filter]
    # Based on the intensity filter, filter mz and RT values as well
    mzs = np.concatenate([df_ms1.loc[index, "mzarray"] for index in df_ms1.index])[
        int_filter
    ]
    rts = np.concatenate(
        [
            np.full(len(df_ms1.loc[index, "mzarray"]), df_ms1.loc[index, "RT"])
            for index in df_ms1.index
        ]
    )[int_filter]
    # Sort in ascending order to plot highest intensities last
    sort = np.argsort(ints)
    ints = ints[sort]
    mzs = mzs[sort]
    rts = rts[sort]
    # Use Scattergl (webgl) for efficient scatter plot
    fig.add_trace(
        go.Scattergl(
            name="peaks",
            x=rts,
            y=mzs,
            mode="markers",
            marker_color=ints,
            marker_symbol="square",
        )
    )
    # Add MS2 precursors as green markers
    fig.add_trace(
        go.Scattergl(
            name="peaks",
            x=df_ms2["RT"],
            y=df_ms2["precursormz"],
            mode="markers",
            marker_color="#00FF00",
            marker_symbol="x",
        )
    )
    fig.update_layout(
        xaxis_title="retention time",
        yaxis_title="m/z",
        plot_bgcolor="rgb(255,255,255)",
        showlegend=False,
    )
    fig.layout.template = "plotly_white"
    # Set color scale
    color_scale = [
        (0.00, "rgba(233, 233, 233, 1.0)"),
        (0.01, "rgba(243, 236, 166, 1.0)"),
        (0.1, "rgba(255, 168, 0, 1.0)"),
        (0.2, "rgba(191, 0, 191, 1.0)"),
        (0.4, "rgba(68, 0, 206, 1.0)"),
        (1.0, "rgba(33, 0, 101, 1.0)"),
    ]
    fig.update_traces(
        marker_colorscale=color_scale,
        hovertext=ints.round(),
        selector={"type": 'scattergl'},
    )
    return fig


@st.cache_resource
def plot_bpc(df: pd.DataFrame) -> go.Figure:
    """Plot the base peak chromatogram (BPC) from a given dataframe.

    Args:
        df: A pandas DataFrame containing the data to be plotted. The DataFrame should
            contain columns named 'RT' and 'intarray', representing the retention time
            and intensity values, respectively, for each data point.

    Returns:
        A plotly Figure object containing the BPC plot.
    """
    intensity = np.array([max(intensity_array) for intensity_array in df["intarray"]])
    fig = px.line(df, x="RT", y=intensity)
    fig.update_traces(line_color="#555FF5", line_width=3)
    fig.update_traces(showlegend=False)
    fig.update_layout(
        showlegend=False,
        # title_text="base peak chromatogram (BPC)",
        xaxis_title="retention time (s)",
        yaxis_title="intensity (cps)",
        plot_bgcolor="rgb(255,255,255)",
        width=1000,
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
    fig.update_layout(
        showlegend=False,
        title_text=title,
        xaxis_title="m/z",
        yaxis_title="intensity",
        plot_bgcolor="rgb(255,255,255)",
    )
    fig.layout.template = "plotly_white"
    fig.update_yaxes(fixedrange=True)
    return fig
