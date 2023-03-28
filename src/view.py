import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode
from st_aggrid.shared import GridUpdateMode

from pyopenms import MSExperiment, MzMLFile


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
def plotDeconvolutedMS(spec):
    """
    Takes a pandas Series (spec) and generates a needle plot with m/z and intensity dimension.
    """

    def create_spectra(x, y, zero=0):
        x = np.repeat(x, 3)
        y = np.repeat(y, 3)
        y[::3] = y[2::3] = zero
        return pd.DataFrame({"Mass": x, "Intensity": y})

    df = create_spectra(spec["mzarray"], spec["intarray"])
    fig = px.line(df, x="Mass", y="Intensity")
    # fig.update_traces(line_color=color)
    fig.update_layout(
        showlegend=False,
        title_text='Retention time: %f'%spec["RT"],
        xaxis_title="Monoisotopic Mass",
        yaxis_title="Intensity",
        # plot_bgcolor="rgb(255,255,255)",
    )
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, use_container_width=True)
    return

@st.cache_resource
def plot3DSignalView(spec):
    """
    Takes a pandas series (spec) and generates a needle 3D plot
    with m/z, retention time, intensity dimension
    """

    def create_spectra(x, y, z, zero=0):
        x = np.repeat(x, 3) # mz
        y = np.repeat(y, 3) # rt
        z = np.repeat(z, 3) # intensity
        # to draw vertical lines
        z[::3] = 0
        z[2::3] = np.nan
        return pd.DataFrame({"mz": x, "rt":y, "intensity": z})

    # for testing, generate rts
    rts = np.repeat(spec["RT"], len(spec["mzarray"]))

    # drawing dropline from scatter plot marker (vertical lines)
    df = create_spectra(spec["mzarray"], rts, spec["intarray"])
    fig = px.line_3d(df, x="mz", y="rt", z="intensity")
    fig.update_traces(connectgaps=False)

    # drawing scatte plot for markers on the tip of vertical lines
    fig.add_trace(go.Scatter3d(x=spec["mzarray"],
                               y=rts,
                               z=spec["intarray"],
                               mode="markers"))

    fig.update_layout(
        showlegend=False,
        scene=dict(
            xaxis_title='Mass',
            yaxis_title='Retention time',
            zaxis_title='Intensity'),
        plot_bgcolor="rgb(255,255,255)",
    )
    # fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, use_container_width=True)

    return

def drawSpectraTable(in_df: pd.DataFrame):
    """
    Takes a pandas dataframe and generates interactive table (listening to row selection)
    """

    options = GridOptionsBuilder.from_dataframe(
        in_df, enableRowGroup=True, enableValue=True, enablePivot=True
    )

    options.configure_selection("single")
    options.configure_side_bar() # sidebar of table
    selection = AgGrid(
        in_df,
        height=400,
        enable_enterprise_modules=True,
        gridOptions=options.build(),
        update_mode=GridUpdateMode.MODEL_CHANGED,
        # allow_unsafe_jscode=True,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW
    )
    return selection
