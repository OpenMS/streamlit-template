import json

import pandas as pd
import streamlit.components.v1 as st_components

DATAFRAME_NAMES = [
    'raw_heatmap_df',
    'deconv_heatmap_df',
    'per_scan_data'
]

class FlashViewerGrid:
    columns = None
    rows = None
    components = []
    dataframes = {}

    _flash_viewer_grid = st_components.declare_component(
        "flash_viewer_grid",
        url="http://localhost:5173",
    )

    def __init__(self, components, dataframes, columns=1, rows=1):
        self.columns = columns
        self.rows = rows
        self.components = components
        self.dataframes = {key: df.to_json(orient='records') for key, df in dataframes.items()}

    def addGrid(self, key=None):
        return self._flash_viewer_grid(
            columns=self.columns,
            rows=self.rows,
            components=list(
                map(
                    lambda component: { 
                        "componentLayout": component.componentLayout.__dict__, 
                        "componentArgs": component.componentArgs.__dict__ 
                    }, 
                    self.components
                )
            ),
            dataframes=self.dataframes,
            key=key,
        )

class FlashViewerComponent:
    componentLayout = None
    componentArgs = None

    def __init__(self, component_args, component_layout):
        self.componentLayout = component_layout
        self.componentArgs = component_args
    
    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)

class ComponentLayout:
    width = None
    height = None

    def __init__(self, width=None, height=None):
        self.width = width
        self.height = height

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)

class PlotlyHeatmap:
    title = None
    x = []
    y = []
    intensity = []
    showLegend = None

    def __init__(self, title, df, show_legend=False):
        self.title = title
        self.x = list(df['rt'])
        self.y = list(df['mass'])
        self.intensity = list(df['intensity'])
        self.show_legend = show_legend
        self.componentName = "PlotlyHeatmap"

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)

class ScanTable:
    class Column:
        def __init__(self, title, field):
            self.title = title
            self.field = field

        def toJson(self):
            return json.dumps(self, default=lambda o: o.__dict__)

    def __init__(self, df, title=None, show_legend=False):
        self.componentName = "TabulatorTable"
        self.data = df.to_json(orient='records')
        self.title = title
        self.columns = [
            self.Column(title='Index', field='index').toJson(),
            self.Column(title='Scan', field='Scan').toJson(),
            self.Column(title='MSLevel', field='MSLevel').toJson(),
            self.Column(title='RT', field='RT').toJson(),
            self.Column(title='Precursor Mass', field='PrecursorMass').toJson(),
            self.Column(title='# Masses', field='#Masses').toJson(),
        ]

class MassTable:
    class Column:
        def __init__(self, title, field):
            self.title = title
            self.field = field

        def toJson(self):
            return json.dumps(self, default=lambda o: o.__dict__)

    def __init__(self, df, title=None, show_legend=False):
        self.componentName = "TabulatorTable"
        self.data = df.to_json(orient='records')
        self.title = title
        self.columns = [
            self.Column(title='Index', field='index').toJson(),
            self.Column(title='Mono mass', field='Mono mass').toJson(),
            self.Column(title='Sum intensity', field='Sum intensity').toJson(),
            self.Column(title='Min charge', field='Min charge').toJson(),
            self.Column(title='Max charge', field='Max charge').toJson(),
            self.Column(title='Min isotope', field='Min isotope').toJson(),
            self.Column(title='Max isotope', field='Max isotope').toJson(),
            self.Column(title='Cosine score', field='Cosine Score').toJson(),
            self.Column(title='SNR', field='SNR').toJson(),
            self.Column(title='QScore', field='QScore').toJson(),
        ]

class PlotlyLineplot:
    title = None
    x = []
    y = []

    def __init__(self, title, x, y):
        self.title = title
        self.x = x
        self.y = y
        self.componentName = "PlotlyLineplot"

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)

class Plotly3Dplot:
    title = None
    signal_x, signal_y, signal_z = [], [], []
    noise_x, noise_y, noise_z = [], [], []

    def __init__(self, title, signal_df, noise_df):
        self.title = title
        self.signal_x = list(signal_df['charge'])
        self.signal_y = list(signal_df['mass'])
        self.signal_z = list(signal_df['intensity'])
        self.noise_x = list(noise_df['charge'])
        self.noise_y = list(noise_df['mass'])
        self.noise_z = list(noise_df['intensity'])
        self.componentName = "Plotly3Dplot"

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)