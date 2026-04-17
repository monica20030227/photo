import os
import shutil
import streamlit.components.v1 as components

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
            width: 100%;
            background: #f8f8f8;
            font-family: sans-serif;
            overflow-x: hidden;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
        }

        .outer {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            padding-bottom: 8px;
        }

        .tools {
            width: 100%;
            max-width: 980px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
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
            padding: 0 12px;
        }

        .canvas-wrap {
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: flex-start;
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
            touch-action: pan-y pinch-zoom;
        }
    </style>
</head>
<body>
    <div class="outer">
        <div class="tools">
            <button id="sync-btn">確認排版並產生下載檔</button>
            <div class="tip">
                直接在這張完整比例卡片上拖曳、縮放、旋轉人物。<br>
                手機上看到的就是整張版面。
            </div>
        </div>

        <div class="canvas-wrap">
            <div class="canvas-shell">
                <canvas id="editor"></canvas>
            </div>
        </div>
    </div>

    <script>
        function sendMessageToStreamlitClient(type, data) {
            window.parent.postMessage(
                Object.assign({isStreamlitMessage: true, type: type}, data),
                "*"
            );
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
                // 手機上固定接近背景卡片大小，但比背景圖再大一點，方便操作
                displayWidth = Math.min(vw - 36, 200);
            } else {
                // 桌機稍微放大
                displayWidth = 380;
            }

            const displayHeight = Math.round(cHeight * (displayWidth / cWidth));

            return {
                displayWidth: displayWidth,
                displayHeight: displayHeight
            };
        }

        function updateFrameHeight(size) {
            const targetHeight = size.displayHeight + 150;
            Streamlit_setFrameHeight(targetHeight);
        }

        function initCanvas(args) {
            const cWidth = args.canvas_width;
            const cHeight = args.canvas_height;
            const size = calcDisplaySize(cWidth, cHeight);

            canvas = new fabric.Canvas('editor', {
                width: cWidth,
                height: cHeight,
                preserveObjectStacking: true,
                selection: true,
                allowTouchScrolling: true
            });

            // 關鍵：只改顯示尺寸，不改實際座標系統
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

            setTimeout(() => updateFrameHeight(size), 450);

            window.addEventListener("resize", function() {
                const newSize = calcDisplaySize(cWidth, cHeight);
                canvas.setDimensions(
                    { width: newSize.displayWidth, height: newSize.displayHeight },
                    { cssOnly: true }
                );
                updateFrameHeight(newSize);
            });
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
    component_dir = os.path.join(current_dir, "fabric_frontend_shared")

    if os.path.exists(component_dir):
        try:
            shutil.rmtree(component_dir)
        except Exception:
            pass

    os.makedirs(component_dir, exist_ok=True)

    html_path = os.path.join(component_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(FABRIC_HTML)

    return components.declare_component("fabric_canvas_shared", path=component_dir)

fabric_canvas = get_fabric_component()
