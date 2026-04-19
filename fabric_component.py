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
            box-sizing: border-box;
            touch-action: none; 
        }

        .canvas-container {
            margin: 0 auto;
        }
    </style>
</head>
<body>
    <div class="outer">
        <div class="tools">
            <button id="sync-btn">確認排版並產生下載檔</button>
            <div class="tip">
                直接在卡片上拖曳、縮放貼紙。<br>
                (貼紙將被嚴格限制，完全無法超出背景範圍)
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
            let boxWidth = 260, boxHeight = 390;

            if (!isMobile) {
                boxWidth = 340;
                boxHeight = 510;
            }

            if (boxWidth > vw - 24) {
                const scale = (vw - 24) / boxWidth;
                boxWidth = Math.round(boxWidth * scale);
                boxHeight = Math.round(boxHeight * scale);
            }

            return { displayWidth: boxWidth, displayHeight: boxHeight };
        }

        function applyFixedDisplaySize(size) {
            const shell = document.getElementById("shell");
            shell.style.width = size.displayWidth + 14 + "px";
            shell.style.height = size.displayHeight + 14 + "px";
            if (canvas) {
                canvas.setDimensions(
                    { width: size.displayWidth + "px", height: size.displayHeight + "px" },
                    { cssOnly: true }
                );
                canvas.calcOffset();
            }
        }

        // 🌟 核心修改：嚴格邊界限制邏輯 (0% 超出)
        function constrainObject(obj) {
            // 必須先更新座標系，取得最新佔位空間
            obj.setCoords();
            const rect = obj.getBoundingRect();
            const canvasW = canvas.width;
            const canvasH = canvas.height;
            
            let newLeft = obj.left;
            let newTop = obj.top;

            // 處理 X 軸 (左右邊界)
            if (rect.width > canvasW) {
                // 防呆：如果物件被放大到比畫布還寬，強制鎖在正中間，避免無限拉扯
                newLeft = canvasW / 2;
            } else {
                if (rect.left < 0) {
                    newLeft -= rect.left; // 撞到左牆
                } else if (rect.left + rect.width > canvasW) {
                    newLeft -= ((rect.left + rect.width) - canvasW); // 撞到右牆
                }
            }

            // 處理 Y 軸 (上下邊界)
            if (rect.height > canvasH) {
                // 防呆：如果物件被放大到比畫布還高，強制鎖在正中間
                newTop = canvasH / 2;
            } else {
                if (rect.top < 0) {
                    newTop -= rect.top; // 撞到天花板
                } else if (rect.top + rect.height > canvasH) {
                    newTop -= ((rect.top + rect.height) - canvasH); // 撞到地板
                }
            }

            // 如果座標需要修正，就寫入新座標並重新刷新
            if (newLeft !== obj.left || newTop !== obj.top) {
                obj.set({
                    left: newLeft,
                    top: newTop
                });
                obj.setCoords(); // 修正後再次更新座標
            }
        }

        function initCanvas(args) {
            const cWidth = args.canvas_width;
            const cHeight = args.canvas_height;
            const size = calcDisplaySize();

            canvas = new fabric.Canvas('editor', {
                width: cWidth,
                height: cHeight,
                preserveObjectStacking: true,
                selection: false
            });

            applyFixedDisplaySize(size);

            // 監聽移動與縮放，即時修正位置
            canvas.on('object:moving', (e) => constrainObject(e.target));
            canvas.on('object:scaling', (e) => constrainObject(e.target));

            if (args.bg_b64) {
                fabric.Image.fromURL(args.bg_b64, function(img) {
                    img.set({
                        scaleX: cWidth / img.width,
                        scaleY: cHeight / img.height,
                        originX: 'left', originY: 'top',
                        selectable: false, evented: false
                    });
                    canvas.setBackgroundImage(img, canvas.renderAll.bind(canvas));
                }, { crossOrigin: "anonymous" });
            }

            args.items.forEach((item) => {
                fabric.Image.fromURL(item.b64, function(img) {
                    img.set({
                        left: item.x, top: item.y,
                        scaleX: item.scale, scaleY: item.scale,
                        angle: item.rotation,
                        originX: 'center', originY: 'center',
                        id: item.id,
                        cornerColor: '#FF4B4B', borderColor: '#FF4B4B',
                        transparentCorners: false, cornerStyle: 'circle',
                        padding: 12, cornerSize: 24, touchCornerSize: 48
                    });
                    canvas.add(img);
                    
                    // 🌟 載入後立刻檢查一次，確保一開始也不會在外面
                    const objIndex = canvas.getObjects().length - 1;
                    const loadedObj = canvas.item(objIndex);
                    constrictInitially(loadedObj);

                }, { crossOrigin: "anonymous" });
            });

            // 輔助函式：確保載入當下也不會出界
            function constrictInitially(obj) {
                if(!obj) return;
                constrainObject(obj);
                canvas.renderAll();
            }

            document.getElementById('sync-btn').onclick = function() {
                const layoutData = canvas.getObjects().map(obj => ({
                    id: obj.id,
                    x: obj.left, y: obj.top,
                    scale: obj.scaleX, rotation: obj.angle,
                    z: canvas.getObjects().indexOf(obj)
                }));
                Streamlit_setComponentValue(layoutData);
            };

            setTimeout(() => Streamlit_setFrameHeight(size.displayHeight + 180), 450);
            window.addEventListener("resize", function() {
                const newSize = calcDisplaySize();
                applyFixedDisplaySize(newSize);
                canvas.renderAll();
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
    # 改變資料夾名稱以確保 Streamlit 吃到新的快取
    component_dir = os.path.join(current_dir, "fabric_frontend_v5_strict")

    if os.path.exists(component_dir):
        try: shutil.rmtree(component_dir)
        except: pass

    os.makedirs(component_dir, exist_ok=True)
    with open(os.path.join(component_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(FABRIC_HTML)

    return components.declare_component("fabric_canvas_v5_strict", path=component_dir)

fabric_canvas = get_fabric_component()
