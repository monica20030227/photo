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

if "processed_items" not in st.session_state or len(st.session_state.processed_items) == 0:
    st.warning("目前沒有可排版的素材，請先回 Home 頁完成去背。")
    st.page_link("Home.py", label="回到 Home", icon="🏠")
    st.stop()


# =========================
# Editor state
# =========================
def ensure_editor_state():
    if "editor_layout" not in st.session_state:
        st.session_state.editor_layout = {}
    if "editor_item_counter" not in st.session_state:
        st.session_state.editor_item_counter = 0


def next_editor_uid(prefix="item"):
    st.session_state.editor_item_counter += 1
    return f"{prefix}_{st.session_state.editor_item_counter}"


def ensure_item_uids():
    for item in st.session_state.processed_items:
        if "uid" not in item:
            item["uid"] = next_editor_uid("item")


def prune_editor_layout():
    valid_uids = {item["uid"] for item in st.session_state.processed_items if "uid" in item}
    st.session_state.editor_layout = {
        uid: layout for uid, layout in st.session_state.editor_layout.items()
        if uid in valid_uids
    }


ensure_editor_state()
ensure_item_uids()
prune_editor_layout()


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


def load_sticker_files(folder="stickers"):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    target_folder = os.path.join(root_dir, folder)

    files = []
    if os.path.exists(target_folder):
        for f in os.listdir(target_folder):
            if f.lower().endswith((".png", ".webp")):
                files.append(os.path.join(target_folder, f))
    return sorted(files)


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
    # Fabric 與 PIL 旋轉方向相反，所以這裡要加負號
    rotated = resized.rotate(-rotation, expand=True, resample=Image.BICUBIC)
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


