import streamlit as st
from PIL import Image, ImageDraw, ImageOps, ImageChops
import numpy as np
import cv2
import io
import os
import math
import svgwrite
import base64
from datetime import datetime

from fabric_component import fabric_canvas

st.set_page_config(page_title="Editor - Joe's Snapshot", layout="wide", initial_sidebar_state="collapsed")

# 🌟 核心修正：接收下載完成的訊號，自動跳轉回 Home (由 Home 負責清空狀態)
if st.session_state.get("trigger_go_home"):
    st.session_state.trigger_go_home = False
    st.switch_page("Home.py")

# 點擊下載時觸發這個 Callback
def on_download_clicked():
    st.session_state.trigger_go_home = True

st.markdown("""
    <style>
    .block-container { padding-top: 0.8rem; padding-bottom: 2rem; padding-left: 0.9rem; padding-right: 0.9rem; max-width: 1200px; }
    @media (max-width: 768px) { .block-container { padding-top: 0.5rem; padding-left: 0.65rem; padding-right: 0.65rem; } }
    div[data-testid="stImage"] img { border-radius: 12px; }
    </style>
""", unsafe_allow_html=True)

# --- 狀態初始化 (持久化座標字典) ---
if "canvas_states" not in st.session_state:
    st.session_state.canvas_states = {}
if "processed_items" not in st.session_state:
    st.session_state.processed_items = []
if "pb_slots" not in st.session_state:
    st.session_state.pb_slots = [None, None, None, None]

# 偵測當前模式
editor_mode = st.session_state.get("editor_mode", "sticker")
has_pb_images = (editor_mode == "photobooth") and any(img is not None for img in st.session_state.pb_slots)

if not has_pb_images and len(st.session_state.processed_items) == 0:
    st.warning("目前沒有照片或貼紙，請先回到 Home 頁選擇功能。")
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
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"

def load_sticker_files(folder="stickers"):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_folder = os.path.join(root_dir, folder)
    files = []
    if os.path.exists(target_folder):
        for f in os.listdir(target_folder):
            if f.lower().endswith((".png", ".webp")):
                files.append(os.path.join(target_folder, f))
    return sorted(files)

# 🌟 新增：讀取管理員內建的外框圖片
def load_frame_files(folder="frames"):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_folder = os.path.join(root_dir, folder)
    files = []
    if os.path.exists(target_folder):
        for f in os.listdir(target_folder):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                files.append(os.path.join(target_folder, f))
    return sorted(files)

def get_selected_background():
    if st.session_state.get("uploaded_bg_image") is not None:
        return st.session_state.uploaded_bg_image.convert("RGBA")
    if st.session_state.get("selected_bg_path") is not None and os.path.exists(st.session_state.selected_bg_path):
        return Image.open(st.session_state.selected_bg_path).convert("RGBA")
    return None

def transform_image(img: Image.Image, scale: float = 1.0, rotation: float = 0.0) -> Image.Image:
    new_w, new_h = max(1, int(img.width * scale)), max(1, int(img.height * scale))
    return img.resize((new_w, new_h), Image.LANCZOS).rotate(-rotation, expand=True, resample=Image.BICUBIC)

def paste_centered(base: Image.Image, overlay: Image.Image, center_x: int, center_y: int):
    base.alpha_composite(overlay, (int(center_x - overlay.width / 2), int(center_y - overlay.height / 2)))

def find_logo():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in [os.path.join(root_dir, p) for p in ["assets/logo.png", "assets/logo.jpg", "logo.png", "logo.jpg"]]:
        if os.path.exists(path): return path
    return None

