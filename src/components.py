import json
import streamlit.components.v1 as st_components

class FlashViewerGrid:
    columns = None
    rows = None
    components = []

    _flash_viewer_grid = st_components.declare_component(
        "flash_viewer_grid",
        url="http://localhost:5173",
    )

    def __init__(self, components, columns=1, rows=1):
        self.columns = columns
        self.rows = rows
        self.components = components

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

    def __init__(self, title, x, y, intensity, show_legend=False):
        self.title = title
        self.x = x
        self.y = y
        self.intensity = intensity
        self.show_legend = show_legend
        self.componentName = "PlotlyHeatmap"

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)
