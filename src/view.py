import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

from pyopenms import MSExperiment, MzMLFile


@st.cache_data
def getAnnotatedData(file):
    exp = MSExperiment()
    MzMLFile().load(str(Path(st.session_state["anno-mzMLs"], file)), exp)
    df = exp.get_df()
    df.insert(0, "mslevel", [spec.getMSLevel() for spec in exp])
    # df.insert(
    #     0,
    #     "precursormz",
    #     [
    #         spec.getPrecursors()[0].getMZ() if spec.getPrecursors() else 0
    #         for spec in exp
    #     ],
    # )
    if not df.empty:
        return df
    else:
        return pd.DataFrame()


@st.cache_data
def getDeconvMSData(file):
    exp = MSExperiment()
    MzMLFile().load(str(Path(st.session_state["deconv-mzML-files"], file)), exp)
    df = exp.get_df()

    df.insert(0, "mslevel", [spec.getMSLevel() for spec in exp])
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
    else:
        return pd.DataFrame()

@st.cache_resource
def plot_2D_map(df_ms1, df_ms2, cutoff):
    fig = go.Figure()
    ints = np.concatenate([df_ms1.loc[index, "intarray"] for index in df_ms1.index])
    int_filter = ints > cutoff  # show only ints over cutoff threshold
    ints = ints[int_filter]
    mzs = np.concatenate([df_ms1.loc[index, "mzarray"] for index in df_ms1.index])[
        int_filter
    ]
    rts = np.concatenate(
        [
            np.full(len(df_ms1.loc[index, "mzarray"]), df_ms1.loc[index, "RT"])
            for index in df_ms1.index
        ]
    )[int_filter]

    sort = np.argsort(ints)
    ints = ints[sort]
    mzs = mzs[sort]
    rts = rts[sort]

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

    # Add MS2 precursors
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
        # title="peak map 2D",
        xaxis_title="retention time",
        yaxis_title="m/z",
        plot_bgcolor="rgb(255,255,255)",
        showlegend=False,
        # width=1000,
        # height=800,
    )
    fig.layout.template = "plotly_white"

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
        selector=dict(type="scattergl"),
    )
    return fig


@st.cache_resource
def plot_bpc(df):
    intensity = np.array([max(intensity_array) for intensity_array in df["intarray"]])
    fig = px.line(df, x="RT", y=intensity)
    fig.update_traces(line_color="#555FF5", line_width=3)
    # fig.add_trace(
    #     go.Scatter(
    #         x=[ms1_rt],
    #         y=[intensity[np.abs(df["RT"] - ms1_rt).argmin()]],
    #         name="MS1 spectrum",
    #         text="MS1",
    #         textposition="top center",
    #         textfont=dict(color="#EF553B", size=20),
    #     )
    # )
    # fig.data[1].update(
    #     mode="markers+text",
    #     marker_symbol="x",
    #     marker=dict(color="#EF553B", size=12),
    # )
    # if ms2_rt > 0:
    #     fig.add_trace(
    #         go.Scatter(
    #             x=[ms2_rt],
    #             y=[intensity[np.abs(df["RT"] - ms2_rt).argmin()]],
    #             name="MS2 spectrum",
    #             text="MS2",
    #             textposition="top center",
    #             textfont=dict(color="#00CC96", size=20),
    #         )
    #     )
    #     fig.data[2].update(
    #         mode="markers+text",
    #         marker_symbol="x",
    #         marker=dict(color="#00CC96", size=12),
    #     )
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
    """

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
    st.plotly_chart(fig, use_container_width=True)
    return

@st.cache_resource
def plot_3D_signal_view(spec, title):
    return
