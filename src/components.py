import json
import streamlit.components.v1 as st_components

DATA_OBJ_NAMES = [
    'raw_heatmap_df',
    'deconv_heatmap_df',
    'per_scan_data',
    'sequence_data'
]

class FlashViewerGrid:
    components = [[]]
    data = {}

    _flash_viewer_grid = st_components.declare_component(
        "flash_viewer_grid",
        url="http://localhost:5173",
    )

    def __init__(self, components, data):
        self.components = components
        self.data = {}
        for key, df in data.items():
            if type(df) is dict:
                self.data[key] = json.dumps(df)
            else:
                self.data[key] = df.to_json(orient='records')

    def addGrid(self, key=None):
        out_components = []
        for row in self.components:
            out_components.append(list(map(lambda component: {"componentArgs": component.componentArgs.__dict__}, row)))
        return self._flash_viewer_grid(
            components=out_components,
            data_for_drawing=self.data,
            key=key,
        )

class FlashViewerComponent:
    componentArgs = None

    def __init__(self, component_args):
        self.componentArgs = component_args


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
