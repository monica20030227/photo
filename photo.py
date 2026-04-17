import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageFilter, ImageOps
import numpy as np
import cv2
import io
import os
import math
import svgwrite
import base64
import shutil
from datetime import datetime

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="Joe's Snapshot",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DEFAULT_CANVAS_WIDTH = 1200
DEFAULT_CANVAS_HEIGHT = 1800
MAX_ITEMS = 6


# =========================
# 全域 CSS
# =========================
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.9rem;
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
# Session state 初始化
# =========================
def init_session():
    if "raw_items" not in st.session_state:
        st.session_state.raw_items = []
    if "processed_items" not in st.session_state:
        st.session_state.processed_items = []
    if "selected_bg_path" not in st.session_state:
        st.session_state.selected_bg_path = None
    if "camera_counter" not in st.session_state:
        st.session_state.camera_counter = 1

init_session()


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


def load_background_files(folder="backgrounds"):
    files = []
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                files.append(os.path.join(folder, f))
    return sorted(files)


def remove_background(image: Image.Image) -> Image.Image:
    try:
        from rembg import remove
    except Exception as e:
        raise RuntimeError(f"rembg 載入失敗，請確認已安裝 rembg。詳細錯誤：{e}")

    input_bytes = io.BytesIO()
    image.save(input_bytes, format="PNG")
    output_bytes = remove(input_bytes.getvalue())
    output_image = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    return output_image


def crop_to_content(rgba_image: Image.Image, padding: int = 20) -> Image.Image:
    arr = np.array(rgba_image)
    alpha = arr[:, :, 3]
    coords = np.argwhere(alpha > 0)
    if len(coords) == 0:
        return rgba_image

    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    x_min = max(0, x_min - padding)
    y_min = max(0, y_min - padding)
    x_max = min(rgba_image.width, x_max + padding)
    y_max = min(rgba_image.height, y_max + padding)

    return rgba_image.crop((x_min, y_min, x_max, y_max))


def add_transparent_padding(img: Image.Image, pad: int) -> Image.Image:
    w, h = img.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    canvas.alpha_composite(img, (pad, pad))
    return canvas


def add_white_border_fixed(
    rgba_image: Image.Image,
    border_size: int = 18,
    smooth_radius: int = 2,
    close_kernel_size: int = 5,
    extra_padding: int = 40
) -> Image.Image:
    rgba = rgba_image.convert("RGBA")
    safe_pad = max(border_size + extra_padding, 10)
    rgba = add_transparent_padding(rgba, safe_pad)

    arr = np.array(rgba)
    alpha = arr[:, :, 3]

    _, mask = cv2.threshold(alpha, 1, 255, cv2.THRESH_BINARY)

    if close_kernel_size > 1:
        close_kernel = np.ones((close_kernel_size, close_kernel_size), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)

    kernel_size = border_size * 2 + 1
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    dilated = cv2.dilate(mask, kernel, iterations=1)

    if smooth_radius > 0:
        pil_mask = Image.fromarray(dilated)
        pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=smooth_radius))
        dilated = np.array(pil_mask)

    border_rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
    border_rgba[:, :, 0] = 255
    border_rgba[:, :, 1] = 255
    border_rgba[:, :, 2] = 255
    border_rgba[:, :, 3] = dilated

    border_img = Image.fromarray(border_rgba, mode="RGBA")
    result = Image.alpha_composite(border_img, rgba)
    return result


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

    sorted_items = sorted(
        [item for item in sticker_items if item["visible"] and item["image"] is not None],
        key=lambda x: x["z"]
    )

    for item in sorted_items:
        transformed = transform_image(item["image"], scale=item["scale"], rotation=item["rotation"])
        paste_centered(canvas, transformed, item["x"], item["y"])

    return canvas


