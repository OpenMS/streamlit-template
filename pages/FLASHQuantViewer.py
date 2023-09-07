from src.common import defaultPageSetup
import streamlit.components.v1 as st_components


def content():
    defaultPageSetup('FLASHQuant Viewer')
    _flash_viewer_grid = st_components.declare_component("flash_viewer_grid",
                                                         url="http://localhost:5173")
    _flash_viewer_grid(components=[[{'componentArgs': {'componentName': 'FLASHQuantView'}}]])


if __name__ == "__main__":
    content()
