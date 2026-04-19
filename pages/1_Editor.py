import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import cv2
import io
import os
import math
import svgwrite
import base64
from datetime import datetime
from fabric_component import fabric_canvas

st.set_page_config(page_title="Editor", layout="wide")

# =========================
# 工具函式
# =========================
def pil_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def transform_image(img, scale, rotation):
    w, h = img.size
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    img = img.rotate(-rotation, expand=True)
    return img

def paste_center(base, img, x, y):
    x = int(x - img.width / 2)
    y = int(y - img.height / 2)
    base.alpha_composite(img, (x, y))


# =========================
# ⭐⭐ 關鍵修改：預設縮放 ⭐⭐
# =========================
def default_layout_for_new_item(index, canvas_width, canvas_height):
    default_positions = [
        (300, 300), (900, 300), (300, 900), (900, 900)
    ]

    if index < len(default_positions):
        pos_x = default_positions[index][0] * (canvas_width / 1200)
        pos_y = default_positions[index][1] * (canvas_height / 1800)
    else:
        pos_x = canvas_width / 2
        pos_y = canvas_height / 2

    # ⭐⭐ 手機版縮小 ⭐⭐
    if canvas_width <= 1400:
        default_scale = 0.5
    else:
        default_scale = 0.8

    return {
        "x": int(pos_x),
        "y": int(pos_y),
        "scale": default_scale,
        "rotation": 0,
        "z": index
    }


# =========================
# 主程式
# =========================
st.title("排版 Editor")

if "processed_items" not in st.session_state or len(st.session_state.processed_items) == 0:
    st.warning("沒有素材")
    st.stop()

canvas_width = int(st.session_state.get("canvas_width", 1200))
canvas_height = int(st.session_state.get("canvas_height", 1800))

# 背景
bg = None
if st.session_state.get("uploaded_bg_image"):
    bg = st.session_state.uploaded_bg_image
elif st.session_state.get("selected_bg_path"):
    bg = Image.open(st.session_state.selected_bg_path)

bg_b64 = pil_to_base64(bg) if bg else None

# =========================
# 建立 frontend items
# =========================
frontend_items = []

for i, item in enumerate(st.session_state.processed_items):
    layout = default_layout_for_new_item(i, canvas_width, canvas_height)

    frontend_items.append({
        "id": i,
        "b64": pil_to_base64(item["image"]),
        "x": layout["x"],
        "y": layout["y"],
        "scale": layout["scale"],
        "rotation": layout["rotation"]
    })

layout_data = fabric_canvas(
    canvas_width=canvas_width,
    canvas_height=canvas_height,
    bg_b64=bg_b64,
    items=frontend_items,
    key="editor"
)

# =========================
# 產生成品
# =========================
if layout_data:
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255,255,255,255))

    if bg:
        bg_resized = bg.resize((canvas_width, canvas_height))
        canvas.alpha_composite(bg_resized)

    for obj in layout_data:
        img = st.session_state.processed_items[obj["id"]]["image"]
        img = transform_image(img, obj["scale"], obj["rotation"])
        paste_center(canvas, img, obj["x"], obj["y"])

    st.image(canvas)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")

    st.download_button(
        "下載 PNG",
        data=buf.getvalue(),
        file_name="result.png",
        mime="image/png"
    )