def build_frame_overlay(canvas_w, canvas_h, outer_margin, gap, photo_radius, frame_color, inner_padding, bottom_space, custom_img, custom_layer):
    overlay = custom_img.convert("RGBA").resize((canvas_w, canvas_h), Image.LANCZOS) if custom_img and custom_layer == "背景" else Image.new("RGBA", (canvas_w, canvas_h), frame_color)
    if custom_img and custom_layer == "前景框": return overlay
    
    draw = ImageDraw.Draw(overlay, "RGBA")
    hole_mask = Image.new("L", (canvas_w, canvas_h), 255)
    hole_draw = ImageDraw.Draw(hole_mask)
    
    photo_area_h = canvas_h - bottom_space
    cell_w, cell_h = canvas_w - outer_margin * 2, int((photo_area_h - outer_margin * 2 - gap * 3) / 4)
    
    for idx in range(4):
        top_y = outer_margin + idx * (cell_h + gap)
        backing_color = (255, 255, 255, 235) if custom_img else ((245,245,250,255) if frame_color == (255,255,255,255) else (255,255,255,255))
        draw.rounded_rectangle((outer_margin, top_y, outer_margin + cell_w, top_y + cell_h), radius=photo_radius + 8, fill=backing_color)
        px, py = outer_margin + inner_padding, top_y + inner_padding
        pw, ph = cell_w - inner_padding * 2, cell_h - inner_padding * 2
        hole_draw.rounded_rectangle((px, py, px+pw, py+ph), radius=photo_radius, fill=0)
        
    logo_path = find_logo()
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((int(canvas_w * 0.45), int(bottom_space * 0.5)), Image.LANCZOS)
        overlay.alpha_composite(logo, ((canvas_w - logo.width) // 2, photo_area_h + (bottom_space - logo.height) // 2 - 20))
        
    overlay.putalpha(ImageChops.darker(overlay.split()[3], hole_mask))
    return overlay

def get_largest_contour_from_alpha(rgba_image: Image.Image, threshold: int = 1, approx_epsilon_ratio: float = 0.002):
    arr = np.array(rgba_image.convert("RGBA"))
    _, mask = cv2.threshold(arr[:, :, 3], threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return cv2.approxPolyDP(max(contours, key=cv2.contourArea), approx_epsilon_ratio * cv2.arcLength(max(contours, key=cv2.contourArea), True), True) if contours else None

def transform_points_for_canvas(points, original_width, original_height, scale, rotation_deg, center_x, center_y):
    if not points: return []
    scaled_w, scaled_h = original_width * scale, original_height * scale
    cx_local, cy_local = scaled_w / 2.0, scaled_h / 2.0
    cos_t, sin_t = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
    rotated_corners = [((x - cx_local) * cos_t - (y - cy_local) * sin_t, (x - cx_local) * sin_t + (y - cy_local) * cos_t) for x, y in [(0, 0), (scaled_w, 0), (scaled_w, scaled_h), (0, scaled_h)]]
    min_rx, min_ry = min(p[0] for p in rotated_corners), min(p[1] for p in rotated_corners)
    rotated_w, rotated_h = max(p[0] for p in rotated_corners) - min_rx, max(p[1] for p in rotated_corners) - min_ry
    final_points = []
    for x, y in points:
        rx, ry = (x * scale - cx_local) * cos_t - (y * scale - cy_local) * sin_t, (x * scale - cx_local) * sin_t + (y * scale - cy_local) * cos_t
        final_points.append((rx - min_rx + (center_x - rotated_w / 2.0), ry - min_ry + (center_y - rotated_h / 2.0)))
    return final_points

def create_svg_cutline(sticker_items, canvas_width, canvas_height, include_background_rect=False):
    dwg = svgwrite.Drawing(size=(f"{canvas_width}px", f"{canvas_height}px"), viewBox=f"0 0 {canvas_width} {canvas_height}")
    if include_background_rect: dwg.add(dwg.rect(insert=(0, 0), size=(canvas_width, canvas_height), fill="none", stroke="#dddddd", stroke_width=1))
    for item in sticker_items:
        contour = get_largest_contour_from_alpha(item["image"])
        if contour is None: continue
        pts = transform_points_for_canvas([(float(x), float(y)) for x, y in contour.reshape(-1, 2)], item["image"].width, item["image"].height, item["scale"], item["rotation"], item["x"], item["y"])
        if pts: dwg.add(dwg.path(d=f"M {pts[0][0]:.2f},{pts[0][1]:.2f} " + "".join([f"L {x:.2f},{y:.2f} " for x, y in pts[1:]]) + "Z", fill="none", stroke="#000000", stroke_width=1))
    return dwg.tostring().encode("utf-8")

# =========================
# 頁面主邏輯
# =========================
st.title("Step 5｜排版與裝飾 Editor")
st.page_link("Home.py", label="回到 Home", icon="🏠")

FRAME_COLORS = {"白色": (255,255,255,255), "粉色": (255,223,235,255), "薰衣草紫": (232,226,255,255), "天空藍": (222,239,255,255), "薄荷綠": (224,248,239,255), "奶油黃": (255,245,214,255), "黑色": (30,30,35,255)}

# --- 自動模式設定 ---
with st.sidebar:
    if editor_mode == "photobooth":
        st.header("📸 四格外框設定")
        # 🌟 升級版：支援三種模式
        frame_mode = st.radio("外框來源", ["內建純色", "管理員圖片", "自訂上傳"], horizontal=True)
        custom_bg_img, custom_layer_type = None, "背景"
        
        if frame_mode == "內建純色": 
            frame_name = st.selectbox("選擇純色框", list(FRAME_COLORS.keys()), index=1)
            
        elif frame_mode == "管理員圖片":
            frame_name = "管理員圖片"
            frame_files = load_frame_files("frames")
            if frame_files:
                selected_file = st.selectbox("選擇內建外框", [os.path.basename(f) for f in frame_files])
                selected_path = next(f for f in frame_files if os.path.basename(f) == selected_file)
                custom_bg_img = Image.open(selected_path)
                custom_layer_type = st.radio("圖層位置", ["背景", "前景框"])
            else:
                st.warning("⚠️ 請在專案根目錄建立 `frames` 資料夾並放入圖片。")
                
        else:
            frame_name = "自訂"
            uploaded_frame = st.file_uploader("上傳外框 (建議 900x2800)", type=["png", "jpg", "jpeg", "webp"])
            if uploaded_frame: custom_bg_img = Image.open(uploaded_frame)
            custom_layer_type = st.radio("圖層位置", ["背景", "前景框"])
        
        canvas_width = st.number_input("成品寬度", 600, 1800, 900, 50)
        canvas_height = st.number_input("成品高度", 1600, 4200, 2800, 100)
        bottom_space = st.slider("底部留白高度", 100, 800, 350)
        outer_margin, gap = st.slider("外圍邊界", 10, 120, 56), st.slider("照片間距", 0, 80, 28)
        photo_radius, inner_padding = st.slider("照片圓角", 0, 80, 28), st.slider("白邊厚度", 0, 40, 18)
    else:
        st.header("✨ 貼紙畫布設定")
        canvas_width = int(st.session_state.get("canvas_width", 1200))
        canvas_height = int(st.session_state.get("canvas_height", 1800))
        st.info("背景設定已由去背流程帶入。")

ctrl_col, canvas_col = st.columns([1.2, 1.8])

with ctrl_col:
    st.markdown("### ✨ 裝飾貼圖庫")
    sub_tab1, sub_tab2 = st.tabs(["預設貼圖", "自訂貼圖"])
    with sub_tab1:
        sticker_paths = load_sticker_files("stickers")
        if sticker_paths:
            cols = st.columns(3)
            for idx, path in enumerate(sticker_paths):
                with cols[idx % 3]:
                    st.image(path, use_container_width=True)
                    if st.button(f"加入", key=f"add_s_{idx}", use_container_width=True):
                        st.session_state.processed_items.append({"name": f"sticker_{os.path.basename(path)}", "image": Image.open(path).convert("RGBA")})
                        st.rerun()
        else: st.info("無預設貼圖")
    with sub_tab2:
        uploaded_stickers = st.file_uploader("上傳去背貼圖", type=["png", "webp"], accept_multiple_files=True)
        if st.button("將上傳貼圖加入", use_container_width=True) and uploaded_stickers:
            for file in uploaded_stickers:
                st.session_state.processed_items.append({"name": f"custom_{file.name}", "image": Image.open(file).convert("RGBA")})
            st.rerun()

# --- 物件準備與持久化邏輯 ---
frontend_items, source_images_dict, hole_bounds_dict = [], {}, {}

if has_pb_images:
    photo_area_h = canvas_height - bottom_space
    cell_w, cell_h = canvas_width - outer_margin * 2, int((photo_area_h - outer_margin * 2 - gap * 3) / 4)
    for idx in range(4):
        img = st.session_state.pb_slots[idx]
        if img:
            px, py = outer_margin + inner_padding, outer_margin + idx * (cell_h + gap) + inner_padding
            pw, ph = cell_w - inner_padding * 2, cell_h - inner_padding * 2
            photo_id = f"photo_{idx}"
            source_images_dict[photo_id], hole_bounds_dict[photo_id] = img, (int(px), int(py), int(pw), int(ph))
            
            state = st.session_state.canvas_states.get(photo_id, {})
            frontend_items.append({
                "id": photo_id, "b64": pil_to_base64(img), 
                "x": state.get("x", int(px + pw/2)), "y": state.get("y", int(py + ph/2)), 
                "scale": state.get("scale", max(pw / img.width, ph / img.height)), 
                "rotation": state.get("rotation", 0), "item_type": "photo",
                "hole_x": int(px), "hole_y": int(py), "hole_w": int(pw), "hole_h": int(ph)
            })

    frame_overlay = build_frame_overlay(canvas_width, canvas_height, outer_margin, gap, photo_radius, FRAME_COLORS.get(frame_name, (255,255,255,255)), inner_padding, bottom_space, custom_bg_img, custom_layer_type)
    source_images_dict["frame_overlay"] = frame_overlay
    frontend_items.append({"id": "frame_overlay", "b64": pil_to_base64(frame_overlay), "x": canvas_width // 2, "y": canvas_height // 2, "scale": 1.0, "rotation": 0, "item_type": "frame"})

else:
    selected_bg = get_selected_background()
    if selected_bg:
        bg_resized = selected_bg.convert("RGBA").resize((canvas_width, canvas_height), Image.LANCZOS)
        source_images_dict["main_background"] = bg_resized
        frontend_items.append({
            "id": "main_background", "b64": pil_to_base64(bg_resized), 
            "x": canvas_width // 2, "y": canvas_height // 2, 
            "scale": 1.0, "rotation": 0, "item_type": "frame" 
        })

for i, item in enumerate(st.session_state.processed_items):
    item_id = f"sticker_{i}"
    source_images_dict[item_id] = item["image"]
    state = st.session_state.canvas_states.get(item_id, {})
    
    default_pos = [(300, 300), (900, 300), (300, 900), (900, 900), (300, 1500), (900, 1500)]
    pos_x = state.get("x", default_pos[i][0] * (canvas_width / 1200) if i < 6 else canvas_width / 2)
    pos_y = state.get("y", default_pos[i][1] * (canvas_height / 1800) if i < 6 else canvas_height / 2)

    frontend_items.append({
        "id": item_id, "b64": pil_to_base64(item["image"]), "x": pos_x, "y": pos_y, 
        "scale": state.get("scale", 0.8), "rotation": state.get("rotation", 0), "item_type": "sticker"
    })

# --- 渲染畫布 ---
with canvas_col:
    layout_data = fabric_canvas(canvas_width=canvas_width, canvas_height=canvas_height, items=frontend_items, key=f"editor_final_v13_{canvas_width}_{canvas_height}", default=None)

    if layout_data is not None:
        for obj in layout_data:
            st.session_state.canvas_states[obj["id"]] = obj

        final_canvas_img = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
        sticker_items_for_svg = []
        
        for obj in sorted(layout_data, key=lambda x: x["z"]):
            img = source_images_dict.get(obj["id"])
            if img:
                transformed = transform_image(img, scale=obj["scale"], rotation=obj["rotation"])
                
                if obj["id"] in hole_bounds_dict:
                    hx, hy, hw, hh = hole_bounds_dict[obj["id"]]
                    temp = Image.new("RGBA", (canvas_width, canvas_height), (0,0,0,0))
                    paste_centered(temp, transformed, obj["x"], obj["y"])
                    final_canvas_img.alpha_composite(temp.crop((hx, hy, hx+hw, hy+hh)), (hx, hy))
                else:
                    paste_centered(final_canvas_img, transformed, obj["x"], obj["y"])
                    
                if obj["id"].startswith("sticker_"):
                    sticker_items_for_svg.append({
                        "image": img, "x": obj["x"], "y": obj["y"], "scale": obj["scale"], "rotation": obj["rotation"], "z": obj["z"]
                    })
        
        st.markdown("### 📸 下載區域")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 儲存並回到首頁 (下載 PNG)", data=pil_to_bytes(final_canvas_img), file_name=f"joe_shot_{timestamp}.png", mime="image/png", type="primary", use_container_width=True, on_click=on_download_clicked)
        with col2:
            if not has_pb_images and sticker_items_for_svg:
                svg_bytes = create_svg_cutline(sticker_items_for_svg, canvas_width, canvas_height, st.session_state.get("include_svg_frame", False))
                st.download_button("✂️ 儲存並回到首頁 (下載 SVG)", data=svg_bytes, file_name=f"cutline_{timestamp}.svg", mime="image/svg+xml", use_container_width=True, on_click=on_download_clicked)
            else:
                st.button("🏠 完成並重置回首頁", use_container_width=True, on_click=on_download_clicked)