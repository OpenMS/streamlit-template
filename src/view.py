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
def plotDeconvolvedMS(spec):
    """
    Takes a pandas Series (spec) and generates a needle plot with mass and intensity dimension.
    """

    def create_spectra(x, y):
        x = np.repeat(x, 3)
        y = np.repeat(y, 3)
        # to draw vertical lines
        y[::3] = 0
        y[2::3] = np.nan
        return pd.DataFrame({"Mass": x, "Intensity": y})

    df = create_spectra(spec["mzarray"], spec["intarray"])
    fig = px.line(df, x="Mass", y="Intensity",
                  height=300)
    # fig.update_traces(line_color=color)
    fig.update_layout(
        showlegend=False,
        xaxis_title="Monoisotopic Mass",
        yaxis_title="Intensity",
        title={
            'text': "Deconvolved Spectrum",
            'x' : 0.5,
            'xanchor': 'center',
            'yanchor': 'top'}
    )
    fig.update_yaxes(fixedrange=True)
    fig.update_traces(connectgaps=False)
    st.plotly_chart(fig, use_container_width=True)
    return

@st.cache_resource
def plotAnnotatedMS(spec):
    """
    Takes a pandas Series (spec) and generates a needle plot with mass and intensity dimension.
    """

    def create_spectra(x, y, zero=0):
        x = np.repeat(x, 3)
        y = np.repeat(y, 3)
        y[::3] = y[2::3] = zero
        return pd.DataFrame({"Mass": x, "Intensity": y})

    df = create_spectra(spec["mzarray"], spec["intarray"])
    fig = px.line(df, x="Mass", y="Intensity",
                  height=300)
    # fig.update_traces(line_color=color)
    fig.update_layout(
        showlegend=False,
        xaxis_title="Monoisotopic Mass",
        yaxis_title="Intensity",
        title={
            'text': "Annotated spectrum",
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top'}
    )
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, use_container_width=True)
    return

@st.cache_resource
def plot3DSignalView(signal_3d_df, noisy_3d_df):
    """
    Takes a pandas series (spec) and generates a needle 3D plot
    with mass, charge, intensity dimension
    """

    def create_spectra(x, y, z, zero=0):
        x = np.repeat(x, 3) # mass
        y = np.repeat(y, 3) # charge
        z = np.repeat(z, 3) # intensity
        # to draw vertical lines
        z[::3] = 0
        z[2::3] = np.nan
        return pd.DataFrame({"mass": x, "charge":y, "intensity": z})
    #drawing dropline from scatter plot marker (vertical lines)

    dfs = create_spectra(signal_3d_df["mass"], signal_3d_df["charge"], signal_3d_df["intensity"])
    dfs['color'] = 's'
    dfn = create_spectra(noisy_3d_df["mass"], noisy_3d_df["charge"], noisy_3d_df["intensity"])
    dfn['color'] = 'n'
    df = pd.concat([dfs, dfn])

    # drawing lines
    fig = px.line_3d(df, x="mass", y="charge", z="intensity", color='color',
                     color_discrete_sequence=px.colors.qualitative.G10,)
    fig.update_traces(connectgaps=False)

    # drawing scatter plot for markers on the tip of vertical lines
    fig.add_trace(go.Scatter3d(x=signal_3d_df["mass"],
                               y=signal_3d_df["charge"],
                               z=signal_3d_df["intensity"],
                               marker=dict(size=2, color = px.colors.qualitative.G10[0], opacity=0.5),
                               mode="markers"))

    fig.add_trace(go.Scatter3d(x=noisy_3d_df["mass"],
                               y=noisy_3d_df["charge"],
                               z=noisy_3d_df["intensity"],
                               marker=dict(size=2, color = px.colors.qualitative.G10[1], opacity=0.5, symbol = 'x'),
                               mode="markers"))
    fig.update_traces(opacity=0.5)
    fig.update_layout(
        showlegend=False,
        scene=dict(
            xaxis_title='Mass',
            yaxis_title='Charge',
            zaxis_title='Intensity'),
        plot_bgcolor="rgb(255,255,255)",
    )
    # fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, use_container_width=True)

    return

def drawSpectraTable(in_df: pd.DataFrame, table_height=400):
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
        height=table_height,
        enable_enterprise_modules=True,
        gridOptions=options.build(),
        update_mode=GridUpdateMode.MODEL_CHANGED,
        # allow_unsafe_jscode=True,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_ALL_COLUMNS_TO_VIEW
    )
    return selection

@st.cache_resource
def plotHeatMap():
    st.write('Place for heatmap')
