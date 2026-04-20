import streamlit as st
from PIL import Image, ImageDraw, ImageOps
import io
import math
import time

# =========================
# Session state
# =========================
def init_state():
    if "pb_slots" not in st.session_state:
        st.session_state.pb_slots = [None, None, None, None]
    if "pb_current_slot" not in st.session_state:
        st.session_state.pb_current_slot = 0
    if "pb_result" not in st.session_state:
        st.session_state.pb_result = None
    if "pb_shot_version" not in st.session_state:
        st.session_state.pb_shot_version = 0

init_state()

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

    .count-wrap {
        border-radius: 24px;
        background: rgba(255,255,255,0.72);
        padding: 1rem;
        text-align: center;
        margin-bottom: 1rem;
    }

    .count-num {
        font-size: 96px;
        font-weight: 900;
        line-height: 1;
        color: #6d4aff;
        animation: pop 0.8s ease;
    }

    @keyframes pop {
        0% { transform: scale(0.4); opacity: 0; }
        60% { transform: scale(1.12); opacity: 1; }
        100% { transform: scale(1); opacity: 1; }
    }

    .section-card {
        background: rgba(255,255,255,0.8);
        border: 1px solid rgba(255,255,255,0.95);
        border-radius: 22px;
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

st.title("📷 長條四連拍")
st.caption("內建純色框、倒數動畫、完成後可加系統貼圖")

# =========================
# Helpers
# =========================
FRAME_COLORS = {
    "白色": (255, 255, 255, 255),
    "粉色": (255, 223, 235, 255),
    "薰衣草紫": (232, 226, 255, 255),
    "天空藍": (222, 239, 255, 255),
    "薄荷綠": (224, 248, 239, 255),
    "奶油黃": (255, 245, 214, 255),
    "黑色": (30, 30, 35, 255),
}

def image_to_bytes(img: Image.Image):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def open_if_not_none(file_obj):
    if file_obj is None:
        return None
    return Image.open(file_obj).convert("RGBA")

def resize_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    img = img.convert("RGBA")
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / src_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))

def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask

def apply_round(img: Image.Image, radius: int):
    img = img.convert("RGBA")
    if radius <= 0:
        return img
    mask = rounded_mask(img.size, radius)
    rounded = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask)
    return rounded

