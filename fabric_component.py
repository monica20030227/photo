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
            background: transparent;
            font-family: sans-serif;
            overflow: hidden;
            -webkit-overflow-scrolling: touch;
        }

        .outer {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            padding: 0 0 4px 0;
            background: transparent;
            box-sizing: border-box;
        }

        .tools {
            width: 100%;
            max-width: 980px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            padding-top: 4px;
            box-sizing: border-box;
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
            box-sizing: border-box;
        }

        .canvas-shell {
            background: white;
            border: 1px solid #ddd;
            box-shadow: 0 4px 14px rgba(0,0,0,0.08);
            border-radius: 14px;
            padding: 6px;
            display: inline-block;
            box-sizing: border-box;
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
                直接在這張固定比例卡片上拖曳、縮放、旋轉人物。<br>
                已加強點擊靈敏度。
            </div>
        </div>

        <div class="canvas-wrap">
            <div class="canvas-shell" id="shell">
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

        function calcDisplaySize() {
            const vw = Math.min(window.innerWidth || 390, document.documentElement.clientWidth || 390);
            const isMobile = vw <= 768;

            let boxWidth = 260;
            let boxHeight = 390;

            if (!isMobile) {
                boxWidth = 340;
                boxHeight = 510;
            }

            // 若螢幕太窄才縮小
            if (boxWidth > vw - 24) {
                const scale = (vw - 24) / boxWidth;
                boxWidth = Math.round(boxWidth * scale);
                boxHeight = Math.round(boxHeight * scale);
            }

            return {
                displayWidth: boxWidth,
                displayHeight: boxHeight
            };
        }

        function applyFixedDisplaySize(size) {
            const shell = document.getElementById("shell");
            const editor = document.getElementById("editor");

            shell.style.width = size.displayWidth + "px";
            shell.style.height = size.displayHeight + "px";

            editor.style.width = size.displayWidth + "px";
            editor.style.height = size.displayHeight + "px";
        }

        function updateFrameHeight() {
            const actualHeight = Math.max(
                document.body.scrollHeight,
                document.documentElement.scrollHeight
            );
            Streamlit_setFrameHeight(actualHeight + 8);
        }

        function initCanvas(args) {
            const cWidth = args.canvas_width;
            const cHeight = args.canvas_height;
            const size = calcDisplaySize();

            canvas = new fabric.Canvas('editor', {
                width: cWidth,
                height: cHeight,
                preserveObjectStacking: true,
                selection: true,
                allowTouchScrolling: true,

                // 提高手機點擊容錯
                targetFindTolerance: 24,
                perPixelTargetFind: false
            });

            fabric.Object.prototype.transparentCorners = false;
            fabric.Object.prototype.cornerStyle = 'circle';
            fabric.Object.prototype.cornerColor = '#FF4B4B';
            fabric.Object.prototype.borderColor = '#FF4B4B';

            // 保留高解析內部座標
            canvas.setDimensions(
                { width: cWidth, height: cHeight },
                { backstoreOnly: true }
            );

            // 套用固定顯示尺寸
            applyFixedDisplaySize(size);

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

                        // 提高操作靈敏度
                        padding: 28,
                        cornerSize: 24,
                        touchCornerSize: 38,
                        borderScaleFactor: 2,
                        objectCaching: false
                    });

                    // 只保留角落控制點，避免誤觸
                    img.setControlsVisibility({
                        mt: false,
                        mb: false,
                        ml: false,
                        mr: false
                    });

                    canvas.add(img);
                    canvas.renderAll();
                }, { crossOrigin: "anonymous" });
            });

            // 點空白時，如果很靠近物件，就自動選最近的物件
            canvas.on('mouse:down', function(opt) {
                if (!opt.target) {
                    const pointer = canvas.getPointer(opt.e);
                    let nearest = null;
                    let nearestDist = Infinity;

                    canvas.getObjects().forEach(obj => {
                        const dx = obj.left - pointer.x;
                        const dy = obj.top - pointer.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < nearestDist) {
                            nearestDist = dist;
                            nearest = obj;
                        }
                    });

                    if (nearest && nearestDist < 120) {
                        canvas.setActiveObject(nearest);
                        canvas.renderAll();
                    }
                }
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

            setTimeout(() => updateFrameHeight(), 250);

            window.addEventListener("resize", function() {
                const newSize = calcDisplaySize();
                applyFixedDisplaySize(newSize);
                canvas.renderAll();
                updateFrameHeight();
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
    component_dir = os.path.join(current_dir, "fabric_frontend_shared_v5")

    if os.path.exists(component_dir):
        try:
            shutil.rmtree(component_dir)
        except Exception:
            pass

    os.makedirs(component_dir, exist_ok=True)

    html_path = os.path.join(component_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(FABRIC_HTML)

    return components.declare_component("fabric_canvas_shared_v5", path=component_dir)

fabric_canvas = get_fabric_component()
