import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps
import numpy as np
import cv2
import io
import os
import math
import svgwrite
import base64
import shutil
from datetime import datetime

st.set_page_config(
    page_title="Editor - Joe's Snapshot",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# =========================
# CSS
# =========================
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.8rem;
        padding-bottom: 2rem;
        padding-left: 0.9rem;
        padding-right: 0.9rem;
        max-width: 1200px;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-top: 0.5rem;
            padding-left: 0.65rem;
            padding-right: 0.65rem;
        }
    }

    div[data-testid="stImage"] img {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================
# 防呆
# =========================
if "processed_items" not in st.session_state or len(st.session_state.processed_items) == 0:
    st.warning("目前沒有可排版的素材，請先回 Home 頁完成去背。")
    st.page_link("Home.py", label="回到 Home", icon="🏠")
    st.stop()


# =========================
# 工具函式
# =========================
def pil_to_bytes(img: Image.Image, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def pil_to_base64(img: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


def get_selected_background():
    if st.session_state.get("uploaded_bg_image") is not None:
        return st.session_state.uploaded_bg_image.convert("RGBA")
    if st.session_state.get("selected_bg_path") is not None and os.path.exists(st.session_state.selected_bg_path):
        return Image.open(st.session_state.selected_bg_path).convert("RGBA")
    return None


def transform_image(img: Image.Image, scale: float = 1.0, rotation: float = 0.0) -> Image.Image:
    w, h = img.size
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    rotated = resized.rotate(rotation, expand=True, resample=Image.BICUBIC)
    return rotated


def paste_centered(base: Image.Image, overlay: Image.Image, center_x: int, center_y: int):
    x = int(center_x - overlay.width / 2)
    y = int(center_y - overlay.height / 2)
    base.alpha_composite(overlay, (x, y))


def build_final_canvas(bg_image: Image.Image, sticker_items: list, canvas_width: int, canvas_height: int) -> Image.Image:
    if bg_image is None:
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
    else:
        canvas = bg_image.convert("RGBA").resize((canvas_width, canvas_height), Image.LANCZOS)

    sorted_items = sorted(sticker_items, key=lambda x: x["z"])

    for item in sorted_items:
        transformed = transform_image(item["image"], scale=item["scale"], rotation=item["rotation"])
        paste_centered(canvas, transformed, item["x"], item["y"])

    return canvas


def make_ratio_card_preview(img: Image.Image, card_size=(260, 390), bg_color=(245, 245, 245, 255)) -> Image.Image:
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", card_size, bg_color)
    fitted = ImageOps.contain(img, card_size, Image.LANCZOS)
    x = (card_size[0] - fitted.width) // 2
    y = (card_size[1] - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
    return canvas


def show_ratio_card_preview(img: Image.Image, caption: str = "完整成品預覽"):
    preview = make_ratio_card_preview(img, card_size=(260, 390))
    st.image(preview, caption=caption, use_container_width=False, width=260)


# =========================
# SVG 刀模工具
# =========================
def get_largest_contour_from_alpha(rgba_image: Image.Image, threshold: int = 1, approx_epsilon_ratio: float = 0.002):
    rgba = rgba_image.convert("RGBA")
    arr = np.array(rgba)
    alpha = arr[:, :, 3]
    _, mask = cv2.threshold(alpha, threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(contour, True)
    epsilon = approx_epsilon_ratio * peri
    return cv2.approxPolyDP(contour, epsilon, True)


def contour_to_points(contour):
    if contour is None:
        return []
    pts = contour.reshape(-1, 2)
    return [(float(x), float(y)) for x, y in pts]


def transform_points_for_canvas(points, original_width, original_height, scale, rotation_deg, center_x, center_y):
    if not points:
        return []

    scaled_w = original_width * scale
    scaled_h = original_height * scale
    cx_local, cy_local = scaled_w / 2.0, scaled_h / 2.0
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    corners = [(0, 0), (scaled_w, 0), (scaled_w, scaled_h), (0, scaled_h)]
    rotated_corners = []
    for x, y in corners:
        dx, dy = x - cx_local, y - cy_local
        rx, ry = dx * cos_t - dy * sin_t, dx * sin_t + dy * cos_t
        rotated_corners.append((rx, ry))

    min_rx = min(p[0] for p in rotated_corners)
    min_ry = min(p[1] for p in rotated_corners)
    max_rx = max(p[0] for p in rotated_corners)
    max_ry = max(p[1] for p in rotated_corners)
    rotated_w, rotated_h = max_rx - min_rx, max_ry - min_ry

    final_points = []
    for x, y in points:
        sx, sy = x * scale, y * scale
        dx, dy = sx - cx_local, sy - cy_local
        rx, ry = dx * cos_t - dy * sin_t, dx * sin_t + dy * cos_t
        ex, ey = rx - min_rx, ry - min_ry
        canvas_x = ex + (center_x - rotated_w / 2.0)
        canvas_y = ey + (center_y - rotated_h / 2.0)
        final_points.append((canvas_x, canvas_y))
    return final_points


def points_to_svg_path(points):
    if not points:
        return ""
    path = f"M {points[0][0]:.2f},{points[0][1]:.2f} "
    for x, y in points[1:]:
        path += f"L {x:.2f},{y:.2f} "
    path += "Z"
    return path


def create_svg_cutline(sticker_items, canvas_width, canvas_height, include_background_rect=False):
    dwg = svgwrite.Drawing(
        size=(f"{canvas_width}px", f"{canvas_height}px"),
        viewBox=f"0 0 {canvas_width} {canvas_height}"
    )

    if include_background_rect:
        dwg.add(
            dwg.rect(
                insert=(0, 0),
                size=(canvas_width, canvas_height),
                fill="none",
                stroke="#dddddd",
                stroke_width=1
            )
        )

    visible_items = sorted(sticker_items, key=lambda x: x["z"])

    for idx, item in enumerate(visible_items, start=1):
        contour = get_largest_contour_from_alpha(item["image"])
        if contour is None:
            continue

        raw_points = contour_to_points(contour)
        transformed_points = transform_points_for_canvas(
            raw_points,
            item["image"].width,
            item["image"].height,
            item["scale"],
            item["rotation"],
            item["x"],
            item["y"]
        )

        path_d = points_to_svg_path(transformed_points)
        if not path_d:
            continue

        dwg.add(
            dwg.path(
                d=path_d,
                fill="none",
                stroke="#000000",
                stroke_width=1,
                id=f"cutline_{idx}"
            )
        )

    return dwg.tostring().encode("utf-8")


# =========================
# Fabric 前端
# =========================
FABRIC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js"></script>
    <style>
        html, body {
            margin: 0;
            padding: 0;
            background: #f8f8f8;
            font-family: sans-serif;
            overflow-x: hidden;
            width: 100%;
        }

        .outer {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
        }

        .tools {
            width: 100%;
            max-width: 980px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            padding-top: 8px;
        }

        .tools button {
            padding: 10px 18px;
            font-size: 15px;
            cursor: pointer;
            background-color: #FF4B4B;
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: bold;
        }

        .tools button:hover {
            background-color: #ff3636;
        }

        .tip {
            color: #666;
            font-size: 13px;
            text-align: center;
            line-height: 1.5;
            padding: 0 10px;
        }

        .canvas-wrap {
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            overflow: visible;
        }

        .canvas-shell {
            background: white;
            border: 1px solid #ddd;
            box-shadow: 0 4px 14px rgba(0,0,0,0.08);
            border-radius: 14px;
            padding: 6px;
            display: inline-block;
            max-width: 100%;
        }

        canvas {
            display: block;
            touch-action: none;
        }
    </style>
</head>
<body>
    <div class="outer">
        <div class="tools">
            <button id="sync-btn">確認排版並產生下載檔</button>
            <div class="tip">直接在這張固定比例卡片上拖曳、縮放、旋轉人物。</div>
        </div>

        <div class="canvas-wrap">
            <div class="canvas-shell">
                <canvas id="c"></canvas>
            </div>
        </div>
    </div>

    <script>
        function sendMessageToStreamlitClient(type, data) {
            window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
        }

        function Streamlit_setComponentValue(value) {
            sendMessageToStreamlitClient("streamlit:setComponentValue", {value: value});
        }

        function Streamlit_setFrameHeight(height) {
            sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: height});
        }

        let canvas;
        let isInitialized = false;

        function calcDisplaySize(cWidth, cHeight) {
            const vw = Math.min(window.innerWidth || 390, document.documentElement.clientWidth || 390);
            const isMobile = vw <= 768;

            let displayWidth;

            if (isMobile) {
                displayWidth = 260;
                if (displayWidth > vw - 40) {
                    displayWidth = vw - 40;
                }
            } else {
                displayWidth = 340;
            }

            const displayHeight = Math.round(cHeight * (displayWidth / cWidth));

            return {
                displayWidth: displayWidth,
                displayHeight: displayHeight
            };
        }

        function initCanvas(args) {
            const cWidth = args.canvas_width;
            const cHeight = args.canvas_height;
            const size = calcDisplaySize(cWidth, cHeight);

            canvas = new fabric.Canvas('c', {
                width: cWidth,
                height: cHeight,
                preserveObjectStacking: true,
                selection: true
            });

            canvas.setDimensions(
                { width: size.displayWidth, height: size.displayHeight },
                { cssOnly: true }
            );

            if (args.bg_b64) {
                fabric.Image.fromURL(args.bg_b64, function(img) {
                    img.set({
                        scaleX: cWidth / img.width,
                        scaleY: cHeight / img.height,
                        originX: 'left',
                        originY: 'top',
                        selectable: false,
                        evented: false
                    });
                    canvas.setBackgroundImage(img, canvas.renderAll.bind(canvas));
                }, { crossOrigin: "anonymous" });
            } else {
                canvas.backgroundColor = '#ffffff';
            }

            args.items.forEach((item) => {
                fabric.Image.fromURL(item.b64, function(img) {
                    img.set({
                        left: item.x,
                        top: item.y,
                        scaleX: item.scale,
                        scaleY: item.scale,
                        angle: item.rotation,
                        originX: 'center',
                        originY: 'center',
                        id: item.id,
                        cornerColor: '#FF4B4B',
                        borderColor: '#FF4B4B',
                        transparentCorners: false,
                        cornerStyle: 'circle',
                        padding: 4
                    });
                    canvas.add(img);
                    canvas.renderAll();
                }, { crossOrigin: "anonymous" });
            });

            document.getElementById('sync-btn').onclick = function() {
                const layoutData = canvas.getObjects().map(obj => ({
                    id: obj.id,
                    x: obj.left,
                    y: obj.top,
                    scale: obj.scaleX,
                    rotation: obj.angle,
                    z: canvas.getObjects().indexOf(obj)
                }));
                Streamlit_setComponentValue(layoutData);
            };

            setTimeout(() => {
                const targetHeight = size.displayHeight + 150;
                Streamlit_setFrameHeight(targetHeight);
            }, 450);
        }

        window.addEventListener("message", function(event) {
            if (event.data.type === "streamlit:render") {
                if (!isInitialized) {
                    initCanvas(event.data.args);
                    isInitialized = true;
                }
            }
        });

        window.onload = function() {
            sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1});
        };
    </script>
</body>
</html>
"""


def get_fabric_component():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    component_dir = os.path.join(current_dir, "fabric_frontend_editor")

    if os.path.exists(component_dir):
        try:
            shutil.rmtree(component_dir)
        except Exception:
            pass

    os.makedirs(component_dir, exist_ok=True)

    html_path = os.path.join(component_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(FABRIC_HTML)

    return components.declare_component("fabric_canvas_editor", path=component_dir)


fabric_canvas = get_fabric_component()


# =========================
# 頁面
# =========================
st.title("Step 5｜排版 Editor")
st.page_link("Home.py", label="回到 Home", icon="🏠")

selected_bg = get_selected_background()
canvas_width = int(st.session_state.get("canvas_width", 1200))
canvas_height = int(st.session_state.get("canvas_height", 1800))
include_svg_frame = st.session_state.get("include_svg_frame", False)

bg_b64 = pil_to_base64(selected_bg) if selected_bg else None

default_positions = [
    (300, 300),
    (900, 300),
    (300, 900),
    (900, 900),
    (300, 1500),
    (900, 1500)
]

frontend_items = []
for i, item in enumerate(st.session_state.processed_items):
    pos_x = default_positions[i][0] * (canvas_width / 1200) if i < len(default_positions) else canvas_width / 2
    pos_y = default_positions[i][1] * (canvas_height / 1800) if i < len(default_positions) else canvas_height / 2

    frontend_items.append({
        "id": i,
        "b64": pil_to_base64(item["image"]),
        "x": int(pos_x),
        "y": int(pos_y),
        "scale": 0.8,
        "rotation": 0
    })

dynamic_key = f"editor_{canvas_width}_{canvas_height}_{len(frontend_items)}"

layout_data = fabric_canvas(
    canvas_width=canvas_width,
    canvas_height=canvas_height,
    bg_b64=bg_b64,
    items=frontend_items,
    key=dynamic_key,
    default=None
)

if layout_data is not None:
    final_sticker_items = []
    for obj in layout_data:
        idx = obj["id"]
        if idx < len(st.session_state.processed_items):
            final_sticker_items.append({
                "image": st.session_state.processed_items[idx]["image"],
                "x": obj["x"],
                "y": obj["y"],
                "scale": obj["scale"],
                "rotation": obj["rotation"],
                "z": obj["z"]
            })

    final_canvas_img = build_final_canvas(
        bg_image=selected_bg,
        sticker_items=final_sticker_items,
        canvas_width=canvas_width,
        canvas_height=canvas_height
    )

    final_png = pil_to_bytes(final_canvas_img, fmt="PNG")
    svg_cutline_bytes = create_svg_cutline(
        sticker_items=final_sticker_items,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        include_background_rect=include_svg_frame
    )

    st.markdown("### 完整成品預覽")
    show_ratio_card_preview(final_canvas_img, caption="完整成品預覽")

    col1, col2 = st.columns(2)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with col1:
        st.download_button(
            label="下載最終高畫質 PNG",
            data=final_png,
            file_name=f"photobooth_{timestamp}.png",
            mime="image/png",
            type="primary",
            use_container_width=True
        )

    with col2:
        st.download_button(
            label="下載 SVG 刀模",
            data=svg_cutline_bytes,
            file_name=f"cutline_{timestamp}.svg",
            mime="image/svg+xml",
            use_container_width=True
        )