def star_points(cx, cy, outer_r, inner_r, num_points=5):
    points = []
    angle = -math.pi / 2
    step = math.pi / num_points
    for i in range(num_points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r
        points.append((x, y))
        angle += step
    return points

def make_sticker(name: str, size: int = 220) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if name == "heart":
        r = size // 4
        draw.ellipse((size*0.18, size*0.12, size*0.18 + 2*r, size*0.12 + 2*r), fill=(255, 119, 156, 255))
        draw.ellipse((size*0.42, size*0.12, size*0.42 + 2*r, size*0.12 + 2*r), fill=(255, 119, 156, 255))
        draw.polygon(
            [(size*0.14, size*0.34), (size*0.86, size*0.34), (size*0.50, size*0.88)],
            fill=(255, 119, 156, 255)
        )

    elif name == "star":
        draw.polygon(star_points(size/2, size/2, size*0.38, size*0.16), fill=(255, 214, 88, 255))

    elif name == "sparkle":
        draw.polygon(star_points(size/2, size/2, size*0.34, size*0.08, num_points=4), fill=(167, 130, 255, 255))
        draw.ellipse((size*0.72, size*0.18, size*0.86, size*0.32), fill=(255,255,255,230))
        draw.ellipse((size*0.16, size*0.72, size*0.28, size*0.84), fill=(255,255,255,230))

    elif name == "smile":
        draw.ellipse((size*0.12, size*0.12, size*0.88, size*0.88), fill=(255, 214, 88, 255))
        draw.ellipse((size*0.33, size*0.35, size*0.41, size*0.43), fill=(60, 60, 60, 255))
        draw.ellipse((size*0.59, size*0.35, size*0.67, size*0.43), fill=(60, 60, 60, 255))
        draw.arc((size*0.30, size*0.38, size*0.70, size*0.72), start=15, end=165, fill=(60, 60, 60, 255), width=8)

    elif name == "flower":
        petal = (255, 173, 207, 255)
        center = (255, 214, 88, 255)
        petals = [
            (0.34, 0.08, 0.66, 0.40),
            (0.34, 0.60, 0.66, 0.92),
            (0.08, 0.34, 0.40, 0.66),
            (0.60, 0.34, 0.92, 0.66),
            (0.18, 0.18, 0.46, 0.46),
            (0.54, 0.18, 0.82, 0.46),
            (0.18, 0.54, 0.46, 0.82),
            (0.54, 0.54, 0.82, 0.82),
        ]
        for x1, y1, x2, y2 in petals:
            draw.ellipse((size*x1, size*y1, size*x2, size*y2), fill=petal)
        draw.ellipse((size*0.36, size*0.36, size*0.64, size*0.64), fill=center)

    return img

def add_stickers(base_img: Image.Image, sticker_names, sticker_size=170):
    base = base_img.copy().convert("RGBA")
    w, h = base.size
    positions = [
        (int(w*0.08), int(h*0.05)),
        (int(w*0.72), int(h*0.12)),
        (int(w*0.08), int(h*0.72)),
        (int(w*0.72), int(h*0.84)),
    ]
    for i, name in enumerate(sticker_names[:4]):
        sticker = make_sticker(name, size=sticker_size)
        x, y = positions[i]
        base.alpha_composite(sticker, (x, y))
    return base

def build_strip(
    images,
    canvas_w=900,
    canvas_h=2600,
    outer_margin=56,
    gap=28,
    photo_radius=28,
    frame_color=(255,255,255,255),
    inner_padding=18
):
    canvas = Image.new("RGBA", (canvas_w, canvas_h), frame_color)

    cell_w = canvas_w - outer_margin * 2
    cell_h = int((canvas_h - outer_margin * 2 - gap * 3) / 4)

    draw = ImageDraw.Draw(canvas)

    for idx in range(4):
        top_y = outer_margin + idx * (cell_h + gap)

        # 外框底板
        draw.rounded_rectangle(
            (outer_margin, top_y, outer_margin + cell_w, top_y + cell_h),
            radius=photo_radius + 8,
            fill=(255, 255, 255, 235) if frame_color != (255,255,255,255) else (245,245,250,255)
        )

        photo_x = outer_margin + inner_padding
        photo_y = top_y + inner_padding
        photo_w = cell_w - inner_padding * 2
        photo_h = cell_h - inner_padding * 2

        if images[idx] is None:
            placeholder = Image.new("RGBA", (photo_w, photo_h), (238, 238, 244, 255))
            ph_draw = ImageDraw.Draw(placeholder)
            ph_draw.rounded_rectangle((0, 0, photo_w-1, photo_h-1), radius=photo_radius, outline=(210,210,220,255), width=3)
            placeholder = apply_round(placeholder, photo_radius)
            canvas.alpha_composite(placeholder, (photo_x, photo_y))
        else:
            fitted = resize_cover(images[idx], photo_w, photo_h)
            fitted = apply_round(fitted, photo_radius)
            canvas.alpha_composite(fitted, (photo_x, photo_y))

    return canvas

def show_slot_grid():
    st.subheader("目前四張照片")
    cols = st.columns(4)
    for i in range(4):
        with cols[i]:
            st.markdown(f"**第 {i+1} 張**")
            if st.session_state.pb_slots[i] is not None:
                st.image(st.session_state.pb_slots[i], use_container_width=True)
            else:
                st.caption("尚未拍攝 / 匯入")

# =========================
# Sidebar settings
# =========================
with st.sidebar:
    st.header("拍貼設定")
    strip_w = st.number_input("成品寬度", min_value=600, max_value=1800, value=900, step=50)
    strip_h = st.number_input("成品高度", min_value=1600, max_value=4200, value=2600, step=100)
    outer_margin = st.slider("外圍留白", 10, 120, 56)
    gap = st.slider("四張間距", 0, 80, 28)
    photo_radius = st.slider("照片圓角", 0, 80, 28)
    inner_padding = st.slider("內框厚度", 0, 40, 18)

    frame_name = st.selectbox("內建純色框", list(FRAME_COLORS.keys()), index=1)
    selected_stickers = st.multiselect(
        "完成後加入貼圖",
        ["heart", "star", "sparkle", "smile", "flower"],
        default=["heart", "sparkle"]
    )
    sticker_size = st.slider("貼圖大小", 80, 280, 170)

    st.divider()
    if st.button("清空四張照片", use_container_width=True):
        st.session_state.pb_slots = [None, None, None, None]
        st.session_state.pb_current_slot = 0
        st.session_state.pb_result = None
        st.session_state.pb_shot_version += 1
        st.rerun()

# =========================
# Input tabs
# =========================
tab1, tab2 = st.tabs(["📸 拍照模式", "🖼️ 匯入模式"])

with tab1:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.write(f"目前要拍：**第 {st.session_state.pb_current_slot + 1} 張**")

    if st.session_state.pb_current_slot < 4:
        if st.button(f"開始第 {st.session_state.pb_current_slot + 1} 張倒數", type="primary", use_container_width=True):
            holder = st.empty()
            for n in [3, 2, 1]:
                holder.markdown(
                    f'<div class="count-wrap"><div class="count-num">{n}</div></div>',
                    unsafe_allow_html=True
                )
                time.sleep(1)
            holder.markdown(
                '<div class="count-wrap"><div class="count-num" style="font-size:64px;">GO!</div></div>',
                unsafe_allow_html=True
            )
            time.sleep(0.8)
            holder.empty()

        cam = st.camera_input(
            f"拍第 {st.session_state.pb_current_slot + 1} 張",
            key=f"pb_cam_{st.session_state.pb_current_slot}_{st.session_state.pb_shot_version}"
        )

        if cam is not None:
            preview_img = Image.open(cam).convert("RGBA")
            st.image(preview_img, caption="拍攝預覽", use_container_width=True)

            if st.button("使用這張照片", use_container_width=True):
                idx = st.session_state.pb_current_slot
                st.session_state.pb_slots[idx] = preview_img
                st.session_state.pb_current_slot = min(4, idx + 1)
                st.session_state.pb_result = None
                st.session_state.pb_shot_version += 1
                st.rerun()
    else:
        st.success("4 張都拍完了，可以往下產生成品。")
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    uploads = []
    cols = st.columns(2)
    for i in range(4):
        with cols[i % 2]:
            f = st.file_uploader(
                f"上傳第 {i+1} 張",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"pb_upload_{i}"
            )
            uploads.append(open_if_not_none(f))

    if st.button("用匯入圖片覆蓋四張", use_container_width=True):
        st.session_state.pb_slots = uploads
        last_filled = 0
        for i in range(4):
            if uploads[i] is not None:
                last_filled = i + 1
        st.session_state.pb_current_slot = min(last_filled, 4)
        st.session_state.pb_result = None
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

show_slot_grid()

# =========================
# Result
# =========================
st.subheader("產生成品")

if st.button("產生長條四連拍", type="primary", use_container_width=True):
    strip = build_strip(
        st.session_state.pb_slots,
        canvas_w=strip_w,
        canvas_h=strip_h,
        outer_margin=outer_margin,
        gap=gap,
        photo_radius=photo_radius,
        frame_color=FRAME_COLORS[frame_name],
        inner_padding=inner_padding
    )

    if selected_stickers:
        strip = add_stickers(strip, selected_stickers, sticker_size=sticker_size)

    st.session_state.pb_result = strip

if st.session_state.pb_result is not None:
    st.subheader("成品預覽")
    st.image(st.session_state.pb_result, use_container_width=True)

    st.download_button(
        "下載長條四連拍 PNG",
        data=image_to_bytes(st.session_state.pb_result),
        file_name="photobooth_strip.png",
        mime="image/png",
        use_container_width=True
    )