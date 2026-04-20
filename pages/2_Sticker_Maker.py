import streamlit as st
from PIL import Image, ImageFilter, ImageOps
import numpy as np
import cv2
import io
import os
import base64

DEFAULT_CANVAS_WIDTH = 1200
DEFAULT_CANVAS_HEIGHT = 1800
MAX_ITEMS = 6

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
    if "uploaded_bg_image" not in st.session_state:
        st.session_state.uploaded_bg_image = None
    if "camera_counter" not in st.session_state:
        st.session_state.camera_counter = 1
    if "editor_ready" not in st.session_state:
        st.session_state.editor_ready = False
    if "canvas_width" not in st.session_state:
        st.session_state.canvas_width = DEFAULT_CANVAS_WIDTH
    if "canvas_height" not in st.session_state:
        st.session_state.canvas_height = DEFAULT_CANVAS_HEIGHT
    if "add_border" not in st.session_state:
        st.session_state.add_border = True
    if "border_size" not in st.session_state:
        st.session_state.border_size = 18
    if "border_smooth" not in st.session_state:
        st.session_state.border_smooth = 2
    if "border_close_kernel" not in st.session_state:
        st.session_state.border_close_kernel = 5
    if "crop_after_cut" not in st.session_state:
        st.session_state.crop_after_cut = True
    if "crop_padding" not in st.session_state:
        st.session_state.crop_padding = 20
    if "include_svg_frame" not in st.session_state:
        st.session_state.include_svg_frame = False

init_session()