def make_uniform_preview(img: Image.Image, target_size=(260, 390), bg_color=(245, 245, 245, 255)) -> Image.Image:
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", target_size, bg_color)
    fitted = ImageOps.contain(img, target_size, Image.LANCZOS)
    x = (target_size[0] - fitted.width) // 2
    y = (target_size[1] - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
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

    visible_items = sorted(
        [item for item in sticker_items if item["visible"] and item["image"] is not None],
        key=lambda x: x["z"]
    )

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
# Fabric.js 前端
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
            <div class="tip">
                直接在這張固定比例卡片上拖曳、縮放、旋轉人物。
            </div>
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
                // 跟背景卡片相近的手機視覺尺寸
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
                displayHeight: displayHeight,
                isMobile: isMobile
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
    component_dir = os.path.join(current_dir, "fabric_frontend_v5")

    if os.path.exists(component_dir):
        try:
            shutil.rmtree(component_dir)
        except Exception:
            pass

    os.makedirs(component_dir, exist_ok=True)

    html_path = os.path.join(component_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(FABRIC_HTML)

    return components.declare_component("fabric_canvas_v5", path=component_dir)


fabric_canvas = get_fabric_component()


# =========================
# 標題
# =========================
st.title("Joe's Snapshot")
st.caption("手機與電腦都可使用的拍貼排版平台")


# =========================
# 側邊欄
# =========================
with st.sidebar:
    st.header("全域設定")

    canvas_width = st.number_input("成品寬度", min_value=600, max_value=3000, value=DEFAULT_CANVAS_WIDTH, step=100)
    canvas_height = st.number_input("成品高度", min_value=800, max_value=4000, value=DEFAULT_CANVAS_HEIGHT, step=100)

    add_border = st.checkbox("加白邊", value=True)
    border_size = st.slider("白邊寬度", 0, 60, 18)
    border_smooth = st.slider("白邊平滑", 0, 10, 2)
    border_close_kernel = st.slider("白邊補洞強度", 1, 15, 5, step=2)

    crop_after_cut = st.checkbox("去背後自動裁切", value=True)
    crop_padding = st.slider("裁切保留邊界", 0, 100, 20, step=5)

    include_svg_frame = st.checkbox("SVG 顯示畫布外框", value=False)

    st.divider()

    if st.button("清空全部素材"):
        st.session_state.raw_items = []
        st.session_state.processed_items = []
        st.rerun()


# =========================
# Step 1 背景選擇
# =========================
st.subheader("Step 1｜選擇背景")

bg_files = load_background_files("backgrounds")
bg_mode = st.radio("背景來源", ["使用內建背景", "上傳自訂背景"], horizontal=True)
selected_bg = None

if bg_mode == "使用內建背景":
    if len(bg_files) == 0:
        st.warning("找不到 backgrounds 資料夾中的背景圖，請先放入背景圖片。")
    else:
        if st.session_state.selected_bg_path is None:
            st.session_state.selected_bg_path = bg_files[0]

        cols = st.columns(2)
        for idx, path in enumerate(bg_files):
            with cols[idx % 2]:
                img = Image.open(path).convert("RGBA")
                uniform_preview = make_uniform_preview(img, target_size=(260, 390))
                st.image(uniform_preview, caption=os.path.basename(path), use_container_width=True)
                if st.button(f"選這張 {idx + 1}", key=f"pick_bg_{idx}", use_container_width=True):
                    st.session_state.selected_bg_path = path

        if st.session_state.selected_bg_path and os.path.exists(st.session_state.selected_bg_path):
            selected_bg = Image.open(st.session_state.selected_bg_path).convert("RGBA")
            st.success(f"目前背景：{os.path.basename(st.session_state.selected_bg_path)}")

else:
    uploaded_bg = st.file_uploader("上傳背景圖", type=["png", "jpg", "jpeg", "webp"], key="uploaded_bg")
    if uploaded_bg:
        selected_bg = Image.open(uploaded_bg).convert("RGBA")
        st.image(make_uniform_preview(selected_bg, target_size=(260, 390)), caption="自訂背景預覽", use_container_width=True)


# =========================
# Step 2 加入素材
# =========================
st.subheader("Step 2｜加入素材（上傳 / 直接拍照）")

col_input1, col_input2 = st.columns(2)

with col_input1:
    st.markdown("**上傳照片**")
    uploaded_files = st.file_uploader(
        "請選擇照片（可多張）",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True
    )

    if st.button("把上傳照片加入素材清單", use_container_width=True):
        if uploaded_files:
            remain = MAX_ITEMS - len(st.session_state.raw_items)
            for file in uploaded_files[:remain]:
                st.session_state.raw_items.append({
                    "name": file.name,
                    "image": Image.open(file).convert("RGBA")
                })
            st.rerun()

with col_input2:
    st.markdown("**直接拍照**")
    camera_file = st.camera_input("拍一張照片")

    if camera_file and st.button("把這張拍照加入素材清單", use_container_width=True):
        if len(st.session_state.raw_items) < MAX_ITEMS:
            st.session_state.raw_items.append({
                "name": f"camera_{st.session_state.camera_counter}.png",
                "image": Image.open(camera_file).convert("RGBA")
            })
            st.session_state.camera_counter += 1
            st.rerun()


# =========================
# Step 3 素材清單
# =========================
st.subheader("Step 3｜目前素材清單")

if len(st.session_state.raw_items) == 0:
    st.info("目前還沒有素材。")
else:
    cols = st.columns(2)
    for i, item in enumerate(st.session_state.raw_items):
        with cols[i % 2]:
            st.image(item["image"], caption=item["name"], use_container_width=True)
            if st.button(f"刪除素材 {i+1}", key=f"del_{i}", use_container_width=True):
                del st.session_state.raw_items[i]
                if i < len(st.session_state.processed_items):
                    del st.session_state.processed_items[i]
                st.rerun()


# =========================
# Step 4 去背
# =========================
st.subheader("Step 4｜自動去背")

if st.button("開始去背並生成貼紙", type="primary", use_container_width=True) and len(st.session_state.raw_items) > 0:
    processed = []
    progress, status = st.progress(0), st.empty()

    for i, item in enumerate(st.session_state.raw_items[:MAX_ITEMS]):
        status.write(f"處理第 {i+1} 張...")
        cut = remove_background(item["image"])

        if crop_after_cut:
            cut = crop_to_content(cut, padding=crop_padding)

        if add_border and border_size > 0:
            cut = add_white_border_fixed(cut, border_size, border_smooth, border_close_kernel)

        processed.append({"name": item["name"], "image": cut})
        progress.progress((i + 1) / len(st.session_state.raw_items[:MAX_ITEMS]))

    st.session_state.processed_items = processed
    status.success("去背完成，請往下排版。")
    st.rerun()


# =========================
# Step 5 排版
# =========================
if len(st.session_state.processed_items) > 0:
    st.markdown("---")
    st.subheader("Step 5｜互動排版與輸出")
    st.info("下方這張就是可操作畫布本身，比例已調整成和背景選擇卡片類似。")

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
        pos_x = default_positions[i][0] * (canvas_width / DEFAULT_CANVAS_WIDTH) if i < len(default_positions) else canvas_width / 2
        pos_y = default_positions[i][1] * (canvas_height / DEFAULT_CANVAS_HEIGHT) if i < len(default_positions) else canvas_height / 2

        frontend_items.append({
            "id": i,
            "b64": pil_to_base64(item["image"]),
            "x": int(pos_x),
            "y": int(pos_y),
            "scale": 0.8,
            "rotation": 0
        })

    current_bg = st.session_state.selected_bg_path if st.session_state.selected_bg_path else "custom"
    current_items_hash = "_".join([item["name"] for item in st.session_state.processed_items])
    dynamic_key = f"fabric_v5_{current_bg}_{current_items_hash}_{canvas_width}_{canvas_height}"

    layout_data = fabric_canvas(
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        bg_b64=bg_b64,
        items=frontend_items,
        key=dynamic_key,
        default=None
    )

    if layout_data is not None:
        st.success("排版已同步，以下是完整預覽與下載檔案。")

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
                    "z": obj["z"],
                    "visible": True
                })

        final_canvas_img = build_final_canvas(
            bg_image=selected_bg,
            sticker_items=final_sticker_items,
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height)
        )

        final_png = pil_to_bytes(final_canvas_img, fmt="PNG")

        svg_cutline_bytes = create_svg_cutline(
            sticker_items=final_sticker_items,
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
            include_background_rect=include_svg_frame
        )

        st.markdown("### 完整成品預覽")
        show_ratio_card_preview(final_canvas_img, caption="完整成品預覽")

        dl1, dl2 = st.columns(2)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        with dl1:
            st.download_button(
                label="下載最終高畫質 PNG",
                data=final_png,
                file_name=f"photobooth_{timestamp}.png",
                mime="image/png",
                type="primary",
                use_container_width=True
            )

        with dl2:
            st.download_button(
                label="下載 SVG 刀模",
                data=svg_cutline_bytes,
                file_name=f"cutline_{timestamp}.svg",
                mime="image/svg+xml",
                use_container_width=True
            )

        st.caption("下載的是原始高畫質尺寸；頁面上的畫布與預覽已調整為固定比例卡片。")