def make_sticker_preview(img: Image.Image, target_size=(170, 170), bg_color=(245, 245, 245, 255)) -> Image.Image:
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", target_size, bg_color)
    fitted = ImageOps.contain(img, target_size, Image.LANCZOS)
    x = (target_size[0] - fitted.width) // 2
    y = (target_size[1] - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
    return canvas


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


def default_layout_for_new_item(index: int, canvas_width: int, canvas_height: int):
    default_positions = [
        (300, 300), (900, 300), (300, 900), (900, 900), (300, 1500), (900, 1500)
    ]

    if index < len(default_positions):
        pos_x = default_positions[index][0] * (canvas_width / 1200)
        pos_y = default_positions[index][1] * (canvas_height / 1800)
    else:
        pos_x = canvas_width / 2
        pos_y = canvas_height / 2

    return {
        "x": int(pos_x),
        "y": int(pos_y),
        "scale": 0.8,
        "rotation": 0,
        "z": index
    }


def add_item_to_editor(image: Image.Image, name: str, prefix: str, canvas_width: int, canvas_height: int, default_scale=None):
    uid = next_editor_uid(prefix)
    index = len(st.session_state.processed_items)

    layout = default_layout_for_new_item(index, canvas_width, canvas_height)
    if default_scale is not None:
        layout["scale"] = default_scale

    st.session_state.processed_items.append({
        "uid": uid,
        "name": name,
        "image": image
    })
    st.session_state.editor_layout[uid] = layout


# SVG 工具函式
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

    scaled_w, scaled_h = original_width * scale, original_height * scale
    cx_local, cy_local = scaled_w / 2.0, scaled_h / 2.0

    # 與 transform_image 同方向，這裡也要相反號
    theta = math.radians(-rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    corners = [(0, 0), (scaled_w, 0), (scaled_w, scaled_h), (0, scaled_h)]
    rotated_corners = []
    for x, y in corners:
        dx, dy = x - cx_local, y - cy_local
        rx, ry = dx * cos_t - dy * sin_t, dx * sin_t + dy * cos_t
        rotated_corners.append((rx, ry))

    min_rx, min_ry = min(p[0] for p in rotated_corners), min(p[1] for p in rotated_corners)
    max_rx, max_ry = max(p[0] for p in rotated_corners), max(p[1] for p in rotated_corners)
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
# 主程式邏輯
# =========================
st.title("Step 5｜排版 Editor")
st.page_link("Home.py", label="回到 Home", icon="🏠")

selected_bg = get_selected_background()
canvas_width = int(st.session_state.get("canvas_width", 1200))
canvas_height = int(st.session_state.get("canvas_height", 1800))
include_svg_frame = st.session_state.get("include_svg_frame", False)
bg_b64 = pil_to_base64(selected_bg) if selected_bg else None

# --- 裝飾貼圖選擇區 ---
st.markdown("### ✨ 裝飾貼圖庫")
tab1, tab2 = st.tabs(["管理者預設貼圖", "上傳自訂貼圖"])

with tab1:
    sticker_paths = load_sticker_files("stickers")
    if not sticker_paths:
        st.info("目前 stickers 資料夾中沒有預設貼圖。")
    else:
        cols = st.columns(4)
        for idx, path in enumerate(sticker_paths):
            with cols[idx % 4]:
                s_img = Image.open(path).convert("RGBA")
                sticker_with_border = add_white_border_fixed(
                    s_img,
                    border_size=int(st.session_state.get("border_size", 18)),
                    smooth_radius=int(st.session_state.get("border_smooth", 2)),
                    close_kernel_size=int(st.session_state.get("border_close_kernel", 5))
                )

                st.image(make_sticker_preview(sticker_with_border), use_container_width=True)

                if st.button(f"加入畫布", key=f"add_default_s_{idx}", use_container_width=True):
                    add_item_to_editor(
                        image=sticker_with_border,
                        name=f"sticker_{os.path.basename(path)}",
                        prefix="sticker",
                        canvas_width=canvas_width,
                        canvas_height=canvas_height,
                        default_scale=0.45
                    )
                    st.toast(f"已加入貼圖：{os.path.basename(path)}")
                    st.rerun()

with tab2:
    uploaded_stickers = st.file_uploader(
        "上傳去背貼圖 (PNG/WebP)",
        type=["png", "webp"],
        accept_multiple_files=True,
        key="editor_sticker_upload"
    )

    if st.button("將上傳貼圖加入畫布", use_container_width=True):
        if uploaded_stickers:
            for file in uploaded_stickers:
                s_img = Image.open(file).convert("RGBA")
                sticker_with_border = add_white_border_fixed(
                    s_img,
                    border_size=int(st.session_state.get("border_size", 18)),
                    smooth_radius=int(st.session_state.get("border_smooth", 2)),
                    close_kernel_size=int(st.session_state.get("border_close_kernel", 5))
                )
                add_item_to_editor(
                    image=sticker_with_border,
                    name=f"custom_{file.name}",
                    prefix="custom",
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    default_scale=0.45
                )
            st.success("自訂貼圖已加入！")
            st.rerun()

st.divider()

# --- 畫布排版邏輯 ---
frontend_items = []
for i, item in enumerate(st.session_state.processed_items):
    uid = item["uid"]
    saved_layout = st.session_state.editor_layout.get(uid)

    if saved_layout is None:
        saved_layout = default_layout_for_new_item(i, canvas_width, canvas_height)
        st.session_state.editor_layout[uid] = saved_layout

    frontend_items.append({
        "id": uid,
        "b64": pil_to_base64(item["image"]),
        "x": int(saved_layout["x"]),
        "y": int(saved_layout["y"]),
        "scale": float(saved_layout.get("scale", 0.8)),
        "rotation": float(saved_layout.get("rotation", 0)),
        "z": int(saved_layout.get("z", i))
    })

# 只跟畫布尺寸綁定，不再因素材數量改變而重置整個畫布
dynamic_key = f"editor_v4_{canvas_width}_{canvas_height}"

layout_data = fabric_canvas(
    canvas_width=canvas_width,
    canvas_height=canvas_height,
    bg_b64=bg_b64,
    items=frontend_items,
    key=dynamic_key,
    default=None
)

if layout_data is not None:
    remaining_uids = {obj["id"] for obj in layout_data}

    # 前端刪掉的物件，後端也同步刪除
    st.session_state.processed_items = [
        item for item in st.session_state.processed_items
        if item["uid"] in remaining_uids
    ]

    new_layout = {}
    image_by_uid = {
        item["uid"]: item["image"]
        for item in st.session_state.processed_items
    }

    final_sticker_items = []
    for obj in layout_data:
        uid = obj["id"]
        new_layout[uid] = {
            "x": obj["x"],
            "y": obj["y"],
            "scale": obj["scale"],
            "rotation": obj["rotation"],
            "z": obj["z"]
        }

        if uid in image_by_uid:
            final_sticker_items.append({
                "image": image_by_uid[uid],
                "x": obj["x"],
                "y": obj["y"],
                "scale": obj["scale"],
                "rotation": obj["rotation"],
                "z": obj["z"]
            })

    st.session_state.editor_layout = new_layout

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

    st.markdown("### 📸 最終成品預覽")
    show_ratio_card_preview(final_canvas_img, caption="完整成品預覽")

    col1, col2 = st.columns(2)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with col1:
        st.download_button(
            label="📥 下載最終高畫質 PNG",
            data=final_png,
            file_name=f"photobooth_{timestamp}.png",
            mime="image/png",
            type="primary",
            use_container_width=True
        )

    with col2:
        st.download_button(
            label="✂️ 下載 SVG 刀模",
            data=svg_cutline_bytes,
            file_name=f"cutline_{timestamp}.svg",
            mime="image/svg+xml",
            use_container_width=True
        )
