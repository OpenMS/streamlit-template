import time

import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode
from st_aggrid.shared import GridUpdateMode

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
    return fig

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
    return fig

@st.cache_resource
def plot3DSignalView(signal_3d_df, noisy_3d_df, title):
    """
    Takes a pandas series (spec) and generates a needle 3D plot
    with mass, charge, intensity dimension
    mass is in y-axis dimension to show masses in ascending order
    """

    def create_spectra(x, y, z, zero=0):
        x = np.repeat(x, 3) # charge
        y = np.repeat(y, 3) # mass
        z = np.repeat(z, 3) # intensity
        # to draw vertical lines
        z[::3] = 0
        z[2::3] = np.nan
        return pd.DataFrame({"charge": x, "mass":y, "intensity": z})

    #drawing dropline from scatter plot marker (vertical lines)
    dfs = create_spectra(signal_3d_df["charge"], signal_3d_df["mass"], signal_3d_df["intensity"])
    dfs['color'] = 'Signal'
    dfn = create_spectra(noisy_3d_df["charge"], noisy_3d_df["mass"], noisy_3d_df["intensity"])
    dfn['color'] = 'Noise'
    df = pd.concat([dfs, dfn])

    # drawing lines
    fig = px.line_3d(df, x="charge", y="mass", z="intensity", color='color',
                     color_discrete_sequence=px.colors.qualitative.G10,)
    fig.update_traces(connectgaps=False)

    # drawing scatter plot for markers on the tip of vertical lines
    fig.add_trace(go.Scatter3d(x=signal_3d_df["charge"],
                               y=signal_3d_df["mass"],
                               z=signal_3d_df["intensity"],
                               marker=dict(size=5, color = px.colors.qualitative.G10[0], opacity=0.5, symbol='circle'),
                               showlegend=False,
                               mode="markers"))

    fig.add_trace(go.Scatter3d(x=noisy_3d_df["charge"],
                               y=noisy_3d_df["mass"],
                               z=noisy_3d_df["intensity"],
                               marker=dict(size=2, color = px.colors.qualitative.G10[1], opacity=0.5, symbol = 'x'),
                               showlegend=False,
                               mode="markers"))

    # initial view of the plot: mass-intensity plane
    camera = dict(
        eye=dict(x=2.5, y=0, z=0.2) #
    )

    fig.update_layout(
        height=800,
        title=dict(
            text=title,
            font_size=20,
            x=0.4
        ),
        showlegend=True,
        legend_title='',
        scene=dict(
            xaxis_title='Charge',
            yaxis_title='Mass',
            zaxis_title='Intensity'),
        # plot_bgcolor="rgb(255,255,255)",
        scene_camera=camera,
    )
    return fig

def drawSpectraTable(in_df: pd.DataFrame, table_height=400):
    """
    Takes a pandas dataframe and generates interactive table (listening to row selection)
    """
    options = GridOptionsBuilder.from_dataframe(in_df)
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
def plotMS1HeatMap(df, plot_title, legends_colname=[]):
    masses, rts, intys = df['mass'], df['rt'], df['intensity']
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            name="raw peaks",
            x=rts,
            y=masses,
            mode='markers',
            marker=dict(
                color=intys,
                size=3,
                showscale = True,
            ),
        )
    )
    fig.update_traces(marker_colorscale="viridis",
                      marker_colorbar=dict(
                          title="Intensity",
                          thickness=5,
                      ),
                      hovertext=intys.round(),
                      selector=dict(type="scattergl"))

    show_legend = True if legends_colname else False
    fig.update_layout(
        title=dict(
            text=plot_title,
            x=.4
        ),
        showlegend=show_legend,
        xaxis_title='Retention Time',
        yaxis_title='Monoisotopic Mass',
    )
    return fig