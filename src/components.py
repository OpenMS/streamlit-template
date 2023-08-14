import json
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
    showLegend = None

    def __init__(self, title, show_legend=False):
        self.title = title
        self.show_legend = show_legend
        self.componentName = "PlotlyHeatmap"

class Tabulator:
    def __init__(self, table_type):
        if table_type == 'ScanTable':
            self.title = 'Scan Table'
            self.componentName = "TabulatorScanTable"
        elif table_type == 'MassTable':
            self.title = 'Mass Table'
            self.componentName = "TabulatorMassTable"

class PlotlyLineplot:
    title = None

    def __init__(self, title):
        self.title = title
        self.componentName = "PlotlyLineplot"

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