// FloorplanGenerator MTV behavior
(function(){
  const ROOM_LABELS = {
    japanStyle: 'guest room',
    study: 'study room',
    storage: 'storage',
    balcony: 'balcony',
    secondLiving: 'second living room'
  };
  const POLL_INTERVAL_MS = 3000;
  const POLL_TIMEOUT_MS = 5 * 60 * 1000;

  const floorEl = document.getElementById('floorBtns');
  const totalAreaInput = document.getElementById('totalArea');
  const floorSections = Array.from(document.querySelectorAll('.floor-settings'));
  const floorControls = new Map();
  const generateBtn = document.querySelector('.generate-btn');
  const areaPlanInfo = document.getElementById('areaPlanInfo');
  const heroImg = document.querySelector('#proposal1 img');
  const sketchCanvas = document.getElementById('sketchCanvas');
  const sketchToggleBtn = document.getElementById('sketchToggleBtn');
  const sketchUndoBtn = document.getElementById('sketchUndoBtn');
  const sketchClearBtn = document.getElementById('sketchClearBtn');
  const sketchSaveBtn = document.getElementById('sketchSaveBtn');
  const sketchCommandInput = document.getElementById('sketchCommand');
  const sketchApplyCommandBtn = document.getElementById('sketchApplyCommand');
  const landInfoGroup = document.getElementById('landInfoGroup');
  const landInfoEmpty = document.getElementById('landInfoEmpty');
  const landInfoContent = document.getElementById('landInfoContent');
  const landInfoCanvas = document.getElementById('landInfoCanvas');
  const landInfoAreaValue = document.getElementById('landInfoAreaValue');
  const landInfoPreviewButton = document.getElementById('landInfoPreviewButton');
  const landInfoModal = document.getElementById('landInfoModal');
  const landInfoModalClose = document.getElementById('landInfoModalClose');
  const landInfoModalCanvas = document.getElementById('landInfoModalCanvas');
  const landInfoModalAreaValue = document.getElementById('landInfoModalAreaValue');
  const landInfoClearBtn = document.getElementById('landInfoClearBtn');
  const statusEl = document.createElement('div');
  statusEl.className = 'status-message status-info';
  if(generateBtn){
    generateBtn.insertAdjacentElement('afterend', statusEl);
  }

  const loadingOverlay = document.getElementById('loadingOverlay');
  const loadingMessageEl = loadingOverlay ? loadingOverlay.querySelector('.loading-message') : null;
  const loadingProgressBar = document.getElementById('loadingProgressBar');

  let pollTimer = null;
  let activeJobId = null;
  let pendingAreaPlanValue = null;
  let displayedProgress = 0;
  let targetProgress = 0;
  let progressTimer = null;
  let progressAnimStart = 0;
  let progressAnimFrom = 0;
  let progressAnimTo = 0;
  let progressAnimDuration = 0;
  let progressBaseMessage = 'Generating floorplans...';
  let progressOnDone = null;
  const fallbackHeroSrc = heroImg ? heroImg.src : null;

  const DRAW_SIZE = 600; // inner area (px) representing 20000mm
  const CANVAS_SIZE = 720;
  const CANVAS_MARGIN = (CANVAS_SIZE - DRAW_SIZE) / 2; // 50px borders
  const LOGICAL_SIZE = 20000; // millimetres in each axis
  const LOGICAL_STEP = 1000; // millimetres grid spacing
  const SCALE = DRAW_SIZE / LOGICAL_SIZE; // 0.3 px per mm

  const sketchState = {
    drawing: false,
    points: [],
    lines: [],
    lastPoint: null,
    maskSupersample: 8,
  };

  const SNAP_DISTANCE = 10;

  function captureLandPreviewDataUrl(){
    if(!landInfoCanvas) return null;
    try{
      const context = landInfoCanvas.getContext('2d');
      if(!context) return null;
      // Avoid capturing a completely blank canvas by checking alpha data
      const { width, height } = landInfoCanvas;
      const pixels = context.getImageData(0, 0, width, height).data;
      const hasContent = pixels.some((value, index) => index % 4 === 3 ? value !== 0 : false);
      if(!hasContent) return null;
      return landInfoCanvas.toDataURL('image/png');
    }catch(err){
      console.warn('Unable to capture land preview:', err);
      return null;
    }
  }

  function resetLandInfoCanvas(){
    if(!landInfoCanvas) return;
    const ctx = landInfoCanvas.getContext('2d');
    if(!ctx) return;
    const { width, height } = landInfoCanvas;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = '#cbd5f5';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
  }

  function showLandInfoPlaceholder(){
    if(landInfoEmpty) landInfoEmpty.classList.remove('hidden');
    if(landInfoContent) landInfoContent.classList.add('hidden');
    if(landInfoAreaValue){
      landInfoAreaValue.textContent = '--';
      landInfoAreaValue.removeAttribute('title');
    }
    if(landInfoModalAreaValue){
      landInfoModalAreaValue.textContent = '--';
      landInfoModalAreaValue.removeAttribute('title');
    }
    resetLandInfoCanvas();
    if(landInfoModalCanvas){
      const ctx = landInfoModalCanvas.getContext('2d');
      if(ctx){
        ctx.clearRect(0, 0, landInfoModalCanvas.width, landInfoModalCanvas.height);
        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, landInfoModalCanvas.width, landInfoModalCanvas.height);
        ctx.strokeStyle = '#d1d5db';
        ctx.lineWidth = 1;
        ctx.strokeRect(0.5, 0.5, landInfoModalCanvas.width - 1, landInfoModalCanvas.height - 1);
      }
    }
  }

  function showLandInfoContent(){
    if(landInfoEmpty) landInfoEmpty.classList.add('hidden');
    if(landInfoContent) landInfoContent.classList.remove('hidden');
  }

  function formatLengthMm(length){
    if(!Number.isFinite(length)) return '--';
    return `${Math.round(length)}`;
  }

  function setLandAreaValue(areaMm2){
    if(!landInfoAreaValue) return;
    if(!Number.isFinite(areaMm2) || areaMm2 <= 0){
      landInfoAreaValue.textContent = '--';
      landInfoAreaValue.removeAttribute('title');
      if(landInfoModalAreaValue){
        landInfoModalAreaValue.textContent = '--';
        landInfoModalAreaValue.removeAttribute('title');
      }
      return;
    }
    const areaM2 = areaMm2 / 1_000_000;
    landInfoAreaValue.textContent = `${areaM2.toFixed(2)} m²`;
    landInfoAreaValue.title = `${Math.round(areaMm2).toLocaleString()} mm²`;
    if(landInfoModalAreaValue){
      landInfoModalAreaValue.textContent = `${areaM2.toFixed(2)} m²`;
      landInfoModalAreaValue.title = `${Math.round(areaMm2).toLocaleString()} mm²`;
    }
  }

  function pointsRoughlyEqual(a, b){
    if(!a || !b) return false;
    const EPS = 1e-4;
    return Math.abs(a[0] - b[0]) <= EPS && Math.abs(a[1] - b[1]) <= EPS;
  }

  function computePolygonCentroid(points){
    if(!points.length){
      return { x: 0, y: 0 };
    }
    let areaAcc = 0;
    let cxAcc = 0;
    let cyAcc = 0;
    const count = points.length;
    for(let i = 0; i < count; i += 1){
      const [x1, y1] = points[i];
      const [x2, y2] = points[(i + 1) % count];
      const cross = x1 * y2 - x2 * y1;
      areaAcc += cross;
      cxAcc += (x1 + x2) * cross;
      cyAcc += (y1 + y2) * cross;
    }
    const area = areaAcc / 2;
    if(Math.abs(area) < 1e-5){
      let sumX = 0;
      let sumY = 0;
      points.forEach(([x, y]) => {
        sumX += x;
        sumY += y;
      });
      const denom = points.length || 1;
      return { x: sumX / denom, y: sumY / denom };
    }
    return {
      x: cxAcc / (6 * area),
      y: cyAcc / (6 * area),
    };
  }

  function drawEdgeLabel(ctx, start, end, label, centroid){
    const [x1, y1] = start;
    const [x2, y2] = end;
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const angle = Math.atan2(dy, dx);
    let displayAngle = angle;
    if(displayAngle > Math.PI / 2 || displayAngle < -Math.PI / 2){
      displayAngle += Math.PI;
    }
    const length = Math.hypot(dx, dy) || 1;
    const offsetDistance = 10;
    let nx = -(dy / length);
    let ny = dx / length;
    if(centroid){
      const toCentroidX = centroid.x - midX;
      const toCentroidY = centroid.y - midY;
      if(nx * toCentroidX + ny * toCentroidY > 0){
        nx = -nx;
        ny = -ny;
      }
    }
    const labelX = midX + nx * offsetDistance;
    const labelY = midY + ny * offsetDistance;

    ctx.save();
    ctx.translate(labelX, labelY);
    ctx.rotate(displayAngle);
    ctx.font = '10px "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const metrics = ctx.measureText(label);
    const textWidth = metrics.width;
    const ascent = metrics.actualBoundingBoxAscent || 6;
    const descent = metrics.actualBoundingBoxDescent || 6;
    const textHeight = ascent + descent;
    const padding = 3;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
    ctx.fillRect(-textWidth / 2 - padding, -textHeight / 2 - padding, textWidth + padding * 2, textHeight + padding * 2);
    ctx.fillStyle = '#111827';
    ctx.fillText(label, 0, 0);
    ctx.restore();
  }

  function drawEdgeLabelSmall(ctx, start, end, label, centroid){
    const [x1, y1] = start;
    const [x2, y2] = end;
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const angle = Math.atan2(dy, dx);
    let displayAngle = angle;
    if(displayAngle > Math.PI / 2 || displayAngle < -Math.PI / 2){
      displayAngle += Math.PI;
    }
    const length = Math.hypot(dx, dy) || 1;
    const offsetDistance = 6;
    let nx = -(dy / length);
    let ny = dx / length;
    if(centroid){
      const toCentroidX = centroid.x - midX;
      const toCentroidY = centroid.y - midY;
      if(nx * toCentroidX + ny * toCentroidY > 0){
        nx = -nx;
        ny = -ny;
      }
    }
    const labelX = midX + nx * offsetDistance;
    const labelY = midY + ny * offsetDistance;

    ctx.save();
    ctx.translate(labelX, labelY);
    ctx.rotate(displayAngle);
    ctx.font = '8px "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const metrics = ctx.measureText(label);
    const textWidth = metrics.width;
    const ascent = metrics.actualBoundingBoxAscent || 6;
    const descent = metrics.actualBoundingBoxDescent || 6;
    const textHeight = ascent + descent;
    const padding = 2;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
    ctx.fillRect(-textWidth / 2 - padding, -textHeight / 2 - padding, textWidth + padding * 2, textHeight + padding * 2);
    ctx.fillStyle = '#111827';
    ctx.fillText(label, 0, 0);
    ctx.restore();
  }

  function renderLandInfoCanvas(data){
    if(!landInfoCanvas) return;
    const ctx = landInfoCanvas.getContext('2d');
    if(!ctx) return;
    const { width, height } = landInfoCanvas;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, width, height);

    const renderTarget = (context, targetWidth, targetHeight, drawEdges = true, smallLabels = false) => {
      context.clearRect(0, 0, targetWidth, targetHeight);
      context.fillStyle = '#f8fafc';
      context.fillRect(0, 0, targetWidth, targetHeight);
      context.save();
      context.strokeStyle = '#cbd5f5';
      context.lineWidth = 1;
      context.strokeRect(0.5, 0.5, targetWidth - 1, targetHeight - 1);
      context.restore();

      const rawPoints = Array.isArray(data.points_px) ? data.points_px : [];
      if(rawPoints.length < 2) return;

      const scaleX = targetWidth / CANVAS_SIZE;
      const scaleY = targetHeight / CANVAS_SIZE;
      const scaledPoints = rawPoints.map(pt => [pt.x * scaleX, pt.y * scaleY]);
      const centroidPoints = pointsRoughlyEqual(scaledPoints[0], scaledPoints[scaledPoints.length - 1])
        ? scaledPoints.slice(0, -1)
        : scaledPoints;
      const centroid = computePolygonCentroid(centroidPoints);

      context.save();
      context.beginPath();
      scaledPoints.forEach(([sx, sy], idx) => {
        if(idx === 0){
          context.moveTo(sx, sy);
        }else{
          context.lineTo(sx, sy);
        }
      });
      context.closePath();
      context.fillStyle = 'rgba(59, 130, 246, 0.18)';
      context.strokeStyle = '#1d4ed8';
      context.lineWidth = 2;
      context.fill();
      context.stroke();
      context.restore();

      if(!drawEdges) return;
      const lengths = Array.isArray(data.lengths_mm) ? data.lengths_mm : [];
      const edgeCount = Math.min(lengths.length, scaledPoints.length - 1);
      if(edgeCount <= 0) return;

      for(let i = 0; i < edgeCount; i += 1){
        const start = scaledPoints[i];
        const end = scaledPoints[i + 1];
        if(smallLabels){
          drawEdgeLabelSmall(context, start, end, formatLengthMm(lengths[i]), centroid);
        }else{
          drawEdgeLabel(context, start, end, formatLengthMm(lengths[i]), centroid);
        }
      }
    };

    const drawPreview = () => {
      renderTarget(ctx, width, height, true, true);
      if(landInfoModalCanvas){
        const modalCtx = landInfoModalCanvas.getContext('2d');
        if(modalCtx){
          renderTarget(modalCtx, landInfoModalCanvas.width, landInfoModalCanvas.height, true, false);
        }
      }
    };

    if(data.preview_data_url){
      const img = new Image();
      img.decoding = 'async';
      img.onload = () => {
        ctx.drawImage(img, 0, 0, width, height);
        if(landInfoModalCanvas){
          const modalCtx = landInfoModalCanvas.getContext('2d');
          if(modalCtx){
            modalCtx.drawImage(img, 0, 0, landInfoModalCanvas.width, landInfoModalCanvas.height);
          }
        }
        drawPreview();
      };
      img.onerror = drawPreview;
      img.src = data.preview_data_url;
    }else{
      drawPreview();
    }
  }

  async function loadLatestLandInfo(){
    if(!landInfoGroup) return;
    showLandInfoPlaceholder();
    try{
      const response = await fetch(`/api/latest-land-info?t=${Date.now()}`, { cache: 'no-store' });
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if(!data || data.success !== true){
        return;
      }
      showLandInfoContent();
      setLandAreaValue(data.area_mm2);
      renderLandInfoCanvas(data);
    }catch(err){
      console.warn('Unable to load land info:', err);
    }
  }

  if(landInfoGroup){
    showLandInfoPlaceholder();
  }

  function openLandInfoModal(){
    if(!landInfoModal) return;
    landInfoModal.classList.remove('hidden');
    document.body.classList.add('overlay-active');
  }

  function closeLandInfoModal(){
    if(!landInfoModal) return;
    landInfoModal.classList.add('hidden');
    document.body.classList.remove('overlay-active');
  }

  if(landInfoPreviewButton){
    landInfoPreviewButton.addEventListener('click', openLandInfoModal);
  }

  if(landInfoModalClose){
    landInfoModalClose.addEventListener('click', closeLandInfoModal);
  }

  if(landInfoModal){
    landInfoModal.addEventListener('click', event => {
      if(event.target === landInfoModal){
        closeLandInfoModal();
      }
    });
  }

  if(landInfoClearBtn){
    landInfoClearBtn.addEventListener('click', () => {
      closeLandInfoModal();
      showLandInfoPlaceholder();
    });
  }

  function hasSketchCanvas(){
    return Boolean(sketchCanvas && sketchCanvas.getContext);
  }

  function updateSketchButtons(){
    const hasLines = sketchState.lines.length > 0;
    if(sketchToggleBtn){
      sketchToggleBtn.textContent = sketchState.drawing ? 'Exit (Esc)' : 'Line';
    }
    if(sketchUndoBtn){
      sketchUndoBtn.disabled = !hasLines;
    }
    if(sketchSaveBtn){
      sketchSaveBtn.disabled = sketchState.points.length < 3;
    }
  }

  function redrawSketch(){
    if(!hasSketchCanvas()) return;
    const ctx = sketchCanvas.getContext('2d');
    ctx.clearRect(0, 0, sketchCanvas.width, sketchCanvas.height);

    drawAxes(ctx);

    ctx.lineWidth = 2;
    ctx.strokeStyle = '#000';
    sketchState.lines.forEach(line => {
      ctx.beginPath();
      ctx.moveTo(line[0][0], line[0][1]);
      ctx.lineTo(line[1][0], line[1][1]);
      ctx.stroke();
    });
  }

  function drawAxes(ctx){
    ctx.save();
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    ctx.fillStyle = '#f8f9ff';
    ctx.fillRect(CANVAS_MARGIN, CANVAS_MARGIN, DRAW_SIZE, DRAW_SIZE);

    const majorStepMm = 5000;
    for(let val = 0; val <= LOGICAL_SIZE; val += LOGICAL_STEP){
      const offset = val * SCALE;
      const isMajor = val % majorStepMm === 0;
      ctx.lineWidth = isMajor ? (val === 0 || val === LOGICAL_SIZE ? 1.5 : 1.2) : 1;
      ctx.strokeStyle = isMajor ? '#bfc3e0' : '#d0d3e8';

      const y = CANVAS_MARGIN + DRAW_SIZE - offset;
      ctx.beginPath();
      ctx.moveTo(CANVAS_MARGIN, y);
      ctx.lineTo(CANVAS_MARGIN + DRAW_SIZE, y);
      ctx.stroke();

      const x = CANVAS_MARGIN + offset;
      ctx.beginPath();
      ctx.moveTo(x, CANVAS_MARGIN);
      ctx.lineTo(x, CANVAS_MARGIN + DRAW_SIZE);
      ctx.stroke();
    }

    ctx.lineWidth = 2;
    ctx.strokeStyle = '#7278c3';
    // X axis (bottom)
    ctx.beginPath();
    ctx.moveTo(CANVAS_MARGIN, CANVAS_MARGIN + DRAW_SIZE);
    ctx.lineTo(CANVAS_MARGIN + DRAW_SIZE, CANVAS_MARGIN + DRAW_SIZE);
    ctx.stroke();
    // Y axis (left)
    ctx.beginPath();
    ctx.moveTo(CANVAS_MARGIN, CANVAS_MARGIN);
    ctx.lineTo(CANVAS_MARGIN, CANVAS_MARGIN + DRAW_SIZE);
    ctx.stroke();

    ctx.font = '11px "Segoe UI", sans-serif';
    ctx.fillStyle = '#3f46a5';
    for(let val = majorStepMm; val <= LOGICAL_SIZE; val += majorStepMm){
      const offset = val * SCALE;
      const labelX = CANVAS_MARGIN + offset;
      const labelY = CANVAS_MARGIN + DRAW_SIZE - offset;
      const meterValue = val / 1000; // Convert mm to m
      ctx.fillText(String(meterValue), labelX - 18, CANVAS_MARGIN + DRAW_SIZE + 18);
      ctx.fillText(String(meterValue), CANVAS_MARGIN - 30, labelY + 4);
    }

    ctx.fillText('x (m)', CANVAS_MARGIN + DRAW_SIZE + 26, CANVAS_MARGIN + DRAW_SIZE + 18);
    ctx.save();
    ctx.translate(CANVAS_MARGIN - 32, CANVAS_MARGIN - 8);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('y (m)', 0, 0);
    ctx.restore();

    ctx.restore();
  }

  function clampToDrawArea(x, y){
    const clampedX = Math.max(CANVAS_MARGIN, Math.min(CANVAS_MARGIN + DRAW_SIZE, x));
    const clampedY = Math.max(CANVAS_MARGIN, Math.min(CANVAS_MARGIN + DRAW_SIZE, y));
    return [clampedX, clampedY];
  }

  function rebuildPointsFromLines(){
    if(sketchState.lines.length){
      sketchState.points = [sketchState.lines[0][0], ...sketchState.lines.map(line => line[1])];
      sketchState.lastPoint = sketchState.points[sketchState.points.length - 1];
    }else{
      sketchState.points = [];
      sketchState.lastPoint = null;
    }
  }

  function toCanvasCoords([xValue, yValue]){
    const clampedX = Math.max(0, Math.min(LOGICAL_SIZE, xValue));
    const clampedY = Math.max(0, Math.min(LOGICAL_SIZE, yValue));
    const canvasX = CANVAS_MARGIN + (clampedX * SCALE);
    const canvasY = CANVAS_MARGIN + DRAW_SIZE - (clampedY * SCALE);
    return [canvasX, canvasY];
  }

  function fromCanvasCoords(x, y){
    const clampedX = Math.max(CANVAS_MARGIN, Math.min(CANVAS_MARGIN + DRAW_SIZE, x));
    const clampedY = Math.max(CANVAS_MARGIN, Math.min(CANVAS_MARGIN + DRAW_SIZE, y));
    const logicalX = Math.max(0, Math.min(LOGICAL_SIZE, (clampedX - CANVAS_MARGIN) / SCALE));
    const logicalY = Math.max(0, Math.min(LOGICAL_SIZE, (CANVAS_MARGIN + DRAW_SIZE - clampedY) / SCALE));
    return [logicalX, logicalY];
  }

  function getSnapPoint(x, y){
    let [candidateX, candidateY] = clampToDrawArea(x, y);
    const last = sketchState.lastPoint;
    if(last){
      const dx = candidateX - last[0];
      const dy = candidateY - last[1];
      if(dx !== 0){
        const angle = Math.abs(Math.atan(dy / dx) * (180 / Math.PI));
        if(angle < 10 || angle > 80){
          if(Math.abs(dx) > Math.abs(dy)){
            for(let i = 0; i < sketchState.lines.length; i += 1){
              const line = sketchState.lines[i];
              if(Math.abs(candidateX - line[0][0]) < SNAP_DISTANCE){
                return clampToDrawArea(line[0][0], last[1]);
              }
            }
            return clampToDrawArea(candidateX, last[1]);
          }
          for(let i = 0; i < sketchState.lines.length; i += 1){
            const line = sketchState.lines[i];
            if(Math.abs(candidateY - line[0][1]) < SNAP_DISTANCE){
              return clampToDrawArea(last[0], line[0][1]);
            }
          }
          return clampToDrawArea(last[0], candidateY);
        }
      }
    }

    for(let i = 0; i < sketchState.lines.length; i += 1){
      const line = sketchState.lines[i];
      for(let j = 0; j < 2; j += 1){
        const pt = line[j];
        if(Math.abs(candidateX - pt[0]) < SNAP_DISTANCE && Math.abs(candidateY - pt[1]) < SNAP_DISTANCE){
          return clampToDrawArea(pt[0], pt[1]);
        }
        if(Math.abs(candidateX - pt[0]) < SNAP_DISTANCE){
          return clampToDrawArea(pt[0], candidateY);
        }
        if(Math.abs(candidateY - pt[1]) < SNAP_DISTANCE){
          return clampToDrawArea(candidateX, pt[1]);
        }
      }
    }
    return clampToDrawArea(candidateX, candidateY);
  }

  function drawPreviewLine(point){
    if(!hasSketchCanvas() || !sketchState.lastPoint) return;
    redrawSketch();
    const ctx = sketchCanvas.getContext('2d');
    ctx.setLineDash([4, 2]);
    ctx.beginPath();
    ctx.moveTo(sketchState.lastPoint[0], sketchState.lastPoint[1]);
    const [px, py] = clampToDrawArea(point[0], point[1]);
    ctx.lineTo(px, py);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function handleSketchClick(event){
    if(!sketchState.drawing) return;
    const rect = sketchCanvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const snapped = getSnapPoint(x, y);
    const logical = fromCanvasCoords(snapped[0], snapped[1]);
    const canvasPoint = toCanvasCoords(logical);
    appendPoint(canvasPoint);
  }

  function handleSketchMove(event){
    if(!sketchState.drawing || !sketchState.lastPoint) return;
    const rect = sketchCanvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const snap = getSnapPoint(x, y);
    drawPreviewLine(snap);
  }

  function toggleSketchMode(){
    sketchState.drawing = !sketchState.drawing;
    if(!sketchState.drawing){
      redrawSketch();
      sketchState.lastPoint = null;
    }
    updateSketchButtons();
  }

  function undoSketch(){
    if(!sketchState.lines.length) return;
    sketchState.lines.pop();
    rebuildPointsFromLines();
    redrawSketch();
    updateSketchButtons();
  }

  function clearSketch(){
    sketchState.lines = [];
    sketchState.points = [];
    sketchState.lastPoint = null;
    redrawSketch();
    updateSketchButtons();
  }

  function parseCommandInput(text){
    if(!text) return null;
    const parts = text.split(/[\s,]+/).filter(Boolean);
    if(parts.length !== 2) return null;
    const x = Number(parts[0]);
    const y = Number(parts[1]);
    if(!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [x, y];
  }

  function normalisePoint([x, y]){
    return clampToDrawArea(x, y);
  }

  function buildLinesFromPoints(points){
    const lines = [];
    for(let i = 1; i < points.length; i += 1){
      lines.push([points[i - 1], points[i]]);
    }
    return lines;
  }

  function appendPoint(point){
    const normalised = normalisePoint(point);
    if(!sketchState.points.length){
      sketchState.points = [normalised];
      sketchState.lines = [];
    }else{
      const existingLast = sketchState.points[sketchState.points.length - 1];
      sketchState.lines.push([existingLast, normalised]);
      sketchState.points.push(normalised);
    }
    sketchState.lastPoint = normalised;
    redrawSketch();
    updateSketchButtons();
  }

  function createCanvas(width, height){
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  function canvasToBlob(canvas){
    return new Promise((resolve, reject) => {
      if(typeof canvas.toBlob === 'function'){
        canvas.toBlob(blob => {
          if(blob){
            resolve(blob);
          }else{
            reject(new Error('Unable to convert canvas to blob'));
          }
        }, 'image/png');
      }else if(canvas instanceof HTMLCanvasElement && canvas.ownerDocument){
        try{
          const dataUrl = canvas.toDataURL('image/png');
          const binary = atob(dataUrl.split(',')[1]);
          const array = new Uint8Array(binary.length);
          for(let i = 0; i < binary.length; i += 1){
            array[i] = binary.charCodeAt(i);
          }
          resolve(new Blob([array], { type: 'image/png' }));
        }catch(err){
          reject(err);
        }
      }else{
        reject(new Error('Canvas toBlob not supported'));
      }
    });
  }

  function buildMaskImage(){
    if(!sketchState.points.length || !hasSketchCanvas()) return null;
    const polygon = sketchState.points.map(pt => [Math.round(pt[0]), Math.round(pt[1])]);
    if(polygon.length > 2){
      const first = polygon[0];
      const last = polygon[polygon.length - 1];
      if(first[0] !== last[0] || first[1] !== last[1]){
        polygon.push([first[0], first[1]]);
      }
    }

    const scale = Math.max(1, sketchState.maskSupersample);
    const width = sketchCanvas.width * scale;
    const height = sketchCanvas.height * scale;
    const offscreen = createCanvas(width, height);
    const ctx = offscreen.getContext('2d');
    if(!ctx) return null;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#000';
    ctx.beginPath();
    polygon.forEach(([px, py], idx) => {
      const scaledX = Math.round(px * scale);
      const scaledY = Math.round(py * scale);
      if(idx === 0){
        ctx.moveTo(scaledX, scaledY);
      }else{
        ctx.lineTo(scaledX, scaledY);
      }
    });
    ctx.closePath();
    ctx.fill();

    return offscreen;
  }

  function generatePreviewMask(offscreen){
    if(!offscreen) return null;
    const resized = createCanvas(64, 64);
    const ctx = resized.getContext('2d');
    if(!ctx) return null;
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(offscreen, 0, 0, 64, 64);
    return resized;
  }

  async function saveMaskAndPoints(){
    if(!hasSketchCanvas() || sketchState.points.length < 3) return;
    const maskCanvas = buildMaskImage();
    const previewMask = generatePreviewMask(maskCanvas);
    if(!maskCanvas || !previewMask) return;

    const [fullBlob, previewBlob] = await Promise.all([
      canvasToBlob(maskCanvas),
      canvasToBlob(previewMask),
    ]);

    const pointsPayload = {
      points: sketchState.points.map(([px, py]) => {
        const [lx, ly] = fromCanvasCoords(px, py);
        return { x_mm: Math.round(lx), y_mm: Math.round(ly), x: Math.round(px), y: Math.round(py) };
      }),
      logical_size_mm: LOGICAL_SIZE,
      grid_step_mm: LOGICAL_STEP,
    };

    const formData = new FormData();
    formData.append('mask', fullBlob, 'mask.png');
    formData.append('mask_preview', previewBlob, 'mask_64.png');
    formData.append('points', JSON.stringify(pointsPayload));

    sketchSaveBtn.disabled = true;
    try{
      const response = await fetch('/api/upload-sketch', {
        method: 'POST',
        body: formData,
      });
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }
      setStatus('Sketch saved successfully.', 'success');
      loadLatestLandInfo();
    }catch(err){
      console.error(err);
      setStatus(`Unable to save sketch: ${err.message}`, 'error');
    }finally{
      sketchSaveBtn.disabled = false;
    }
  }

  function initSketchCanvas(){
    if(!hasSketchCanvas()) return;
    redrawSketch();
    sketchCanvas.addEventListener('click', handleSketchClick);
    sketchCanvas.addEventListener('mousemove', handleSketchMove);
    document.addEventListener('keydown', event => {
      if(event.key === 'Escape' && sketchState.drawing){
        toggleSketchMode();
      }
      if((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && sketchState.lines.length){
        event.preventDefault();
        undoSketch();
      }
    });

    if(sketchToggleBtn){
      sketchToggleBtn.addEventListener('click', () => {
        toggleSketchMode();
      });
    }
    if(sketchUndoBtn){
      sketchUndoBtn.addEventListener('click', () => {
        undoSketch();
      });
    }
    if(sketchClearBtn){
      sketchClearBtn.addEventListener('click', () => {
        clearSketch();
      });
    }
    if(sketchSaveBtn){
      sketchSaveBtn.addEventListener('click', () => {
        saveMaskAndPoints();
      });
    }
    function handleCommand(){
      if(!sketchCommandInput) return;
      const text = sketchCommandInput.value.trim();
      let canvasPoint = null;
      let statusMessage = 'Point added to sketch.';

      if(text === ''){
        if(sketchState.points.length >= 3){
          const firstPoint = sketchState.points[0];
          const lastPoint = sketchState.points[sketchState.points.length - 1];
          if(firstPoint && lastPoint && firstPoint[0] === lastPoint[0] && firstPoint[1] === lastPoint[1]){
            setStatus('Shape already closed.', 'info');
            return;
          }
          canvasPoint = [...firstPoint];
          statusMessage = 'Shape closed to starting point.';
        }else{
          setStatus('Enter coordinates until you have at least 3 points.', 'error');
          return;
        }
      }else{
        const parsed = parseCommandInput(text);
        if(parsed === null){
          setStatus('Invalid command. Format "x,y"', 'error');
          return;
        }
        canvasPoint = normalisePoint(toCanvasCoords(parsed));
      }

      appendPoint(canvasPoint);
      sketchCommandInput.value = '';
      setStatus(statusMessage, 'success');
    }
    if(sketchApplyCommandBtn){
      sketchApplyCommandBtn.addEventListener('click', () => handleCommand());
    }
    if(sketchCommandInput){
      sketchCommandInput.addEventListener('keydown', event => {
        if(event.key === 'Enter'){
          event.preventDefault();
          handleCommand();
        }
      });
    }

    updateSketchButtons();
  }


  function updateAreaPlanDisplay(value){
    if(!areaPlanInfo) return;
    if(Number.isFinite(value) && value > 0){
      areaPlanInfo.textContent = `Area Plan: ${value.toFixed(2)} m2`;
      areaPlanInfo.classList.remove('hidden');
    }else{
      areaPlanInfo.textContent = '';
      areaPlanInfo.classList.add('hidden');
    }
  }

  function queueAreaPlan(value){
    if(!areaPlanInfo) return;
    const numeric = Number(value);
    if(!Number.isFinite(numeric) || numeric <= 0){
      pendingAreaPlanValue = null;
      updateAreaPlanDisplay(null);
      return;
    }
    pendingAreaPlanValue = numeric;
    updateAreaPlanDisplay(null);
    if(heroImg && heroImg.complete && heroImg.naturalWidth > 0){
      updateAreaPlanDisplay(pendingAreaPlanValue);
      pendingAreaPlanValue = null;
    }
  }

  function handleHeroLoad(){
    if(pendingAreaPlanValue !== null){
      updateAreaPlanDisplay(pendingAreaPlanValue);
      pendingAreaPlanValue = null;
    }
  }

  function handleHeroError(){
    pendingAreaPlanValue = null;
    updateAreaPlanDisplay(null);
  }

  if(heroImg){
    heroImg.addEventListener('load', handleHeroLoad);
    heroImg.addEventListener('error', handleHeroError);
  }

  if(areaPlanInfo){
    const initialArea = Number(areaPlanInfo.dataset.initialArea);
    if(Number.isFinite(initialArea) && initialArea > 0){
      queueAreaPlan(initialArea);
    }else{
      queueAreaPlan(null);
    }
  }

  const initialFloor = floorEl ? Number(floorEl.querySelector('.btn-toggle.active')?.dataset.floor || 1) : 1;

  const state = {
    floor: initialFloor,
    totalArea: totalAreaInput ? Number(totalAreaInput.value) || 0 : 0,
    floors: {}
  };

  function ensureFloorState(floor){
    if(!state.floors[floor]){
      state.floors[floor] = {};
    }
    return state.floors[floor];
  }

  function showFloorSection(floor){
    floorSections.forEach(section => {
      const sectionFloor = Number(section.dataset.floor);
      section.classList.toggle('hidden', sectionFloor !== floor);
    });
  }

  function syncFloorSections(){
    floorControls.forEach((controls, floor) => {
      const floorState = ensureFloorState(floor);
      controls.selects?.forEach(select => {
        const field = select.dataset.field;
        if(field in floorState){
          select.value = String(floorState[field]);
        }
      });
      controls.checkboxes?.forEach(checkbox => {
        const field = checkbox.dataset.field;
        if(field in floorState){
          checkbox.checked = Boolean(floorState[field]);
        }
      });
    });
    showFloorSection(state.floor);
  }

  function registerFloorControls(){
    floorControls.clear();
    floorSections.forEach(section => {
      const floor = Number(section.dataset.floor);
      if(!Number.isFinite(floor)) return;
      const selects = Array.from(section.querySelectorAll('select[data-field]'));
      const checkboxes = Array.from(section.querySelectorAll('input[type="checkbox"][data-field]'));
      floorControls.set(floor, { section, selects, checkboxes });
      const floorState = ensureFloorState(floor);

      selects.forEach(select => {
        const field = select.dataset.field;
        const numericValue = Number(select.value);
        floorState[field] = Number.isFinite(numericValue) ? numericValue : select.value;
        select.addEventListener('change', () => {
          const val = Number(select.value);
          floorState[field] = Number.isFinite(val) ? val : select.value;
        });
      });

      checkboxes.forEach(checkbox => {
        const field = checkbox.dataset.field;
        floorState[field] = checkbox.checked;
        checkbox.addEventListener('change', () => {
          floorState[field] = checkbox.checked;
        });
      });
    });
  }

  function syncFloorButtons(){
    if(!floorEl) return;
    floorEl.querySelectorAll('.btn-toggle').forEach(btn => {
      const floor = Number(btn.dataset.floor || 0);
      btn.classList.toggle('active', floor === state.floor);
    });
  }

  function syncFields(){
    if(totalAreaInput){
      totalAreaInput.value = state.totalArea ? String(state.totalArea) : '';
    }
    syncFloorSections();
  }

  function clearPollTimer(){
    if(pollTimer){
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function setStatus(message, type = 'info'){
    if(!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.remove('status-info', 'status-success', 'status-error');
    statusEl.classList.add(`status-${type}`);
  }

  function updateLoadingMessage(message){
    if(!loadingMessageEl || !message) return;
    loadingMessageEl.textContent = message;
  }

  function showLoadingOverlay(message){
    if(!loadingOverlay) return;
    if(message){
      updateLoadingMessage(message);
    }
    loadingOverlay.hidden = false;
    loadingOverlay.setAttribute('aria-hidden', 'false');
    if(loadingProgressBar){
      loadingProgressBar.style.width = '0%';
      loadingProgressBar.setAttribute('aria-valuenow', '0');
    }
  }

  function hideLoadingOverlay(){
    if(!loadingOverlay) return;
    loadingOverlay.hidden = true;
    loadingOverlay.setAttribute('aria-hidden', 'true');
  }

  function stopProgressTimer(){
    if(progressTimer){
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  function animateProgressTo(newTarget, durationMs, onDone){
    if(!Number.isFinite(newTarget)) return;
    const nextTarget = Math.max(0, Math.min(100, Math.round(newTarget)));
    // Never animate backwards
    const fromVal = Math.max(displayedProgress, 0);
    if(nextTarget <= fromVal){
      targetProgress = nextTarget;
      displayedProgress = fromVal; // no change
      if(typeof onDone === 'function') onDone();
      return;
    }
    // Start a new animation that runs for a fixed duration
    targetProgress = nextTarget;
    progressAnimFrom = fromVal;
    progressAnimTo = nextTarget;
    progressAnimDuration = Math.max(100, Number(durationMs) || 3000);
    progressAnimStart = Date.now();
    progressOnDone = typeof onDone === 'function' ? onDone : null;
    stopProgressTimer();
    progressTimer = setInterval(() => {
      const elapsed = Date.now() - progressAnimStart;
      const t = Math.min(1, elapsed / progressAnimDuration);
      // easeOutCubic for a gentle feel
      const eased = 1 - Math.pow(1 - t, 3);
      displayedProgress = Math.min(
        progressAnimTo,
        Math.round(progressAnimFrom + (progressAnimTo - progressAnimFrom) * eased)
      );
      // live update overlay message as it animates
      const pct = Math.max(0, Math.min(100, Math.round(displayedProgress)));
      updateLoadingMessage(`${progressBaseMessage} ${pct}%`);
      if(loadingProgressBar){
        loadingProgressBar.style.width = `${pct}%`;
        loadingOverlay?.setAttribute?.('aria-valuenow', String(pct));
      }
      if(t >= 1 || displayedProgress >= progressAnimTo){
        displayedProgress = progressAnimTo;
        stopProgressTimer();
        if(progressOnDone){
          const cb = progressOnDone;
          progressOnDone = null;
          cb();
        }
      }
    }, 100); // refresh 10x/second for smoothness
  }

  function syncAll(){
    syncFloorButtons();
    syncFields();
  }

  function formatCount(count, label){
    return `${count} ${label}`;
  }

  const EXTRA_ROOM_FIELDS = ['japanStyle', 'study', 'storage', 'balcony', 'secondLiving'];

  function normaliseCount(value){
    if(typeof value === 'boolean'){
      return value ? 1 : 0;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
  }

  function buildRoomDescription(){
    const floorState = ensureFloorState(state.floor);
    if(!floorState){
      return '';
    }

    const totals = {
      living: 0,
      master: 0,
      second: 0,
      bathroom: 0,
      japanStyle: 0,
      study: 0,
      storage: 0,
      balcony: 0,
      secondLiving: 0
    };

    const ldk = Number(floorState.ldk) || 0;
    if(ldk > 0){
      totals.living = 1;
      totals.master = 1;
      if(ldk > 1){
        totals.second = ldk - 1;
      }
    }

    const toiletCount = normaliseCount(floorState.toilet);
    if(toiletCount > 0 || floorState.toilet !== undefined){
      totals.bathroom = 1 + toiletCount;
    }

    EXTRA_ROOM_FIELDS.forEach(field => {
      const count = normaliseCount(floorState[field]);
      if(count){
        totals[field] = count;
      }
    });

    const items = [];
    if(totals.living) items.push(formatCount(totals.living, 'living room'));
    if(totals.master) items.push(formatCount(totals.master, 'master room'));
    if(totals.second) items.push(formatCount(totals.second, 'second room'));
    if(totals.bathroom) items.push(formatCount(totals.bathroom, 'bathroom'));

    EXTRA_ROOM_FIELDS.forEach(field => {
      if(totals[field]){
        const label = ROOM_LABELS[field];
        if(label){
          items.push(formatCount(totals[field], label));
        }
      }
    });

    return items.join(', ');
  }

  async function saveRequest(text, totalArea){
    const response = await fetch('/api/save-text', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text, total_area_m2: totalArea })
    });

    if(!response.ok){
      const errorData = await response.json().catch(() => ({}));
      const message = errorData.error || `HTTP ${response.status}`;
      throw new Error(message);
    }

    return response.json();
  }

  function refreshImages(heroUrl, galleryUrl, version, heroVersion, galleryVersion){
    // Use individual versions if available, otherwise use common version or timestamp
    const heroCacheBuster = heroVersion ? `?v=${heroVersion}` : (version ? `?v=${version}` : `?t=${Date.now()}`);
    const galleryCacheBuster = galleryVersion ? `?v=${galleryVersion}` : (version ? `?v=${version}` : `?t=${Date.now()}`);
    
    const heroImg = document.querySelector('#proposal1 img');
    if(heroImg){
      heroImg.src = `${heroUrl}${heroCacheBuster}`;
    }

    const galleryImg = document.querySelector('#galleryBar img');
    if(galleryImg){
      galleryImg.src = `${galleryUrl}${galleryCacheBuster}`;
    }
  }

  function startJobPolling(jobId){
    activeJobId = jobId;
    clearPollTimer();
    const startTime = Date.now();
    displayedProgress = 0;
    targetProgress = 0;
    stopProgressTimer();

    const poll = async () => {
      if(activeJobId !== jobId) return;

      try{
        const response = await fetch(`/api/job-status/${jobId}?t=${Date.now()}`, { cache: 'no-store' });
        if(!response.ok){
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();

        if(data.status === 'pending'){
          if(Date.now() - startTime > POLL_TIMEOUT_MS){
            throw new Error('Timed out while waiting for the result.');
          }
          setStatus('Processing...', 'info');
          // Base message reflects current server hint; animation will update message live
          progressBaseMessage = 'Generating floorplans...';
          if(data.progress_message){
            progressBaseMessage += ` — ${data.progress_message}`;
          }
          if(typeof data.progress_percent === 'number'){
            // Animate each milestone to complete within ~3s
            animateProgressTo(data.progress_percent, 3000);
          }else{
            updateLoadingMessage(progressBaseMessage);
          }
          pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
          return;
        }

        if(data.status === 'failed'){
          const errorMessage = data.error && data.error.toLowerCase().includes('area') 
            ? 'Try again with a different number of rooms or a different shape' 
            : (data.error || 'Job processing failed.');
          throw new Error(errorMessage);
        }

        if(data.status === 'completed'){
          refreshImages(data.hero_image_url, data.gallery_image_url, data.version, data.hero_version, data.gallery_version);
          queueAreaPlan(data.total_area_m2);
          setStatus('Done! Images have been refreshed.', 'success');
          if(heroImg){
            delete heroImg.dataset.previousSrc;
            delete heroImg.dataset.landPreviewSrc;
          }
          // Fast-finish to 100% before hiding overlay
          progressBaseMessage = 'Finalizing...';
          const finalize = () => {
            hideLoadingOverlay();
            generateBtn.disabled = false;
          };
          if(displayedProgress < 100){
            animateProgressTo(100, 600, finalize);
          } else {
            stopProgressTimer();
            finalize();
          }
          return;
        }

        throw new Error('Unknown job status.');
      }catch(err){
        console.error(err);
        let errorMessage = err.message || 'An error occurred';
        
        // Handle specific error messages
        if (errorMessage.includes('Area not found') || errorMessage.includes('area') || errorMessage.includes('Area')) {
          errorMessage = 'Try again with a different number of rooms or a different shape';
        }
        
        setStatus(`Error: ${errorMessage}`, 'error');
        if(heroImg && heroImg.dataset.previousSrc){
          heroImg.src = heroImg.dataset.previousSrc;
          delete heroImg.dataset.previousSrc;
          delete heroImg.dataset.landPreviewSrc;
        }
        stopProgressTimer();
        hideLoadingOverlay();
        generateBtn.disabled = false;
      }
    };

    poll();
  }

  if(floorEl){
    floorEl.addEventListener('click', event => {
      const btn = event.target.closest('.btn-toggle');
      if(!btn) return;
      const floor = Number(btn.dataset.floor || state.floor);
      state.floor = floor;
      syncFloorButtons();
      showFloorSection(state.floor);
    });
  }

  if(totalAreaInput){
    totalAreaInput.addEventListener('input', () => {
      const parsed = Number(totalAreaInput.value);
      state.totalArea = Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
    });
  }

  registerFloorControls();
  syncAll();
  initSketchCanvas();
  loadLatestLandInfo();

  if(generateBtn){
    generateBtn.addEventListener('click', async () => {
      const description = buildRoomDescription();
      const totalArea = state.totalArea || 100;

      updateAreaPlanDisplay(null);

      try{
        generateBtn.disabled = true;
        setStatus('Submitting request...', 'info');
        if(heroImg){
          heroImg.dataset.previousSrc = heroImg.src;
          const previewSrc = captureLandPreviewDataUrl();
          if(previewSrc){
            heroImg.dataset.landPreviewSrc = previewSrc;
            heroImg.src = previewSrc;
          }
        }
        showLoadingOverlay('Submitting request...');
        const data = await saveRequest(description, totalArea);
        setStatus('Request submitted. Waiting for the result...', 'info');
        updateLoadingMessage('Waiting for the prediction...');
        startJobPolling(data.job_id);
      }catch(err){
        console.error(err);
        setStatus('Unable to submit request: ' + err.message, 'error');
        if(heroImg && heroImg.dataset.previousSrc){
          heroImg.src = heroImg.dataset.previousSrc;
          delete heroImg.dataset.previousSrc;
          delete heroImg.dataset.landPreviewSrc;
        }
        hideLoadingOverlay();
        generateBtn.disabled = false;
      }
    });
  }
})();

// Fade in proposals
window.addEventListener('load', () => {
  document.querySelectorAll('.proposal').forEach(el => el.classList.add('visible'));
});

// Gallery navigation
const galleryImages = Array.from(document.querySelectorAll('#galleryBar img'));
if(galleryImages.length){
  let currentIndex = 0;

  function updateGallery(){
    galleryImages.forEach((img, idx) => {
      img.classList.toggle('active', idx === currentIndex);
    });
  }

  const nextBtn = document.getElementById('next');
  const prevBtn = document.getElementById('prev');

  if(nextBtn){
    nextBtn.addEventListener('click', () => {
      currentIndex = (currentIndex + 1) % galleryImages.length;
      updateGallery();
    });
  }

  if(prevBtn){
    prevBtn.addEventListener('click', () => {
      currentIndex = (currentIndex - 1 + galleryImages.length) % galleryImages.length;
      updateGallery();
    });
  }

  galleryImages.forEach((img, idx) => {
    img.addEventListener('click', () => {
      currentIndex = idx;
      updateGallery();

      const proposalId = `proposal${idx + 1}`;
      const proposalElem = document.getElementById(proposalId);
      if(proposalElem){
        proposalElem.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  updateGallery();
}

// Close gallery bar
const closeGalleryBtn = document.getElementById('closeGallery');
if(closeGalleryBtn){
  closeGalleryBtn.addEventListener('click', () => {
    const galleryBar = document.getElementById('galleryBar');
    if(galleryBar){
      galleryBar.style.display = 'none';
    }
  });
}

// Land Setting Modal Functions
let headerHidden = false;
let galleryBarHidden = false;

function openLandModal() {
  document.getElementById('landModal').style.display = 'flex';
  updateLandGrid();

  // Hide header and gallery-bar
  const header = document.querySelector('.header');
  const galleryBar = document.getElementById('galleryBar');
  if (header) {
    header.style.display = 'none';
    headerHidden = true;
  }
  if (galleryBar) {
    galleryBar.style.display = 'none';
    galleryBarHidden = true;
  }
}

function closeLandModal() {
  document.getElementById('landModal').style.display = 'none';

  // Restore header and gallery-bar
  const header = document.querySelector('.header');
  const galleryBar = document.getElementById('galleryBar');
  if (headerHidden && header) {
    header.style.display = '';
  }
  if (galleryBarHidden && galleryBar) {
    galleryBar.style.display = '';
  }
  headerHidden = false;
  galleryBarHidden = false;
}

// Add click event to modal background to close when clicking outside
document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('landModal');
  if (modal) {
    modal.addEventListener('click', function(event) {
      if (event.target === modal) {
        closeLandModal();
      }
    });
  }
});

// Single Job Processing
async function processSingleJob() {
  const btn = document.querySelector('.single-job-btn');
  const originalText = btn.textContent;

  try {
    // Disable button and show processing state
    btn.disabled = true;
    btn.textContent = 'Processing...';
    btn.style.backgroundColor = '#666';

    // Show loading overlay
    showLoadingOverlay('Processing mask 14.png...');

    // Call the API endpoint
    const response = await fetch('/api/single-job', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    const data = await response.json();

    if (data.success) {
      setStatus('Single job completed successfully! Images have been updated.', 'success');
      updateLoadingMessage('Refreshing images...');

      // Refresh images
      const heroImg = document.querySelector('#proposal1 img');
      const galleryImg = document.querySelector('#galleryBar img.active');
      if (heroImg) {
        heroImg.src = `${heroImg.src.split('?')[0]}?t=${Date.now()}`;
      }
      if (galleryImg) {
        galleryImg.src = `${galleryImg.src.split('?')[0]}?t=${Date.now()}`;
      }

      setTimeout(() => {
        hideLoadingOverlay();
        alert('✅ Single job processing completed!\n\nGenerated files:\n' +
              '- Layout: 14.json\n' +
              '- Floorplan: 14_result.png\n' +
              '- Test outputs: 14_corrected.png, 14_improved.png\n\n' +
              'Images have been updated in the gallery.');
      }, 1000);

    } else {
      throw new Error(data.error || 'Processing failed');
    }

  } catch (error) {
    console.error('Single job error:', error);
    setStatus(`Error: ${error.message}`, 'error');
    hideLoadingOverlay();

    alert(`❌ Single job processing failed:\n\n${error.message}`);

  } finally {
    // Restore button state
    btn.disabled = false;
    btn.textContent = originalText;
    btn.style.backgroundColor = '';
  }
}

function updateArea() {
  const vertical = parseInt(document.getElementById('vertical').value) || 10;
  const yoko = parseInt(document.getElementById('yoko').value) || 10;
  const area = vertical * yoko;
  document.getElementById('area').textContent = area;
  updateLandGrid(vertical, yoko);
}

function updateLandGrid(newVertical, newYoko) {
  const vertical = newVertical || parseInt(document.getElementById('vertical').value) || 10;
  const yoko = newYoko || parseInt(document.getElementById('yoko').value) || 10;
  const grid = document.getElementById('landGrid');

  // Store current cell states before rebuilding
  const currentCells = Array.from(grid.children);
  const currentStates = currentCells.map(cell => ({
    isOffSite: cell.classList.contains('off-site'),
    backgroundColor: cell.style.backgroundColor
  }));

  // Always rebuild grid (simpler and more reliable)
  grid.innerHTML = '';
  grid.style.gridTemplateColumns = `repeat(${yoko}, 25px)`;
  grid.style.gridTemplateRows = `repeat(${vertical}, 25px)`;

  for (let i = 0; i < vertical * yoko; i++) {
    const cell = document.createElement('div');
    cell.addEventListener('click', () => {
      cell.classList.toggle('off-site');
      if (cell.classList.contains('off-site')) {
        // CSS will handle the Unicode X and white background
        cell.style.backgroundColor = '';
      } else {
        // Remove icon and set default color
        cell.style.backgroundColor = '#fef3c7';
      }
    });

    // Restore state if available, otherwise use default
    if (currentStates[i]) {
      if (currentStates[i].isOffSite) {
        cell.classList.add('off-site');
        // CSS will handle the Unicode X and white background
        cell.style.backgroundColor = '';
      } else {
        cell.style.backgroundColor = currentStates[i].backgroundColor || '#fef3c7';
      }
    } else {
      // Default state for new cells
      cell.style.backgroundColor = '#fef3c7';
    }

    grid.appendChild(cell);
  }
}

function saveLandSettings() {
  const vertical = parseInt(document.getElementById('vertical').value);
  const yoko = parseInt(document.getElementById('yoko').value);
  const grid = document.getElementById('landGrid');
  const cells = Array.from(grid.children);

  // Build 2D grid array
  const gridData = [];
  for (let i = 0; i < vertical; i++) {
    const row = [];
    for (let j = 0; j < yoko; j++) {
      const cell = cells[i * yoko + j];
      row.push(cell.classList.contains('off-site') ? 0 : 1);
    }
    gridData.push(row);
  }

  const data = {
    length: vertical,
    width: yoko,
    grid: gridData
  };

  fetch('/api/save-land-settings', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })
    .then(response => {
      if(!response.ok){
        return response.json().then(err => {
          const message = err && err.error ? err.error : `HTTP ${response.status}`;
          throw new Error(message);
        }).catch(() => {
          throw new Error(`HTTP ${response.status}`);
        });
      }
      return response.json();
    })
    .then(() => {
      closeLandModal();
    })
    .catch(err => {
      console.error('Failed to save land settings:', err);
      alert(`Unable to save land settings: ${err.message}`);
    });
}
