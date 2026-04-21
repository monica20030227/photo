import os
import shutil
import streamlit.components.v1 as components

FABRIC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js"></script>
    <style>
        html, body { margin: 0; padding: 0; width: 100%; background: #f8f8f8; font-family: sans-serif; overflow-x: hidden; overflow-y: auto; -webkit-overflow-scrolling: touch; }
        .outer { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 10px; padding-bottom: 8px; }
        .tools { width: 100%; max-width: 980px; display: flex; flex-direction: column; align-items: center; gap: 8px; padding-top: 8px; }
        .btn-group { display: flex; gap: 10px; }
        button { padding: 10px 18px; font-size: 15px; cursor: pointer; color: white; border: none; border-radius: 10px; font-weight: bold; }
        #sync-btn { background-color: #FF4B4B; }
        #sync-btn:hover { background-color: #ff3636; }
        #delete-btn { background-color: #666666; }
        #delete-btn:hover { background-color: #444444; }
        .tip { color: #666; font-size: 13px; text-align: center; line-height: 1.5; padding: 0 12px; }
        .canvas-wrap { width: 100%; display: flex; justify-content: center; align-items: flex-start; }
        /* 🌟 防呆：強制設定最小高度，避免手機端計算出錯時縮成 0px 變透明 */
        .canvas-shell { background: white; border: 1px solid #ddd; box-shadow: 0 4px 14px rgba(0,0,0,0.08); border-radius: 14px; padding: 6px; display: inline-block; box-sizing: border-box; touch-action: none; min-height: 300px; }
        .canvas-container { margin: 0 auto; }
    </style>
</head>
<body>
    <div class="outer">
        <div class="tools">
            <div class="btn-group">
                <button id="delete-btn">🗑️ 刪除選取物件</button>
                <button id="sync-btn">✨ 確認排版並產生下載檔</button>
            </div>
            <div class="tip">直接點擊照片或貼紙進行拖曳、縮放。</div>
        </div>
        <div class="canvas-wrap">
            <div class="canvas-shell" id="shell">
                <canvas id="editor"></canvas>
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
        let deletedIds = new Set(); 

        // 🌟 升級版安全計算：即使手機瀏覽器抓不到正確 vw，也有完美預設值
        function calcDisplaySize(origW, origH) {
            let vw = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth || 360;
            if (vw <= 0) vw = 360; // 絕對防呆

            const isMobile = vw <= 768;
            let maxWidth = isMobile ? vw - 24 : 380; 
            if (maxWidth <= 0) maxWidth = 300; // 絕對防呆

            if (origW && origH && origW > 0) {
                let scale = maxWidth / origW;
                let displayW = maxWidth;
                let displayH = origH * scale;
                return { displayWidth: Math.round(displayW), displayHeight: Math.round(displayH) };
            }
            return { displayWidth: 320, displayHeight: 480 };
        }

        function applyFixedDisplaySize(size) {
            const shell = document.getElementById("shell");
            shell.style.width = size.displayWidth + 14 + "px";
            shell.style.height = size.displayHeight + 14 + "px";
            if (canvas) {
                canvas.setDimensions({ width: size.displayWidth + "px", height: size.displayHeight + "px" }, { cssOnly: true });
                canvas.calcOffset();
            }
        }

        function constrainObject(obj) {
            if (obj.item_type === "frame") return;
            const canvasW = canvas.width;
            const canvasH = canvas.height;
            let newLeft = obj.left;
            let newTop = obj.top;
            if (newLeft < 0) newLeft = 0;
            if (newLeft > canvasW) newLeft = canvasW;
            if (newTop < 0) newTop = 0;
            if (newTop > canvasH) newTop = canvasH;
            if (newLeft !== obj.left || newTop !== obj.top) {
                obj.set({ left: newLeft, top: newTop });
                obj.setCoords();
            }
        }

        document.getElementById('delete-btn').onclick = function() {
            const activeObj = canvas.getActiveObject();
            if (activeObj) {
                if (activeObj.item_type === "frame") { alert("⚠️ 這是外框，無法刪除！"); return; }
                if (activeObj.item_type === "photo") { alert("⚠️ 這是主角照片，無法在此刪除！"); return; }
                deletedIds.add(activeObj.id); 
                canvas.remove(activeObj);
                canvas.requestRenderAll();
                syncLayout();
            } else { alert("請先點選想要刪除的物件！"); }
        };

        function syncLayout() {
            const layoutData = canvas.getObjects().map(obj => ({
                id: obj.id, x: obj.left, y: obj.top, scale: obj.scaleX, rotation: obj.angle, z: canvas.getObjects().indexOf(obj)
            }));
            Streamlit_setComponentValue(layoutData);
        }

        function initCanvas(args) {
            const size = calcDisplaySize(args.canvas_width, args.canvas_height);
            canvas = new fabric.Canvas('editor', { width: args.canvas_width, height: args.canvas_height, preserveObjectStacking: true, selection: false });
            applyFixedDisplaySize(size);
            canvas.on('object:moving', (e) => constrainObject(e.target));
            canvas.on('object:scaling', (e) => constrainObject(e.target));
            canvas.on('object:modified', syncLayout);

            const loadPromises = args.items.map(item => {
                return new Promise((resolve) => {
                    fabric.Image.fromURL(item.b64, function(img) {
                        // 🌟 容錯：就算這張圖片因為太大載入失敗，也不能讓整個頁面變透明崩潰
                        if (!img) {
                            resolve(null);
                            return;
                        }
                        let cp = (item.item_type === "photo" && item.hole_w) ? new fabric.Rect({ left: item.hole_x, top: item.hole_y, width: item.hole_w, height: item.hole_h, absolutePositioned: true }) : null;
                        img.set({
                            left: item.x, top: item.y, scaleX: item.scale, scaleY: item.scale, angle: item.rotation,
                            originX: 'center', originY: 'center', id: item.id, item_type: item.item_type,
                            clipPath: cp, selectable: (item.item_type !== "frame"), evented: (item.item_type !== "frame"),
                            cornerColor: '#FF4B4B', borderColor: '#FF4B4B', transparentCorners: false, cornerStyle: 'circle',
                            padding: 12, cornerSize: 24, touchCornerSize: 48
                        });
                        resolve({ img: img, z: item.item_type === "frame" ? 100 : (item.item_type === "photo" ? 10 : 200) });
                    }, { crossOrigin: "anonymous" });
                });
            });

            Promise.all(loadPromises).then(results => {
                results.filter(res => res !== null).sort((a, b) => a.z - b.z).forEach(res => canvas.add(res.img));
                canvas.renderAll();
                syncLayout();
            }).catch(err => {
                console.error("Canvas Error:", err);
                syncLayout(); // 發生錯誤依然要回傳，保證頁面不會卡死
            });

            document.getElementById('sync-btn').onclick = syncLayout;

            // 🌟 防呆高度設定：無論如何，強制給 iframe 一個安全的高度
            setTimeout(() => {
                let finalHeight = size.displayHeight + 180;
                if (isNaN(finalHeight) || finalHeight < 500) finalHeight = 600;
                Streamlit_setFrameHeight(finalHeight);
            }, 450);

            window.addEventListener("resize", function() {
                const newSize = calcDisplaySize(args.canvas_width, args.canvas_height);
                applyFixedDisplaySize(newSize);
                canvas.renderAll();
            });
        }

        function updateCanvas(args) {
            const existingIds = canvas.getObjects().map(obj => obj.id);
            args.items.forEach(item => {
                if (!existingIds.includes(item.id) && !deletedIds.has(item.id)) {
                    fabric.Image.fromURL(item.b64, function(img) {
                        if(!img) return;
                        img.set({
                            left: item.x, top: item.y, scaleX: item.scale, scaleY: item.scale, angle: item.rotation,
                            originX: 'center', originY: 'center', id: item.id, item_type: item.item_type,
                            selectable: true, evented: true, cornerColor: '#FF4B4B', borderColor: '#FF4B4B', transparentCorners: false, cornerStyle: 'circle', padding: 12, cornerSize: 24, touchCornerSize: 48
                        });
                        canvas.add(img);
                        canvas.renderAll();
                    }, { crossOrigin: "anonymous" });
                }
            });
        }

        window.addEventListener("message", function(event) {
            if (event.data.type === "streamlit:render") {
                if (!isInitialized) { initCanvas(event.data.args); isInitialized = true; }
                else { updateCanvas(event.data.args); }
            }
        });

        window.onload = function() { sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1}); };
    </script>
</body>
</html>
"""

_DIR = os.path.dirname(os.path.abspath(__file__))
# 更新快取標籤
_COMP_DIR = os.path.join(_DIR, "fabric_frontend_v14_mobile_fix")
if not os.path.exists(os.path.join(_COMP_DIR, "index.html")):
    os.makedirs(_COMP_DIR, exist_ok=True)
    with open(os.path.join(_COMP_DIR, "index.html"), "w", encoding="utf-8") as f: 
        f.write(FABRIC_HTML)

fabric_canvas = components.declare_component("fabric_canvas_v14_mobile_fix", path=_COMP_DIR)