import os
import streamlit.components.v1 as components

COMPONENT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fabric_frontend_v6_manualsync"
)

fabric_canvas = components.declare_component(
    "fabric_canvas_v6_manualsync",
    path=COMPONENT_DIR
)
