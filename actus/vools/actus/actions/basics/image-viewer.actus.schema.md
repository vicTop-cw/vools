---
id: image-viewer
name: Image Viewer
version: 1.0.0
trust: sandbox
entry: main
description: A beautiful image viewer with modern UI
author: vools
platform: desktop
tags: [image, viewer, gui, webview2]
max_instances: 1
deprecated: false
---

# Image Viewer

A beautiful image viewer with modern UI built with HTML/CSS/JavaScript and WebView2.

## Usage

```python
from vools.actus.actions import load_action

action = load_action("image-viewer")
result = action.execute()
```

## Implementation

```webview2 title="Image Viewer" width=900 height=700 resizable=true devtools=false
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Viewer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .viewer {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
            width: 100%;
            max-width: 1200px;
            height: 90vh;
            max-height: 800px;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 15px 20px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .header-title {
            color: white;
            font-size: 18px;
            font-weight: 600;
            margin-right: auto;
        }
        
        .header-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .header-btn:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.05);
        }
        
        .content {
            flex: 1;
            display: flex;
            overflow: hidden;
        }
        
        .sidebar {
            width: 250px;
            background: #f8f9fa;
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
        }
        
        .folder-info {
            padding: 15px 20px;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .folder-name {
            font-size: 14px;
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }
        
        .folder-count {
            font-size: 12px;
            color: #999;
        }
        
        .image-list {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
        }
        
        .image-item {
            padding: 12px;
            border-radius: 10px;
            cursor: pointer;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: all 0.2s;
        }
        
        .image-item:hover {
            background: #e9ecef;
        }
        
        .image-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .image-thumb {
            width: 50px;
            height: 50px;
            border-radius: 8px;
            object-fit: cover;
            background: #e0e0e0;
        }
        
        .image-name {
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #1a1a1a;
        }
        
        .viewer-area {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            position: relative;
            overflow: hidden;
        }
        
        .image-container {
            max-width: 100%;
            max-height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .main-image {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 8px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            transition: transform 0.3s ease;
        }
        
        .main-image.zoomed {
            cursor: grab;
        }
        
        .controls {
            padding: 15px 20px;
            background: rgba(255, 255, 255, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .nav-buttons {
            display: flex;
            gap: 10px;
        }
        
        .nav-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            padding: 12px 18px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .nav-btn:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        
        .zoom-controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .zoom-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 18px;
            transition: all 0.2s;
        }
        
        .zoom-btn:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        
        .zoom-level {
            color: white;
            font-size: 14px;
            min-width: 50px;
            text-align: center;
        }
        
        .image-info {
            color: white;
            font-size: 14px;
        }
        
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: rgba(255, 255, 255, 0.5);
            height: 100%;
        }
        
        .empty-state-icon {
            font-size: 80px;
            margin-bottom: 20px;
            opacity: 0.3;
        }
        
        .empty-state-text {
            font-size: 16px;
        }
        
        .drag-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(102, 126, 234, 0.9);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            color: white;
            font-size: 24px;
        }
        
        .drag-overlay.active {
            display: flex;
        }
        
        .toolbar {
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.1);
            display: flex;
            gap: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .toolbar-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }
        
        .toolbar-btn:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        
        .fullscreen {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 0;
            padding: 0;
        }
        
        .fullscreen .sidebar {
            width: 300px;
        }
    </style>
</head>
<body>
    <div class="viewer">
        <div class="header">
            <div class="header-title">🖼️ Image Viewer</div>
            <button class="header-btn" onclick="openFolder()">📂 Open Folder</button>
            <button class="header-btn" onclick="toggleFullscreen()">⛶</button>
        </div>
        
        <div class="content">
            <div class="sidebar">
                <div class="folder-info">
                    <div class="folder-name" id="folderName">No folder selected</div>
                    <div class="folder-count" id="folderCount">0 images</div>
                </div>
                <div class="image-list" id="imageList"></div>
            </div>
            
            <div class="main-content">
                <div class="toolbar">
                    <button class="toolbar-btn" onclick="rotateLeft()">↺ Rotate</button>
                    <button class="toolbar-btn" onclick="rotateRight()">↻ Rotate</button>
                    <button class="toolbar-btn" onclick="flipHorizontal()">↔️ Flip H</button>
                    <button class="toolbar-btn" onclick="flipVertical()">↕️ Flip V</button>
                    <button class="toolbar-btn" onclick="resetTransform()">Reset</button>
                </div>
                
                <div class="viewer-area" id="viewerArea">
                    <div class="empty-state" id="emptyState">
                        <div class="empty-state-icon">🖼️</div>
                        <div class="empty-state-text">Open a folder to view images</div>
                    </div>
                    <div class="image-container" id="imageContainer" style="display: none;">
                        <img id="mainImage" class="main-image" src="" alt="">
                    </div>
                </div>
                
                <div class="controls">
                    <div class="nav-buttons">
                        <button class="nav-btn" onclick="prevImage()">◀ Prev</button>
                        <button class="nav-btn" onclick="nextImage()">Next ▶</button>
                    </div>
                    <div class="zoom-controls">
                        <button class="zoom-btn" onclick="zoomOut()">−</button>
                        <span class="zoom-level" id="zoomLevel">100%</span>
                        <button class="zoom-btn" onclick="zoomIn()">+</button>
                        <button class="zoom-btn" onclick="resetZoom()">⊡</button>
                    </div>
                    <div class="image-info" id="imageInfo"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="drag-overlay" id="dragOverlay">Drop images here</div>
    
    <script>
        let images = [];
        let currentIndex = 0;
        let currentZoom = 1;
        let currentRotation = 0;
        let flipH = false;
        let flipV = false;
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        
        const imageList = document.getElementById('imageList');
        const mainImage = document.getElementById('mainImage');
        const imageContainer = document.getElementById('imageContainer');
        const emptyState = document.getElementById('emptyState');
        const folderName = document.getElementById('folderName');
        const folderCount = document.getElementById('folderCount');
        const zoomLevel = document.getElementById('zoomLevel');
        const imageInfo = document.getElementById('imageInfo');
        const viewerArea = document.getElementById('viewerArea');
        const dragOverlay = document.getElementById('dragOverlay');
        
        function openFolder() {
            const input = document.createElement('input');
            input.type = 'file';
            input.webkitdirectory = true;
            input.onchange = (e) => {
                const files = Array.from(e.target.files);
                loadImages(files);
            };
            input.click();
        }
        
        function loadImages(files) {
            const imageFiles = files.filter(file => 
                file.type.startsWith('image/')
            );
            
            if (imageFiles.length === 0) {
                alert('No images found in this folder');
                return;
            }
            
            images = imageFiles.map((file, index) => ({
                name: file.name,
                path: file.path || file.name,
                url: URL.createObjectURL(file),
                index: index
            }));
            
            const folderPath = files[0].path || files[0].name;
            const folderPathParts = folderPath.split('\\');
            folderName.textContent = folderPathParts[folderPathParts.length - 2] || 'Images';
            folderCount.textContent = `${images.length} images`;
            
            currentIndex = 0;
            renderImageList();
            showImage(0);
        }
        
        function renderImageList() {
            imageList.innerHTML = images.map((img, index) => `
                <div class="image-item ${index === currentIndex ? 'active' : ''}" onclick="showImage(${index})">
                    <img class="image-thumb" src="${img.url}" alt="">
                    <div class="image-name">${img.name}</div>
                </div>
            `).join('');
        }
        
        function showImage(index) {
            if (images.length === 0) return;
            
            currentIndex = index;
            const img = images[index];
            
            mainImage.src = img.url;
            mainImage.onload = () => {
                resetTransform();
                emptyState.style.display = 'none';
                imageContainer.style.display = 'flex';
                updateImageInfo();
                renderImageList();
            };
        }
        
        function prevImage() {
            if (images.length === 0) return;
            const newIndex = currentIndex > 0 ? currentIndex - 1 : images.length - 1;
            showImage(newIndex);
        }
        
        function nextImage() {
            if (images.length === 0) return;
            const newIndex = currentIndex < images.length - 1 ? currentIndex + 1 : 0;
            showImage(newIndex);
        }
        
        function zoomIn() {
            currentZoom = Math.min(currentZoom + 0.1, 5);
            applyTransform();
        }
        
        function zoomOut() {
            currentZoom = Math.max(currentZoom - 0.1, 0.1);
            applyTransform();
        }
        
        function resetZoom() {
            currentZoom = 1;
            applyTransform();
        }
        
        function rotateLeft() {
            currentRotation -= 90;
            applyTransform();
        }
        
        function rotateRight() {
            currentRotation += 90;
            applyTransform();
        }
        
        function flipHorizontal() {
            flipH = !flipH;
            applyTransform();
        }
        
        function flipVertical() {
            flipV = !flipV;
            applyTransform();
        }
        
        function resetTransform() {
            currentZoom = 1;
            currentRotation = 0;
            flipH = false;
            flipV = false;
            applyTransform();
        }
        
        function applyTransform() {
            const scaleX = flipH ? -currentZoom : currentZoom;
            const scaleY = flipV ? -currentZoom : currentZoom;
            mainImage.style.transform = `scale(${scaleX}, ${scaleY}) rotate(${currentRotation}deg)`;
            zoomLevel.textContent = `${Math.round(currentZoom * 100)}%`;
        }
        
        function updateImageInfo() {
            if (images.length === 0) return;
            const img = images[currentIndex];
            imageInfo.textContent = `${currentIndex + 1} / ${images.length}`;
        }
        
        function toggleFullscreen() {
            const viewer = document.querySelector('.viewer');
            if (!document.fullscreenElement) {
                viewer.requestFullscreen();
            } else {
                document.exitFullscreen();
            }
        }
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (images.length === 0) return;
            
            switch (e.key) {
                case 'ArrowLeft':
                    prevImage();
                    break;
                case 'ArrowRight':
                    nextImage();
                    break;
                case '+':
                case '=':
                    zoomIn();
                    break;
                case '-':
                    zoomOut();
                    break;
                case '0':
                    resetZoom();
                    break;
            }
        });
        
        // Mouse wheel zoom
        viewerArea.addEventListener('wheel', (e) => {
            if (images.length === 0) return;
            e.preventDefault();
            if (e.deltaY < 0) {
                zoomIn();
            } else {
                zoomOut();
            }
        });
        
        // Drag to pan
        mainImage.addEventListener('mousedown', (e) => {
            if (currentZoom > 1) {
                isDragging = true;
                dragStartX = e.clientX - mainImage.offsetLeft;
                dragStartY = e.clientY - mainImage.offsetTop;
                mainImage.style.cursor = 'grabbing';
            }
        });
        
        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const x = e.clientX - dragStartX;
                const y = e.clientY - dragStartY;
                mainImage.style.position = 'relative';
                mainImage.style.left = x + 'px';
                mainImage.style.top = y + 'px';
            }
        });
        
        document.addEventListener('mouseup', () => {
            isDragging = false;
            mainImage.style.cursor = 'grab';
        });
        
        // Drag and drop
        document.addEventListener('dragover', (e) => {
            e.preventDefault();
            dragOverlay.classList.add('active');
        });
        
        dragOverlay.addEventListener('dragleave', () => {
            dragOverlay.classList.remove('active');
        });
        
        dragOverlay.addEventListener('drop', (e) => {
            e.preventDefault();
            dragOverlay.classList.remove('active');
            
            const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
            if (files.length > 0) {
                loadImages(files);
            }
        });
    </script>
</body>
</html>
```

## Notes

- Open folder with images
- Navigate with arrow keys or buttons
- Zoom with mouse wheel or buttons
- Rotate and flip images
- Fullscreen mode
- Drag and drop support
- Modern gradient design with smooth animations

## Permissions

```yaml
permissions:
  - gui:show
  - filesystem:read
```
