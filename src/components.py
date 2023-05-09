import streamlit.components.v1 as components

class PlotlyHeatmap:
    title = None
    x = []
    y = []
    intensity = []

    _plotly_heatmap = components.declare_component(
        "plotly_heatmap", 
        url="http://localhost:5173",
      )

    def __init__(self, title, x, y, intensity):
        self.title = title
        self.x = x
        self.y = y
        self.intensity = intensity
    
    def addComponent(self, key=None):
        return self._plotly_heatmap(title=self.title, x=self.x, y=self.y, intensity=self.intensity, key=key)



