import os
import json
import streamlit.components.v1 as st_components

# Create a _RELEASE constant. We'll set this to False while we're developing
# the component, and True when we're ready to package and distribute it.
_RELEASE = False


def flash_viewer_grid_component(components, data, component_key='flash_viewer_grid'):

    if not _RELEASE:
        _component_func = st_components.declare_component(
            "flash_viewer_grid",
            url="http://localhost:5173",
    )
    else:
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        build_dir = os.path.join(parent_dir, '..', "js-component", "dist")
        _component_func = st_components.declare_component("flash_viewer_grid", path=build_dir)

    out_components = []
    for row in components:
        out_components.append(list(map(lambda component: {"componentArgs": component.componentArgs.__dict__}, row)))

    data_for_drawing = {}
    for key, df in data.items():
        if type(df) is dict:
            data_for_drawing[key] = json.dumps(df)
        else:
            data_for_drawing[key] = df.to_json(orient='records')

    component_value = _component_func(
        components=out_components,
        data_for_drawing=data_for_drawing,
        key=component_key
    )

    return component_value


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
        elif table_type == 'ProteinTable':
            self.title = 'Protein Table'
            self.componentName = "TabulatorProteinTable"
        elif table_type == 'TagTable':
            self.title = 'Tag Table'
            self.componentName = "TabulatorTagTable"


class PlotlyLineplot:
    def __init__(self, title):
        self.title = title
        self.componentName = "PlotlyLineplot"


class PlotlyLineplotTagger:
    def __init__(self, title):
        self.title = title
        self.componentName = "PlotlyLineplotTagger"


class Plotly3Dplot:
    def __init__(self, title):
        self.title = title
        self.componentName = "Plotly3Dplot"


class SequenceView:
    def __init__(self):
        self.componentName = 'SequenceView'


class SequenceViewTagger:
    def __init__(self):
        self.componentName = 'SequenceViewTagger'


class InternalFragmentMap:
    def __init__(self):
        self.componentName = 'InternalFragmentMap'


class FLASHQuant:
    def __init__(self):
        self.componentName = 'FLASHQuantView'
