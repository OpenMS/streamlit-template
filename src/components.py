import json
import streamlit.components.v1 as st_components

DATA_OBJ_NAMES = [
    'raw_heatmap_df',
    'deconv_heatmap_df',
    'per_scan_data',
    'sequence_data'
]

class FlashViewerGrid:
    columns = None
    rows = None
    components = []
    data = {}

    _flash_viewer_grid = st_components.declare_component(
        "flash_viewer_grid",
        url="http://localhost:5173",
    )

    def __init__(self, components, data, columns=1, rows=1):
        self.columns = columns
        self.rows = rows
        self.components = components
        self.data = {}
        for key, df in data.items():
            if type(df) is dict:
                self.data[key] = json.dumps(df)
            else:
                self.data[key] = df.to_json(orient='records')

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
            data_for_drawing=self.data,
            key=key,
        )

class FlashViewerComponent:
    componentLayout = None
    componentArgs = None

    def __init__(self, component_args, component_layout):
        self.componentLayout = component_layout
        self.componentArgs = component_args

class ComponentLayout:
    width = None
    height = None

    def __init__(self, width=None, height=None):
        self.width = width
        self.height = height

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
    def __init__(self, title):
        self.title = title
        self.componentName = "PlotlyLineplot"

class Plotly3Dplot:
    def __init__(self, title):
        self.title = title
        self.componentName = "Plotly3Dplot"

class SequenceView:
    def __init__(self):
        self.componentName = 'SequenceView'
