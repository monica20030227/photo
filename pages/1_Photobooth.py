import streamlit as st
from PIL import Image
import io
import base64

from webcam_component import custom_webcam

def init_state():
    if "pb_slots" not in st.session_state:
        st.session_state.pb_slots = [None, None, None, None]
    if "pb_current_slot" not in st.session_state:
        st.session_state.pb_current_slot = 0
    if "pb_shot_version" not in st.session_state:
        st.session_state.pb_shot_version = 0

init_state()

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #fffafc 0%, #f6f7ff 100%); }
    header, [data-testid="stHeader"], [data-testid="stToolbar"] { background: transparent !important; }
    .section-card { background: rgba(255,255,255,0.8); border: 1px solid rgba(255,255,255,0.95); border-radius: 22px; padding: 1rem 1.1rem; margin-bottom: 1rem; box-shadow: 0 8px 22px rgba(0,0,0,0.04); }
    div.stButton > button { border-radius: 14px; font-weight: 700; }
    div[data-testid="stImage"] img { border-radius: 12px; }
    </style>
    """, unsafe_allow_html=True
)

st.title("📷 取像與匯入")
st.caption("請完成 4 張照片的拍攝或上傳，接著前往 Editor 進行排版與貼紙裝飾。")

def open_if_not_none(file_obj):
    return Image.open(file_obj).convert("RGBA") if file_obj else None

with st.sidebar:
    st.header("照片管理")
    if st.button("🗑️ 清空所有照片重來", use_container_width=True):
        st.session_state.pb_slots = [None, None, None, None]
        st.session_state.pb_current_slot = 0
        st.session_state.pb_shot_version += 1
        st.rerun()

tab1, tab2 = st.tabs(["📸 拍照模式", "🖼️ 匯入模式"])

with tab1:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    if st.session_state.pb_current_slot < 4:
        st.write(f"目前要拍：**第 {st.session_state.pb_current_slot + 1} 張**")
        cam_data = custom_webcam(key=f"pb_cam_{st.session_state.pb_current_slot}_{st.session_state.pb_shot_version}")
        
        if cam_data and isinstance(cam_data, str) and cam_data.startswith("data:image"):
            preview_img = Image.open(io.BytesIO(base64.b64decode(cam_data.split(",")[1]))).convert("RGBA")
            st.success("✅ 拍攝成功！")
            
            prev_col, action_col = st.columns([1, 1.2])
            with prev_col:
                st.image(preview_img, caption=f"第 {st.session_state.pb_current_slot + 1} 張拍攝結果", use_container_width=True)
            with action_col:
                st.write("請確認照片是否滿意：")
                if st.button("✅ 保留這張", type="primary", use_container_width=True):
                    idx = st.session_state.pb_current_slot
                    st.session_state.pb_slots[idx] = preview_img
                    st.session_state.pb_current_slot = min(4, idx + 1)
                    st.session_state.pb_shot_version += 1
                    st.rerun()
                if st.button("🔄 不滿意，重拍", use_container_width=True):
                    st.session_state.pb_shot_version += 1
                    st.rerun()
    else:
        st.success("🎉 4 張都拍完了，可以往下前往 Editor！")
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    uploads = []
    cols = st.columns(2)
    for i in range(4):
        with cols[i % 2]:
            uploads.append(open_if_not_none(st.file_uploader(f"上傳第 {i+1} 張", type=["png", "jpg", "jpeg", "webp"], key=f"pb_upload_{i}")))
    if st.button("用匯入圖片覆蓋四張", use_container_width=True):
        st.session_state.pb_slots = uploads
        st.session_state.pb_current_slot = min(next((i for i, x in enumerate(uploads) if x is None), 4), 4)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.subheader("目前四張照片")
cols = st.columns(4)
for i in range(4):
    with cols[i]:
        # 🌟 修正 Streamlit Magic 顯示亂碼的 Bug
        if st.session_state.pb_slots[i] is not None:
            st.image(st.session_state.pb_slots[i], use_container_width=True)
        else:
            st.caption(f"第 {i+1} 張 尚未拍攝")

# ... (前方程式碼保持不變，找到最後的跳轉按鈕區塊)

st.divider()
if any(img is not None for img in st.session_state.pb_slots):
    if st.button("✨ 帶著照片前往 Editor 進行排版", type="primary", use_container_width=True):
        # 🌟 核心修正：設定模式並重置狀態，避免與去背功能衝突
        st.session_state.editor_mode = "photobooth"
        st.session_state.canvas_states = {}      # 清空舊排版座標
        st.session_state.processed_items = []    # 清空去背模式的貼紙
        st.switch_page("pages/3_Editor.py")