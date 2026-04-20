import streamlit as st
import os
import base64

st.set_page_config(
    page_title="Joe's Snapshot",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1180px;
    }

    .hero {
        background: linear-gradient(135deg, #ffdce8 0%, #e7e8ff 100%);
        border: 1px solid rgba(255,255,255,0.7);
        border-radius: 28px;
        padding: 1.4rem 1.5rem;
        box-shadow: 0 10px 28px rgba(0,0,0,0.06);
        margin-bottom: 1.2rem;
    }

    .hero-row {
        display: flex;
        align-items: center;
        gap: 14px;
    }

    .logo-box {
        width: 68px;
        height: 68px;
        min-width: 68px;
        border-radius: 18px;
        background: rgba(255,255,255,0.78);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    .logo-box img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        padding: 6px;
    }

    .mode-card {
        background: rgba(255,255,255,0.84);
        border: 1px solid rgba(255,255,255,0.95);
        border-radius: 24px;
        padding: 1.2rem;
        box-shadow: 0 8px 20px rgba(0,0,0,0.04);
        min-height: 240px;
    }

    .mode-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #2b2b3a;
        margin-bottom: 0.5rem;
    }

    .mode-desc {
        color: #5f6678;
        line-height: 1.7;
        margin-bottom: 1rem;
    }

    .badge {
        display: inline-block;
        background: rgba(255,255,255,0.78);
        color: #6d4aff;
        border-radius: 999px;
        padding: 0.22rem 0.7rem;
        font-size: 0.82rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    div.stButton > button {
        border-radius: 14px;
        font-weight: 700;
        height: 46px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

if logo_path:
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="logo">'
else:
    logo_html = "📸"

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-row">
            <div class="logo-box">{logo_html}</div>
            <div>
                <div class="badge">Joe's Snapshot</div>
                <div style="font-size:2rem;font-weight:800;color:#2b2b3a;">Choose your mode</div>
                <div style="color:#5f6678;margin-top:0.3rem;">
                    先選擇你要做長條四連拍，還是去背貼紙。
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown(
        """
        <div class="mode-card">
            <div class="mode-title">📷 Photobooth｜長條四連拍</div>
            <div class="mode-desc">
                4 張長條型拍貼、內建純色框、倒數動畫、拍完後可加系統貼圖。
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.page_link("pages/1_Photobooth.py", label="進入拍貼機", icon="✨")

with col2:
    st.markdown(
        """
        <div class="mode-card">
            <div class="mode-title">✂️ Sticker Maker｜去背貼紙</div>
            <div class="mode-desc">
                使用你原本的去背、白邊、排版流程做貼紙。
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.page_link("pages/2_Sticker_Maker.py", label="進入 Sticker Maker", icon="🫧")