# =========================
# Logo 載入
# =========================
def find_logo():
    possible_paths = [
        "assets/logo.png",
        "assets/logo.jpg",
        "assets/logo.jpeg",
        "logo.png",
        "logo.jpg",
        "logo.jpeg",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

logo_path = find_logo()

# =========================
# CSS
# =========================
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #fffafc 0%, #f6f7ff 100%);
    }

    header, [data-testid="stHeader"], [data-testid="stToolbar"] {
        background: transparent !important;
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    .joe-header {
        background: linear-gradient(135deg, #ffdce8 0%, #e7e8ff 100%);
        border: 1px solid rgba(255,255,255,0.7);
        border-radius: 24px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
    }

    .joe-header-row {
        display: flex;
        align-items: center;
        gap: 14px;
    }

    .joe-logo-box {
        width: 64px;
        height: 64px;
        min-width: 64px;
        border-radius: 18px;
        background: rgba(255,255,255,0.78);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    .joe-logo-box img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        padding: 6px;
    }

    .joe-logo-fallback {
        font-size: 30px;
    }

    .joe-title {
        margin: 0;
        color: #2b2b3a;
        font-size: 1.9rem;
        font-weight: 800;
        line-height: 1.1;
    }

    .joe-subtitle {
        margin-top: 0.25rem;
        color: #5b6474;
        font-size: 0.95rem;
        font-weight: 500;
    }

    .joe-badge {
        display: inline-block;
        width: fit-content;
        background: rgba(255,255,255,0.75);
        color: #6d4aff;
        border-radius: 999px;
        padding: 0.2rem 0.65rem;
        font-size: 0.8rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    .section-card {
        background: rgba(255,255,255,0.78);
        border: 1px solid rgba(255,255,255,0.95);
        border-radius: 20px;
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 22px rgba(0,0,0,0.04);
    }

    div.stButton > button {
        border-radius: 14px;
        font-weight: 700;
    }

    div[data-testid="stFileUploader"] section {
        border-radius: 14px;
    }

    div[data-testid="stImage"] img {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# 工具函式
# =========================
def load_background_files(folder="backgrounds"):
    files = []
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                files.append(os.path.join(folder, f))
    return sorted(files)

def make_uniform_preview(img: Image.Image, target_size=(260, 390), bg_color=(245, 245, 245, 255)) -> Image.Image:
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", target_size, bg_color)
    fitted = ImageOps.contain(img, target_size, Image.LANCZOS)
    x = (target_size[0] - fitted.width) // 2
    y = (target_size[1] - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))
    return canvas

def remove_background(image: Image.Image) -> Image.Image:
    try:
        from rembg import remove
    except Exception as e:
        raise RuntimeError(f"rembg 載入失敗：{e}")

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

def rotate_raw_item(index: int, direction: str):
    if index < 0 or index >= len(st.session_state.raw_items):
        return

    img = st.session_state.raw_items[index]["image"].convert("RGBA")
    if direction == "left":
        rotated = img.rotate(90, expand=True)
    elif direction == "right":
        rotated = img.rotate(-90, expand=True)
    else:
        return

    st.session_state.raw_items[index]["image"] = rotated

def clear_all_sticker_data():
    st.session_state.raw_items = []
    st.session_state.processed_items = []
    st.session_state.editor_ready = False

# =========================
# Header
# =========================
if logo_path:
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="logo">'
else:
    logo_html = '<div class="joe-logo-fallback">✂️</div>'

st.markdown(
    f"""
    <div class="joe-header">
        <div class="joe-header-row">
            <div class="joe-logo-box">
                {logo_html}
            </div>
            <div>
                <div class="joe-badge">Sticker Maker</div>
                <div class="joe-title">去背貼紙製作</div>
                <div class="joe-subtitle">選背景、加入素材、去背處理，最後進入 Editor 排版。</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

top_col1, top_col2 = st.columns([1, 1])
with top_col1:
    st.page_link("Home.py", label="回到首頁", icon="🏠")
with top_col2:
    st.page_link("pages/3_Editor.py", label="直接前往 Editor", icon="✨")

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("貼紙全域設定")

    st.session_state.canvas_width = st.number_input(
        "成品寬度", min_value=600, max_value=3000,
        value=int(st.session_state.canvas_width), step=100
    )
    st.session_state.canvas_height = st.number_input(
        "成品高度", min_value=800, max_value=4000,
        value=int(st.session_state.canvas_height), step=100
    )

    st.session_state.add_border = st.checkbox("加白邊", value=st.session_state.add_border)
    st.session_state.border_size = st.slider("白邊寬度", 0, 60, int(st.session_state.border_size))
    st.session_state.border_smooth = st.slider("白邊平滑", 0, 10, int(st.session_state.border_smooth))
    st.session_state.border_close_kernel = st.slider("白邊補洞強度", 1, 15, int(st.session_state.border_close_kernel), step=2)

    st.session_state.crop_after_cut = st.checkbox("去背後自動裁切", value=st.session_state.crop_after_cut)
    st.session_state.crop_padding = st.slider("裁切保留邊界", 0, 100, int(st.session_state.crop_padding), step=5)

    st.session_state.include_svg_frame = st.checkbox(
        "SVG 刀模含背景外框",
        value=st.session_state.include_svg_frame
    )

    st.divider()

    if st.button("清空全部素材", use_container_width=True):
        clear_all_sticker_data()
        st.rerun()

# =========================
# Step 1 背景選擇
# =========================
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("Step 1｜選擇背景")

bg_files = load_background_files("backgrounds")
bg_mode = st.radio("背景來源", ["使用內建背景", "上傳自訂背景"], horizontal=True)

if bg_mode == "使用內建背景":
    st.session_state.uploaded_bg_image = None

    if len(bg_files) == 0:
        st.warning("找不到 backgrounds 資料夾中的背景圖。")
    else:
        if st.session_state.selected_bg_path is None:
            st.session_state.selected_bg_path = bg_files[0]

        cols = st.columns(2)
        for idx, path in enumerate(bg_files):
            with cols[idx % 2]:
                img = Image.open(path).convert("RGBA")
                st.image(
                    make_uniform_preview(img),
                    caption=os.path.basename(path),
                    use_container_width=True
                )
                if st.button(f"選這張 {idx+1}", key=f"pick_bg_{idx}", use_container_width=True):
                    st.session_state.selected_bg_path = path
                    st.rerun()

        if st.session_state.selected_bg_path:
            st.success(f"目前背景：{os.path.basename(st.session_state.selected_bg_path)}")

else:
    uploaded_bg = st.file_uploader(
        "上傳背景圖",
        type=["png", "jpg", "jpeg", "webp"],
        key="uploaded_bg_home"
    )
    if uploaded_bg is not None:
        st.session_state.uploaded_bg_image = Image.open(uploaded_bg).convert("RGBA")
        st.session_state.selected_bg_path = None
        st.image(
            make_uniform_preview(st.session_state.uploaded_bg_image),
            caption="自訂背景預覽",
            use_container_width=True
        )

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Step 2 加入素材
# =========================
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("Step 2｜加入素材（上傳 / 直接拍照）")

col_input1, col_input2 = st.columns(2)

with col_input1:
    st.markdown("**上傳照片**")
    uploaded_files = st.file_uploader(
        "請選擇照片（可多張）",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="upload_people"
    )

    if st.button("把上傳照片加入素材清單", use_container_width=True):
        if uploaded_files:
            existing_names = {item["name"] for item in st.session_state.raw_items}
            remain = MAX_ITEMS - len(st.session_state.raw_items)

            added_count = 0
            skipped_count = 0

            for file in uploaded_files:
                if added_count >= remain:
                    break

                if file.name in existing_names:
                    skipped_count += 1
                    continue

                st.session_state.raw_items.append({
                    "name": file.name,
                    "image": Image.open(file).convert("RGBA")
                })
                existing_names.add(file.name)
                added_count += 1

            if added_count > 0:
                st.success(f"已加入 {added_count} 張照片")
            if skipped_count > 0:
                st.info(f"略過 {skipped_count} 張重複照片")
            if added_count == 0 and skipped_count == 0:
                st.warning("沒有可加入的照片。")

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
        else:
            st.warning(f"最多只能加入 {MAX_ITEMS} 張素材。")

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Step 3 素材清單
# =========================
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("Step 3｜目前素材清單")

if len(st.session_state.raw_items) == 0:
    st.info("目前還沒有素材。")
else:
    cols = st.columns(2)
    for i, item in enumerate(st.session_state.raw_items):
        with cols[i % 2]:
            st.image(item["image"], caption=item["name"], use_container_width=True)

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button(f"↺ 左轉 90°", key=f"rotate_left_{i}", use_container_width=True):
                    rotate_raw_item(i, "left")
                    st.rerun()
            with btn_col2:
                if st.button(f"↻ 右轉 90°", key=f"rotate_right_{i}", use_container_width=True):
                    rotate_raw_item(i, "right")
                    st.rerun()

            if st.button(f"刪除素材 {i+1}", key=f"del_{i}", use_container_width=True):
                del st.session_state.raw_items[i]
                if i < len(st.session_state.processed_items):
                    del st.session_state.processed_items[i]
                st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Step 4 去背
# =========================
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("Step 4｜自動去背")

if st.button("開始去背並準備排版", type="primary", use_container_width=True):
    if len(st.session_state.raw_items) == 0:
        st.warning("請先加入至少一張素材。")
    else:
        processed = []
        progress = st.progress(0)
        status = st.empty()

        try:
            for i, item in enumerate(st.session_state.raw_items[:MAX_ITEMS]):
                status.write(f"處理第 {i+1} 張...")

                cut = remove_background(item["image"])

                if st.session_state.crop_after_cut:
                    cut = crop_to_content(
                        cut,
                        padding=int(st.session_state.crop_padding)
                    )

                if st.session_state.add_border and st.session_state.border_size > 0:
                    cut = add_white_border_fixed(
                        cut,
                        border_size=int(st.session_state.border_size),
                        smooth_radius=int(st.session_state.border_smooth),
                        close_kernel_size=int(st.session_state.border_close_kernel)
                    )

                processed.append({
                    "name": item["name"],
                    "image": cut
                })

                progress.progress((i + 1) / len(st.session_state.raw_items[:MAX_ITEMS]))

            st.session_state.processed_items = processed
            st.session_state.editor_ready = True
            status.success("去背完成，可以進入 Editor 頁排版。")

        except Exception as e:
            st.error(f"去背處理失敗：{e}")

if st.session_state.editor_ready:
    st.success("已完成貼紙前處理。")
    st.page_link("pages/3_Editor.py", label="前往 Step 5 排版頁", icon="✨")

st.markdown('</div>', unsafe_allow_html=True)
