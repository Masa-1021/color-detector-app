/**
 * Circle Detector - Frontend Logic
 */

// =============================================================================
// State
// =============================================================================
const state = {
  mode: 'edit',           // 'edit' | 'run'
  interactionMode: 'normal', // 'normal' | 'adding_circle' | 'dragging' | 'eyedropper' | 'moving' | 'resizing'
  circles: [],
  groups: [],
  rules: [],
  selectedCircleId: null,
  dragStart: null,
  currentRadius: 0,
  config: {},
  statusPollTimer: null,
  // Rule editing
  editingRuleGroupId: null,
  editingRuleId: null,     // null = new rule
  // Move/resize
  moveOriginal: null,      // { center_x, center_y, radius } before drag
  // Color editing
  editingColorName: null,  // null = new color, string = editing existing
};

// =============================================================================
// Initialization
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
  setupCanvas();
  loadConfig();
  startVideoFeed();
});

function startVideoFeed() {
  const img = document.getElementById('video-feed');
  img.src = '/video_feed?' + Date.now();
  img.onerror = () => {
    setTimeout(() => { img.src = '/video_feed?' + Date.now(); }, 2000);
  };
  img.onload = () => { resizeCanvas(); };
}

function setupCanvas() {
  const canvas = document.getElementById('overlay-canvas');
  canvas.addEventListener('mousedown', onCanvasMouseDown);
  canvas.addEventListener('mousemove', onCanvasMouseMove);
  canvas.addEventListener('mouseup', onCanvasMouseUp);
  canvas.addEventListener('touchstart', onCanvasTouchStart, { passive: false });
  canvas.addEventListener('touchmove', onCanvasTouchMove, { passive: false });
  canvas.addEventListener('touchend', onCanvasTouchEnd);
  window.addEventListener('resize', resizeCanvas);
}

function resizeCanvas() {
  const img = document.getElementById('video-feed');
  const canvas = document.getElementById('overlay-canvas');
  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;
  redrawCanvas();
}

// =============================================================================
// API Helpers
// =============================================================================
async function api(method, url, data = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (data) opts.body = JSON.stringify(data);
  const res = await fetch(url, opts);
  return res.json();
}

// =============================================================================
// Config Loading
// =============================================================================
async function loadConfig() {
  try {
    const data = await api('GET', '/api/config');
    state.config = data;
    state.circles = data.circles || [];
    state.groups = data.groups || [];
    state.rules = data.rules || [];

    // STA_NO1 options
    const select = document.getElementById('sta-no1-select');
    select.innerHTML = '';
    const options = (data.station && data.station.sta_no1_options) || ['PLANT01'];
    const current = (data.station && data.station.sta_no1) || options[0];
    options.forEach(opt => {
      const o = document.createElement('option');
      o.value = opt; o.textContent = opt;
      if (opt === current) o.selected = true;
      select.appendChild(o);
    });

    // Send mode
    const sendMode = (data.detection && data.detection.send_mode) || 'on_change';
    document.getElementById('send-mode-select').value = sendMode;

    // MQTT settings
    const mqttConf = data.mqtt || {};
    document.getElementById('mqtt-broker-input').value = mqttConf.broker || 'localhost';
    document.getElementById('mqtt-port-input').value = mqttConf.port || 1883;
    document.getElementById('mqtt-topic-input').value = mqttConf.topic || 'equipment/status';

    // NTP settings
    const ntpConf = data.ntp || {};
    document.getElementById('ntp-server-input').value = ntpConf.server || 'ntp.nict.jp';
    document.getElementById('ntp-interval-input').value = ntpConf.interval_sec || 3600;

    renderGroups();
    renderCircleEditor();
    redrawCanvas();
    refreshMqttStatus();
  } catch (e) {
    showToast('設定の読み込みに失敗しました', 'error');
  }
}

async function saveConfig() {
  await api('POST', '/api/config');
  showToast('設定を保存しました', 'success');
}

function onStaNo1Change(value) {
  api('PUT', '/api/sta_no1', { sta_no1: value });
}
function onSendModeChange(value) {
  // Update local state; will be saved with saveConfig
  if (!state.config.detection) state.config.detection = {};
  state.config.detection.send_mode = value;
}

// =============================================================================
// MQTT Operations
// =============================================================================
function onMqttConfigChange() {
  const broker = document.getElementById('mqtt-broker-input').value.trim();
  const port = parseInt(document.getElementById('mqtt-port-input').value) || 1883;
  const topic = document.getElementById('mqtt-topic-input').value.trim();
  api('PUT', '/api/mqtt', { broker, port, topic });
}

async function mqttConnect() {
  const btn = document.getElementById('btn-mqtt-connect');
  btn.disabled = true;
  btn.textContent = '接続中...';

  // Save config first
  onMqttConfigChange();

  try {
    const result = await api('POST', '/api/mqtt/connect');
    if (result.connected) {
      showToast('MQTT接続しました', 'success');
    } else {
      showToast('MQTT接続に失敗しました。ブローカーを確認してください', 'error');
    }
  } catch (e) {
    showToast('MQTT接続エラー', 'error');
  }

  btn.disabled = false;
  btn.textContent = '接続';
  refreshMqttStatus();
}

async function mqttDisconnect() {
  await api('POST', '/api/mqtt/disconnect');
  showToast('MQTT切断しました', 'success');
  refreshMqttStatus();
}

async function refreshMqttStatus() {
  try {
    const data = await api('GET', '/api/mqtt');
    const connected = data.connected;

    // Header badge
    const badge = document.getElementById('mqtt-badge');
    badge.className = connected ? 'badge badge-success' : 'badge badge-error';
    badge.textContent = connected ? 'MQTT: 接続中' : 'MQTT: 未接続';

    // Detail status
    const detail = document.getElementById('mqtt-detail-status');
    detail.className = connected ? 'badge badge-success' : 'badge badge-error';
    detail.textContent = connected ? '接続中' : '未接続';

    // Connect/disconnect buttons
    document.getElementById('btn-mqtt-connect').classList.toggle('hidden', connected);
    document.getElementById('btn-mqtt-disconnect').classList.toggle('hidden', !connected);
  } catch (e) {
    // ignore
  }

  // ブリッジ（Oracle DB）+ NTP ステータスも取得
  refreshBridgeStatus();
  refreshNtpStatus();
}

async function refreshBridgeStatus() {
  try {
    const data = await api('GET', '/api/bridge/status');
    const bridgeRunning = data.running;
    const oracleOk = data.oracle_connected;

    // Header Oracle badge
    const badge = document.getElementById('oracle-badge');
    if (bridgeRunning && oracleOk) {
      badge.className = 'badge badge-success';
      badge.textContent = 'DB: 接続中';
    } else if (bridgeRunning) {
      badge.className = 'badge badge-warning';
      badge.textContent = 'DB: 切断';
    } else {
      badge.className = 'badge badge-error';
      badge.textContent = 'DB: 停止';
    }

    // Detail badges
    const bridgeBadge = document.getElementById('bridge-detail-status');
    bridgeBadge.className = bridgeRunning ? 'badge badge-success' : 'badge badge-error';
    bridgeBadge.textContent = bridgeRunning ? 'ブリッジ稼働中' : 'ブリッジ停止';

    const oracleBadge = document.getElementById('oracle-detail-status');
    oracleBadge.className = oracleOk ? 'badge badge-success' : 'badge badge-error';
    oracleBadge.textContent = oracleOk ? 'DB接続中' : 'DB未接続';

    // Stats
    const statsEl = document.getElementById('bridge-stats');
    if (bridgeRunning) {
      statsEl.textContent = `受信:${data.received} 保存:${data.inserted} エラー:${data.errors} キュー:${data.pending}`;
    } else {
      statsEl.textContent = '';
    }
  } catch (e) {
    // ignore
  }
}

// =============================================================================
// NTP Operations
// =============================================================================
function onNtpConfigChange() {
  const server = document.getElementById('ntp-server-input').value.trim();
  const interval = parseInt(document.getElementById('ntp-interval-input').value) || 3600;
  api('PUT', '/api/ntp', { server, interval_sec: interval });
}

async function ntpStart() {
  onNtpConfigChange();
  await api('POST', '/api/ntp/start');
  showToast('NTP同期を有効化しました', 'success');
  refreshNtpStatus();
}

async function ntpStop() {
  await api('POST', '/api/ntp/stop');
  showToast('NTP同期を無効化しました', 'success');
  refreshNtpStatus();
}

async function ntpSyncNow() {
  showToast('NTP同期中...', 'info');
  onNtpConfigChange();
  const result = await api('POST', '/api/ntp/sync');
  if (result.success) {
    const msg = result.adjusted
      ? `同期完了 (オフセット: ${result.offset}s, 時刻補正済み)`
      : `同期完了 (オフセット: ${result.offset}s)`;
    showToast(msg, 'success');
  } else {
    showToast(`NTP同期失敗: ${result.error}`, 'error');
  }
  refreshNtpStatus();
}

async function refreshNtpStatus() {
  try {
    const data = await api('GET', '/api/ntp');
    const running = data.running;

    const badge = document.getElementById('ntp-detail-status');
    badge.className = running ? 'badge badge-success' : 'badge badge-error';
    badge.textContent = running ? '同期中' : '停止';

    document.getElementById('btn-ntp-start').classList.toggle('hidden', running);
    document.getElementById('btn-ntp-stop').classList.toggle('hidden', !running);

    const statsEl = document.getElementById('ntp-stats');
    if (data.last_sync) {
      const t = new Date(data.last_sync).toLocaleTimeString('ja-JP');
      const offset = data.last_offset !== null ? `${data.last_offset > 0 ? '+' : ''}${data.last_offset}s` : '-';
      statsEl.textContent = `最終同期: ${t} | オフセット: ${offset} | 回数: ${data.sync_count}`;
    } else if (data.last_error) {
      statsEl.textContent = `エラー: ${data.last_error}`;
    } else {
      statsEl.textContent = '';
    }
  } catch (e) {
    // ignore
  }
}

// =============================================================================
// Canvas Drawing
// =============================================================================
function getCanvasScale() {
  const img = document.getElementById('video-feed');
  const cw = (state.config.camera && state.config.camera.width) || 640;
  const ch = (state.config.camera && state.config.camera.height) || 480;
  return { sx: img.clientWidth / cw, sy: img.clientHeight / ch };
}

function canvasToCamera(cx, cy) {
  const s = getCanvasScale();
  return { x: Math.round(cx / s.sx), y: Math.round(cy / s.sy) };
}

function cameraToCanvas(x, y) {
  const s = getCanvasScale();
  return { cx: x * s.sx, cy: y * s.sy };
}

function redrawCanvas() {
  const canvas = document.getElementById('overlay-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  state.circles.forEach(circle => {
    const { cx, cy } = cameraToCanvas(circle.center_x, circle.center_y);
    const s = getCanvasScale();
    const r = circle.radius * s.sx;
    const selected = circle.id === state.selectedCircleId;

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.strokeStyle = selected ? '#00ff00' : '#ffffff';
    ctx.lineWidth = selected ? 3 : 2;
    ctx.stroke();

    // Fill with transparent color
    ctx.fillStyle = selected ? 'rgba(0,255,0,0.1)' : 'rgba(255,255,255,0.05)';
    ctx.fill();

    // Resize zone indicator for selected circle (dashed inner ring at 70%)
    if (selected && state.mode === 'edit') {
      ctx.beginPath();
      ctx.arc(cx, cy, r * 0.7, 0, 2 * Math.PI);
      ctx.strokeStyle = 'rgba(0,255,0,0.3)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Small handle dots at cardinal points
      const handleR = 4;
      [[cx + r, cy], [cx - r, cy], [cx, cy - r], [cx, cy + r]].forEach(([hx, hy]) => {
        ctx.beginPath();
        ctx.arc(hx, hy, handleR, 0, 2 * Math.PI);
        ctx.fillStyle = '#00ff00';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.stroke();
      });
    }

    // Label
    ctx.fillStyle = '#ffffff';
    ctx.font = `${Math.max(11, 12 * s.sx)}px sans-serif`;
    ctx.shadowColor = 'rgba(0,0,0,0.8)';
    ctx.shadowBlur = 3;
    ctx.fillText(circle.name || `円${circle.id}`, cx - r, cy - r - 4);
    ctx.shadowBlur = 0;
  });

  // Drawing preview
  if (state.interactionMode === 'dragging' && state.dragStart) {
    const ctx2 = canvas.getContext('2d');
    ctx2.beginPath();
    ctx2.arc(state.dragStart.cx, state.dragStart.cy, state.currentRadius, 0, 2 * Math.PI);
    ctx2.strokeStyle = '#ffff00';
    ctx2.lineWidth = 2;
    ctx2.setLineDash([5, 5]);
    ctx2.stroke();
    ctx2.setLineDash([]);
  }
}

// =============================================================================
// Canvas Interaction
// =============================================================================
function getMousePos(e) {
  const canvas = document.getElementById('overlay-canvas');
  const rect = canvas.getBoundingClientRect();
  return { cx: e.clientX - rect.left, cy: e.clientY - rect.top };
}

function getTouchPos(e) {
  const canvas = document.getElementById('overlay-canvas');
  const rect = canvas.getBoundingClientRect();
  const touch = e.touches[0] || e.changedTouches[0];
  return { cx: touch.clientX - rect.left, cy: touch.clientY - rect.top };
}

function onCanvasMouseDown(e) { handlePointerDown(getMousePos(e)); }
function onCanvasMouseMove(e) { handlePointerMove(getMousePos(e)); }
function onCanvasMouseUp(e) { handlePointerUp(getMousePos(e)); }

function onCanvasTouchStart(e) { e.preventDefault(); handlePointerDown(getTouchPos(e)); }
function onCanvasTouchMove(e) { e.preventDefault(); handlePointerMove(getTouchPos(e)); }
function onCanvasTouchEnd(e) { e.preventDefault(); handlePointerUp(getTouchPos(e)); }

function handlePointerDown(pos) {
  if (state.mode !== 'edit') return;

  if (state.interactionMode === 'adding_circle') {
    state.interactionMode = 'dragging';
    state.dragStart = pos;
    state.currentRadius = 0;
    return;
  }

  if (state.interactionMode === 'eyedropper') {
    pickColorAt(pos);
    return;
  }

  // Check if clicking on an existing circle
  const hit = hitTestCircle(pos);

  if (hit) {
    selectCircle(hit.circle.id);

    if (hit.zone === 'edge') {
      // Start resizing
      state.interactionMode = 'resizing';
      state.dragStart = pos;
      state.moveOriginal = {
        center_x: hit.circle.center_x,
        center_y: hit.circle.center_y,
        radius: hit.circle.radius
      };
    } else {
      // Start moving
      state.interactionMode = 'moving';
      state.dragStart = pos;
      state.moveOriginal = {
        center_x: hit.circle.center_x,
        center_y: hit.circle.center_y,
        radius: hit.circle.radius
      };
    }
  } else {
    selectCircle(null);
  }
}

function handlePointerMove(pos) {
  const canvas = document.getElementById('overlay-canvas');

  if (state.interactionMode === 'dragging' && state.dragStart) {
    const dx = pos.cx - state.dragStart.cx;
    const dy = pos.cy - state.dragStart.cy;
    state.currentRadius = Math.sqrt(dx * dx + dy * dy);
    redrawCanvas();
    return;
  }

  if (state.interactionMode === 'moving' && state.dragStart) {
    const circle = state.circles.find(c => c.id === state.selectedCircleId);
    if (circle) {
      const s = getCanvasScale();
      const dx = pos.cx - state.dragStart.cx;
      const dy = pos.cy - state.dragStart.cy;
      circle.center_x = state.moveOriginal.center_x + Math.round(dx / s.sx);
      circle.center_y = state.moveOriginal.center_y + Math.round(dy / s.sy);
      redrawCanvas();
    }
    return;
  }

  if (state.interactionMode === 'resizing' && state.dragStart) {
    const circle = state.circles.find(c => c.id === state.selectedCircleId);
    if (circle) {
      const { cx, cy } = cameraToCanvas(circle.center_x, circle.center_y);
      const s = getCanvasScale();
      const dx = pos.cx - cx;
      const dy = pos.cy - cy;
      const newRadius = Math.max(5, Math.round(Math.sqrt(dx * dx + dy * dy) / s.sx));
      circle.radius = newRadius;
      redrawCanvas();
    }
    return;
  }

  // Hover cursor: show move/resize hints for selected circle
  if (state.mode === 'edit' && state.interactionMode === 'normal') {
    const hit = hitTestCircle(pos);
    if (hit) {
      canvas.style.cursor = hit.zone === 'edge' ? 'nwse-resize' : 'move';
    } else {
      canvas.style.cursor = '';
    }
  }
}

async function handlePointerUp(pos) {
  // New circle creation
  if (state.interactionMode === 'dragging' && state.dragStart) {
    const s = getCanvasScale();
    const camRadius = Math.round(state.currentRadius / s.sx);

    if (camRadius >= 5) {
      const camPos = canvasToCamera(state.dragStart.cx, state.dragStart.cy);
      const result = await api('POST', '/api/circles', {
        center_x: camPos.x,
        center_y: camPos.y,
        radius: camRadius
      });
      if (result.success) {
        state.circles.push(result.circle);
        selectCircle(result.id);
        showToast('円を追加しました', 'success');
      }
    }

    state.interactionMode = 'normal';
    state.dragStart = null;
    state.currentRadius = 0;
    document.getElementById('video-container').classList.remove('adding-circle');
    redrawCanvas();
    return;
  }

  // Move complete
  if (state.interactionMode === 'moving' && state.dragStart) {
    const circle = state.circles.find(c => c.id === state.selectedCircleId);
    if (circle && state.moveOriginal) {
      const moved = circle.center_x !== state.moveOriginal.center_x ||
                    circle.center_y !== state.moveOriginal.center_y;
      if (moved) {
        await api('PUT', `/api/circles/${circle.id}`, {
          center_x: circle.center_x,
          center_y: circle.center_y
        });
        renderCircleEditor();
      }
    }
    state.interactionMode = 'normal';
    state.dragStart = null;
    state.moveOriginal = null;
    return;
  }

  // Resize complete
  if (state.interactionMode === 'resizing' && state.dragStart) {
    const circle = state.circles.find(c => c.id === state.selectedCircleId);
    if (circle && state.moveOriginal) {
      if (circle.radius !== state.moveOriginal.radius) {
        await api('PUT', `/api/circles/${circle.id}`, {
          radius: circle.radius
        });
        renderCircleEditor();
      }
    }
    state.interactionMode = 'normal';
    state.dragStart = null;
    state.moveOriginal = null;
    return;
  }
}

/**
 * Hit-test: returns { circle, zone: 'center'|'edge' } or null.
 * 'edge' = within outer 30% of radius (for resize).
 */
function hitTestCircle(pos) {
  const cam = canvasToCamera(pos.cx, pos.cy);
  for (let i = state.circles.length - 1; i >= 0; i--) {
    const c = state.circles[i];
    const dx = cam.x - c.center_x;
    const dy = cam.y - c.center_y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist <= c.radius) {
      const zone = dist >= c.radius * 0.7 ? 'edge' : 'center';
      return { circle: c, zone };
    }
  }
  return null;
}


// =============================================================================
// Circle Operations
// =============================================================================
function startAddCircle() {
  state.interactionMode = 'adding_circle';
  document.getElementById('video-container').classList.add('adding-circle');
  showToast('映像上でドラッグして円を作成', 'info');
}

function selectCircle(circleId) {
  state.selectedCircleId = circleId;
  renderCircleEditor();
  redrawCanvas();

  // Update circle tab badge
  const badge = document.getElementById('circle-tab-badge');
  if (badge) {
    if (circleId) {
      const circle = state.circles.find(c => c.id === circleId);
      badge.textContent = circle ? circle.name || `円${circleId}` : '';
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }

  // Auto-switch to circle settings tab when a circle is selected
  if (circleId && state.mode === 'edit') {
    showSettingsTab('tab-circle');
  }
}

async function deleteSelectedCircle() {
  if (!state.selectedCircleId) return;
  await api('DELETE', `/api/circles/${state.selectedCircleId}`);
  state.circles = state.circles.filter(c => c.id !== state.selectedCircleId);
  selectCircle(null);
  renderGroups();
  showToast('円を削除しました', 'success');
}

function renderCircleEditor() {
  const el = document.getElementById('circle-editor-content');
  const circle = state.circles.find(c => c.id === state.selectedCircleId);

  if (!circle) {
    el.innerHTML = `
      <div class="empty-state">映像上の円をクリックして選択<br><small>または下のボタンで新規作成</small></div>
      <div class="flex justify-center mt-4">
        <button class="btn btn-primary btn-sm" onclick="startAddCircle()">+ 円追加</button>
      </div>
    `;
    return;
  }

  const groupOptions = state.groups.map(g =>
    `<option value="${g.id}" ${circle.group_id === g.id ? 'selected' : ''}>${g.name}</option>`
  ).join('');

  const colors = (circle.colors || []).map(c => `
    <div class="color-item" onclick="editColor(${circle.id},'${c.name}')" style="cursor:pointer">
      <div class="color-swatch" style="background:hsl(${c.h_center * 2},${Math.round(c.s_max/2.55)}%,${Math.round(c.v_max/2.55)}%)"></div>
      <span class="color-item-name">${c.name}</span>
      <span class="color-item-info">H:${c.h_center} &plusmn;${c.h_range}</span>
      <span class="color-item-delete" onclick="event.stopPropagation();removeColor(${circle.id},'${c.name}')">&times;</span>
    </div>
  `).join('');

  el.innerHTML = `
    <div class="circle-editor">
      <div class="circle-info-row">
        <label>ID</label>
        <span>${circle.id}</span>
      </div>
      <div class="circle-info-row">
        <label>名前</label>
        <input class="form-input" value="${circle.name || ''}" style="flex:1"
               onchange="updateCircle(${circle.id},{name:this.value})">
      </div>
      <div class="circle-info-row">
        <label>位置</label>
        <span style="font-size:var(--sd-font-size-xs);color:var(--sd-color-text-secondary)">
          (${circle.center_x}, ${circle.center_y}) r=${circle.radius}
        </span>
      </div>
      <div class="circle-info-row">
        <label>グループ</label>
        <select class="form-select" style="flex:1"
                onchange="assignCircleToGroup(${circle.id}, parseInt(this.value))">
          <option value="0">未設定</option>
          ${groupOptions}
        </select>
      </div>
      <div class="section-title mt-4">登録色</div>
      <div class="color-list">${colors || '<div class="empty-state">色なし</div>'}</div>
      <div class="flex gap-2 mt-2 flex-wrap">
        <button class="btn btn-primary btn-sm" onclick="addColorFromCenter(${circle.id})">中心色を取得</button>
        <button class="btn btn-secondary btn-sm" onclick="openColorModal(${circle.id})">カラーパレット</button>
      </div>
      <hr style="margin:var(--sd-spacing-4) 0;border:none;border-top:1px solid var(--sd-color-border);">
      <div class="flex gap-2 justify-between">
        <button class="btn btn-primary btn-sm" onclick="startAddCircle()">+ 円追加</button>
        <button class="btn btn-danger btn-sm" onclick="deleteSelectedCircle()">この円を削除</button>
      </div>
    </div>
  `;
}

async function updateCircle(id, data) {
  const result = await api('PUT', `/api/circles/${id}`, data);
  if (result.success) {
    const idx = state.circles.findIndex(c => c.id === id);
    if (idx >= 0) Object.assign(state.circles[idx], result.circle);
    redrawCanvas();
  }
}

async function assignCircleToGroup(circleId, groupId) {
  const circle = state.circles.find(c => c.id === circleId);
  if (!circle) return;

  // Remove from old group
  if (circle.group_id) {
    await api('DELETE', `/api/groups/${circle.group_id}/circles/${circleId}`);
  }

  // Add to new group
  if (groupId > 0) {
    await api('POST', `/api/groups/${groupId}/circles/${circleId}`);
  }

  circle.group_id = groupId > 0 ? groupId : null;
  await loadConfig(); // Refresh all
}

// =============================================================================
// Color Operations
// =============================================================================
async function addColorFromCenter(circleId) {
  const circle = state.circles.find(c => c.id === circleId);
  if (!circle) return;

  const result = await api('GET', `/api/color/${circle.center_x}/${circle.center_y}`);

  state.selectedCircleId = circleId;
  state.editingColorName = null;
  document.querySelector('#color-modal .modal-header h3').textContent = '中心色から追加';
  document.getElementById('color-name-input').value = result.suggested_name || '';
  document.getElementById('color-name-input').readOnly = false;
  document.getElementById('h-slider').value = result.hsv[0];
  document.getElementById('hr-slider').value = 10;
  document.getElementById('s-center').value = result.hsv[1];
  document.getElementById('sat-slider').value = result.hsv[1];
  document.getElementById('v-center').value = result.hsv[2];
  document.getElementById('sr-slider').value = 50;
  document.getElementById('vr-slider').value = 50;
  paletteCache.sat = -1;
  updateColorPreview();
  document.getElementById('color-modal-backdrop').classList.add('active');
}

function startEyedropper() {
  if (!state.selectedCircleId) return;
  state.interactionMode = 'eyedropper';
  document.getElementById('video-container').style.cursor = 'crosshair';
  showToast('映像上でクリックして色を取得', 'info');
}

async function pickColorAt(pos) {
  const cam = canvasToCamera(pos.cx, pos.cy);
  const result = await api('GET', `/api/color/${cam.x}/${cam.y}`);

  state.interactionMode = 'normal';
  state.editingColorName = null;
  document.getElementById('video-container').style.cursor = '';

  // Open color modal with picked values
  document.querySelector('#color-modal .modal-header h3').textContent = '色の追加';
  document.getElementById('color-name-input').value = result.suggested_name || '';
  document.getElementById('color-name-input').readOnly = false;
  document.getElementById('h-slider').value = result.hsv[0];
  document.getElementById('hr-slider').value = 10;
  document.getElementById('s-center').value = result.hsv[1];
  document.getElementById('sat-slider').value = result.hsv[1];
  document.getElementById('v-center').value = result.hsv[2];
  document.getElementById('sr-slider').value = 50;
  document.getElementById('vr-slider').value = 50;
  paletteCache.sat = -1;
  updateColorPreview();

  document.getElementById('color-modal-backdrop').classList.add('active');
}

function openColorModal(circleId) {
  state.selectedCircleId = circleId;
  state.editingColorName = null;
  document.querySelector('#color-modal .modal-header h3').textContent = '色の追加';
  document.getElementById('color-name-input').value = '';
  document.getElementById('color-name-input').readOnly = false;
  document.getElementById('h-slider').value = 0;
  document.getElementById('hr-slider').value = 10;
  document.getElementById('s-center').value = 200;
  document.getElementById('sat-slider').value = 200;
  document.getElementById('v-center').value = 200;
  document.getElementById('vr-slider').value = 50;
  document.getElementById('sr-slider').value = 50;
  paletteCache.sat = -1; // force redraw
  updateColorPreview();
  document.getElementById('color-modal-backdrop').classList.add('active');
}

function editColor(circleId, colorName) {
  const circle = state.circles.find(c => c.id === circleId);
  if (!circle) return;
  const color = (circle.colors || []).find(c => c.name === colorName);
  if (!color) return;

  state.selectedCircleId = circleId;
  state.editingColorName = colorName;
  document.querySelector('#color-modal .modal-header h3').textContent = `色の編集 - ${colorName}`;
  document.getElementById('color-name-input').value = color.name;
  document.getElementById('color-name-input').readOnly = false;
  document.getElementById('h-slider').value = color.h_center;
  document.getElementById('hr-slider').value = color.h_range;
  const sMid = Math.round((color.s_min + color.s_max) / 2);
  const vMid = Math.round((color.v_min + color.v_max) / 2);
  const sr = Math.round((color.s_max - color.s_min) / 2);
  const vr = Math.round((color.v_max - color.v_min) / 2);
  document.getElementById('s-center').value = sMid;
  document.getElementById('sat-slider').value = sMid;
  document.getElementById('v-center').value = vMid;
  document.getElementById('sr-slider').value = sr || 50;
  document.getElementById('vr-slider').value = vr || 50;
  paletteCache.sat = -1;
  updateColorPreview();
  document.getElementById('color-modal-backdrop').classList.add('active');
}

function closeColorModal() {
  document.getElementById('color-modal-backdrop').classList.remove('active');
}

// =============================================================================
// Visual Color Picker (Hue×Value palette + Saturation slider)
// =============================================================================
let pickerInitialized = false;

function hsvToRgb(h, s, v) {
  const hh = (h * 2) / 360;
  const ss = s / 255;
  const vv = v / 255;
  const i = Math.floor(hh * 6);
  const f = hh * 6 - i;
  const p = vv * (1 - ss);
  const q = vv * (1 - f * ss);
  const t = vv * (1 - (1 - f) * ss);
  let r, g, b;
  switch (i % 6) {
    case 0: r = vv; g = t; b = p; break;
    case 1: r = q; g = vv; b = p; break;
    case 2: r = p; g = vv; b = t; break;
    case 3: r = p; g = q; b = vv; break;
    case 4: r = t; g = p; b = vv; break;
    case 5: r = vv; g = p; b = q; break;
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

// Cache for palette imageData (avoids recalculating 360x256 on every click)
let paletteCache = { sat: -1, imageData: null };

function initPickerCanvases() {
  if (pickerInitialized) return;
  const canvas = document.getElementById('palette-canvas');
  if (!canvas) return;

  const handler = (e) => {
    const rect = canvas.getBoundingClientRect();
    const cx = (e.clientX || e.touches[0].clientX) - rect.left;
    const cy = (e.clientY || e.touches[0].clientY) - rect.top;
    const h = Math.round((cx / rect.width) * 179);
    const v = Math.round((1 - cy / rect.height) * 255);
    document.getElementById('h-slider').value = Math.max(0, Math.min(179, h));
    document.getElementById('v-center').value = Math.max(0, Math.min(255, v));
    syncRangesFromCenter();
    updateColorPreview();
  };

  canvas.addEventListener('mousedown', (e) => { handler(e); canvas._drag = true; });
  canvas.addEventListener('mousemove', (e) => { if (canvas._drag) handler(e); });
  window.addEventListener('mouseup', () => { canvas._drag = false; });
  canvas.addEventListener('touchstart', (e) => { e.preventDefault(); handler(e); canvas._drag = true; }, { passive: false });
  canvas.addEventListener('touchmove', (e) => { e.preventDefault(); if (canvas._drag) handler(e); }, { passive: false });
  canvas.addEventListener('touchend', () => { canvas._drag = false; });

  pickerInitialized = true;
}

function syncRangesFromCenter() {
  const hCenter = parseInt(document.getElementById('h-slider').value) || 0;
  const vCenter = parseInt(document.getElementById('v-center').value) || 200;
  const sCenter = parseInt(document.getElementById('s-center').value) || 255;
  const hr = parseInt(document.getElementById('hr-slider').value) || 10;
  const vr = parseInt(document.getElementById('vr-slider').value) || 50;
  const sr = parseInt(document.getElementById('sr-slider').value) || 50;

  document.getElementById('s-min-input').value = Math.max(0, sCenter - sr);
  document.getElementById('s-max-input').value = Math.min(255, sCenter + sr);
  document.getElementById('v-min-input').value = Math.max(0, vCenter - vr);
  document.getElementById('v-max-input').value = Math.min(255, vCenter + vr);
}

function drawPalette() {
  const canvas = document.getElementById('palette-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const sat = parseInt(document.getElementById('sat-slider').value) || 255;

  // Use cache if saturation hasn't changed
  if (paletteCache.sat !== sat) {
    const imageData = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
      const v = Math.round((1 - y / h) * 255);
      for (let x = 0; x < w; x++) {
        const hue = Math.round((x / w) * 179);
        const [r, g, b] = hsvToRgb(hue, sat, v);
        const idx = (y * w + x) * 4;
        imageData.data[idx] = r;
        imageData.data[idx + 1] = g;
        imageData.data[idx + 2] = b;
        imageData.data[idx + 3] = 255;
      }
    }
    paletteCache = { sat, imageData };
  }

  ctx.putImageData(paletteCache.imageData, 0, 0);

  // Draw selection rectangle
  const hCenter = parseInt(document.getElementById('h-slider').value) || 0;
  const hr = parseInt(document.getElementById('hr-slider').value) || 10;
  const vCenter = parseInt(document.getElementById('v-center').value) || 200;
  const vr = parseInt(document.getElementById('vr-slider').value) || 50;

  const rx = ((hCenter - hr) / 179) * w;
  const rw = (hr * 2 / 179) * w;
  const ry = (1 - Math.min(255, vCenter + vr) / 255) * h;
  const rh = (Math.min(255, vCenter + vr) - Math.max(0, vCenter - vr)) / 255 * h;

  // Selection box
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2;
  ctx.strokeRect(rx, ry, rw, rh);
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 1;
  ctx.strokeRect(rx - 1, ry - 1, rw + 2, rh + 2);

  // Crosshair at center
  const cx = (hCenter / 179) * w;
  const cy = (1 - vCenter / 255) * h;
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx - 8, cy); ctx.lineTo(cx + 8, cy);
  ctx.moveTo(cx, cy - 8); ctx.lineTo(cx, cy + 8);
  ctx.stroke();
  ctx.strokeStyle = '#000';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - 8, cy); ctx.lineTo(cx + 8, cy);
  ctx.moveTo(cx, cy - 8); ctx.lineTo(cx, cy + 8);
  ctx.stroke();
}

function updateColorPreview() {
  initPickerCanvases();

  const h = parseInt(document.getElementById('h-slider').value) || 0;
  const hr = parseInt(document.getElementById('hr-slider').value) || 10;
  const vr = parseInt(document.getElementById('vr-slider').value) || 50;
  const sr = parseInt(document.getElementById('sr-slider').value) || 50;
  const vCenter = parseInt(document.getElementById('v-center').value) || 200;
  const sCenter = parseInt(document.getElementById('s-center').value) || 255;

  document.getElementById('h-value').textContent = h;
  document.getElementById('hr-value').textContent = hr;
  document.getElementById('vr-value').textContent = vr;
  document.getElementById('sr-value').textContent = sr;
  document.getElementById('sat-display').textContent = sCenter;
  document.getElementById('sat-slider').value = sCenter;

  syncRangesFromCenter();

  // Preview swatch
  const [r, g, b] = hsvToRgb(h, sCenter, vCenter);
  document.getElementById('color-preview').style.background = `rgb(${r},${g},${b})`;

  drawPalette();
}

function onSatSliderChange() {
  document.getElementById('s-center').value = document.getElementById('sat-slider').value;
  document.getElementById('sat-display').textContent = document.getElementById('sat-slider').value;
  syncRangesFromCenter();
  updateColorPreview();
}

function onPickerNumberChange() {
  updateColorPreview();
}

async function saveColor() {
  if (!state.selectedCircleId) return;
  const name = document.getElementById('color-name-input').value.trim();
  if (!name) { showToast('色名を入力してください', 'error'); return; }

  const data = {
    name,
    h_center: parseInt(document.getElementById('h-slider').value),
    h_range: parseInt(document.getElementById('hr-slider').value),
    s_min: parseInt(document.getElementById('s-min-input').value),
    s_max: parseInt(document.getElementById('s-max-input').value),
    v_min: parseInt(document.getElementById('v-min-input').value),
    v_max: parseInt(document.getElementById('v-max-input').value),
  };

  let result;
  if (state.editingColorName) {
    // Update existing color
    result = await api('PUT',
      `/api/circles/${state.selectedCircleId}/colors/${encodeURIComponent(state.editingColorName)}`,
      data);
  } else {
    // Add new color
    result = await api('POST', `/api/circles/${state.selectedCircleId}/colors`, data);
  }

  if (result.success) {
    closeColorModal();
    await loadConfig();
    selectCircle(state.selectedCircleId);
    const action = state.editingColorName ? '更新' : '追加';
    showToast(`色「${name}」を${action}しました`, 'success');
    state.editingColorName = null;
  }
}

async function removeColor(circleId, colorName) {
  await api('DELETE', `/api/circles/${circleId}/colors/${encodeURIComponent(colorName)}`);
  await loadConfig();
  selectCircle(circleId);
}

// =============================================================================
// Group Operations
// =============================================================================
async function addGroup() {
  const result = await api('POST', '/api/groups', {});
  if (result.success) {
    state.groups.push(result.group);
    renderGroups();
    renderCircleEditor();
    showToast('グループを追加しました', 'success');
  }
}

function renderGroups() {
  const el = document.getElementById('group-list');

  if (state.groups.length === 0) {
    el.innerHTML = '<div class="empty-state">グループなし</div>';
    return;
  }

  el.innerHTML = state.groups.map(g => {
    const circles = state.circles.filter(c => c.group_id === g.id);
    const circleTags = circles.map(c =>
      `<span class="circle-tag">${c.name || '円' + c.id}</span>`
    ).join('');

    return `
      <div class="group-item" id="group-${g.id}">
        <div class="group-item-header">
          <span class="group-item-title" onclick="toggleGroup(${g.id})">${g.name}
            <span class="group-item-count">${circles.length}円</span>
          </span>
          <button class="btn-icon-delete" onclick="deleteGroup(${g.id})" title="削除">&times;</button>
        </div>
        <div class="group-item-body">
          <div class="group-field">
            <label>名前</label>
            <input value="${g.name}" onchange="updateGroup(${g.id},{name:this.value})">
          </div>
          <div class="group-field">
            <label>STA_NO2</label>
            <input value="${g.sta_no2}" onchange="updateGroup(${g.id},{sta_no2:this.value})">
          </div>
          <div class="group-field">
            <label>STA_NO3</label>
            <input value="${g.sta_no3}" onchange="updateGroup(${g.id},{sta_no3:this.value})">
          </div>
          <div class="group-field">
            <label>デフォルト</label>
            <input type="number" value="${g.default_value}" onchange="updateGroup(${g.id},{default_value:parseInt(this.value)})">
          </div>
          <div class="group-circles">${circleTags || '<span style="color:var(--sd-color-text-disabled)">円なし</span>'}</div>
          <div class="mt-2">
            <button class="btn btn-secondary btn-sm" onclick="openRuleModal(${g.id})">ルール設定</button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function toggleGroup(groupId) {
  const el = document.getElementById(`group-${groupId}`);
  if (el) el.classList.toggle('expanded');
}

async function updateGroup(id, data) {
  const result = await api('PUT', `/api/groups/${id}`, data);
  if (result.success) {
    const idx = state.groups.findIndex(g => g.id === id);
    if (idx >= 0) Object.assign(state.groups[idx], result.group);
    renderGroups();
    renderCircleEditor();
  }
}

async function deleteGroup(id) {
  await api('DELETE', `/api/groups/${id}`);
  state.groups = state.groups.filter(g => g.id !== id);
  state.rules = state.rules.filter(r => r.group_id !== id);
  await loadConfig();
  showToast('グループを削除しました', 'success');
}

// =============================================================================
// Rule Operations
// =============================================================================
function openRuleModal(groupId) {
  state.editingRuleGroupId = groupId;
  state.editingRuleId = null;
  const group = state.groups.find(g => g.id === groupId);
  document.getElementById('rule-modal-title').textContent = `ルール設定 - ${group ? group.name : ''}`;
  document.getElementById('rule-form').classList.add('hidden');
  renderRuleList();
  document.getElementById('rule-modal-backdrop').classList.add('active');
}

function closeRuleModal() {
  document.getElementById('rule-modal-backdrop').classList.remove('active');
}

function renderRuleList() {
  const el = document.getElementById('rule-list');
  const groupRules = state.rules
    .filter(r => r.group_id === state.editingRuleGroupId)
    .sort((a, b) => b.priority - a.priority);

  if (groupRules.length === 0) {
    el.innerHTML = '<div class="empty-state">ルールなし</div>';
    return;
  }

  el.innerHTML = groupRules.map(r => {
    const desc = r.conditions.map(c => {
      let s = `円${c.circle_id}=${c.color}`;
      if (c.blinking) s += '(点滅)';
      return s;
    }).join(' + ');

    return `
      <div class="flex items-center justify-between" style="padding:var(--sd-spacing-2) 0;border-bottom:1px solid var(--sd-color-border)">
        <div>
          <span class="badge badge-info">優先度:${r.priority}</span>
          <span style="font-size:var(--sd-font-size-sm);margin-left:var(--sd-spacing-2)">${desc} → ${r.value}</span>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary btn-sm" onclick="editRule(${r.id})">編集</button>
          <button class="btn btn-danger btn-sm" onclick="deleteRule(${r.id})">削除</button>
        </div>
      </div>
    `;
  }).join('');
}

function addNewRule() {
  state.editingRuleId = null;
  document.getElementById('rule-priority').value = 100;
  document.getElementById('rule-value').value = 0;
  document.getElementById('rule-conditions').innerHTML = '';
  addRuleCondition();
  document.getElementById('rule-form').classList.remove('hidden');
}

function editRule(ruleId) {
  const rule = state.rules.find(r => r.id === ruleId);
  if (!rule) return;

  state.editingRuleId = ruleId;
  document.getElementById('rule-priority').value = rule.priority;
  document.getElementById('rule-value').value = rule.value;
  document.getElementById('rule-conditions').innerHTML = '';

  rule.conditions.forEach(c => addRuleCondition(c));
  document.getElementById('rule-form').classList.remove('hidden');
}

function cancelRuleEdit() {
  document.getElementById('rule-form').classList.add('hidden');
  state.editingRuleId = null;
}

function addRuleCondition(existing = null) {
  const el = document.getElementById('rule-conditions');
  const groupCircles = state.circles.filter(c => c.group_id === state.editingRuleGroupId);

  // Collect all colors from group circles
  const allColors = new Set();
  groupCircles.forEach(c => (c.colors || []).forEach(col => allColors.add(col.name)));

  const circleOpts = groupCircles.map(c =>
    `<option value="${c.id}" ${existing && existing.circle_id === c.id ? 'selected' : ''}>${c.name || '円' + c.id}</option>`
  ).join('');

  const colorOpts = [...allColors].map(name =>
    `<option value="${name}" ${existing && existing.color === name ? 'selected' : ''}>${name}</option>`
  ).join('');

  const div = document.createElement('div');
  div.className = 'flex items-center gap-2 mb-2';
  div.innerHTML = `
    <select class="form-select cond-circle" style="width:auto;flex:1">${circleOpts}</select>
    <span>=</span>
    <select class="form-select cond-color" style="width:auto;flex:1">${colorOpts}</select>
    <label style="font-size:var(--sd-font-size-xs);white-space:nowrap">
      <input type="checkbox" class="cond-blink" ${existing && existing.blinking ? 'checked' : ''}> 点滅
    </label>
    <span class="color-item-delete" onclick="this.parentElement.remove()">&times;</span>
  `;
  el.appendChild(div);
}

async function saveRule() {
  const condEls = document.querySelectorAll('#rule-conditions > div');
  const conditions = Array.from(condEls).map(div => ({
    circle_id: parseInt(div.querySelector('.cond-circle').value),
    color: div.querySelector('.cond-color').value,
    blinking: div.querySelector('.cond-blink').checked
  }));

  if (conditions.length === 0) {
    showToast('条件を追加してください', 'error');
    return;
  }

  const data = {
    group_id: state.editingRuleGroupId,
    priority: parseInt(document.getElementById('rule-priority').value),
    type: conditions.length > 1 ? 'composite' : 'single',
    conditions,
    value: parseInt(document.getElementById('rule-value').value)
  };

  let result;
  if (state.editingRuleId) {
    result = await api('PUT', `/api/rules/${state.editingRuleId}`, data);
  } else {
    result = await api('POST', '/api/rules', data);
  }

  if (result.success) {
    await loadConfig();
    renderRuleList();
    cancelRuleEdit();
    showToast('ルールを保存しました', 'success');
  }
}

async function deleteRule(ruleId) {
  await api('DELETE', `/api/rules/${ruleId}`);
  state.rules = state.rules.filter(r => r.id !== ruleId);
  renderRuleList();
  showToast('ルールを削除しました', 'success');
}

// =============================================================================
// Mode Toggle
// =============================================================================
async function toggleMode() {
  if (state.mode === 'edit') {
    // Start run mode
    const result = await api('POST', '/api/run/start');
    if (!result.success) {
      showToast(result.error || '実行開始に失敗しました', 'error');
      return;
    }
    state.mode = 'run';
    document.getElementById('mode-label').textContent = '実行中';
    document.getElementById('btn-toggle-mode').textContent = '停止';
    document.getElementById('btn-toggle-mode').classList.remove('btn-primary');
    document.getElementById('btn-toggle-mode').classList.add('btn-danger');
    document.getElementById('edit-toolbar').classList.add('hidden');
    document.getElementById('edit-settings').classList.add('hidden');
    document.getElementById('run-settings').classList.remove('hidden');

    // Start status polling
    state.statusPollTimer = setInterval(pollStatus, 500);
  } else {
    // Stop run mode
    await api('POST', '/api/run/stop');
    state.mode = 'edit';
    document.getElementById('mode-label').textContent = '編集モード';
    document.getElementById('btn-toggle-mode').textContent = '実行開始';
    document.getElementById('btn-toggle-mode').classList.remove('btn-danger');
    document.getElementById('btn-toggle-mode').classList.add('btn-primary');
    document.getElementById('edit-toolbar').classList.remove('hidden');
    document.getElementById('edit-settings').classList.remove('hidden');
    document.getElementById('run-settings').classList.add('hidden');

    if (state.statusPollTimer) {
      clearInterval(state.statusPollTimer);
      state.statusPollTimer = null;
    }
  }
}

// =============================================================================
// Status Polling (Run Mode)
// =============================================================================
async function pollStatus() {
  try {
    const data = await api('GET', '/api/status');

    // MQTT badge
    const mqttBadge = document.getElementById('mqtt-badge');
    if (data.mqtt && data.mqtt.connected) {
      mqttBadge.className = 'badge badge-success';
      mqttBadge.textContent = `MQTT: 接続中`;
    } else {
      mqttBadge.className = 'badge badge-error';
      mqttBadge.textContent = 'MQTT: 未接続';
    }

    // Group statuses
    renderRunStatus(data);

    // Send log
    renderSendLog(data.send_log || []);

    // Footer
    const sent = data.mqtt ? data.mqtt.sent : 0;
    const errors = data.mqtt ? data.mqtt.errors : 0;
    const pending = data.mqtt ? data.mqtt.pending : 0;
    document.getElementById('footer-status').textContent =
      `送信:${sent} エラー:${errors} キュー:${pending}`;

    // Bridge status (Oracle DB)
    refreshBridgeStatus();

  } catch (e) {
    // Ignore polling errors
  }
}

function renderRunStatus(data) {
  const el = document.getElementById('status-list');
  const results = data.results || [];
  const groupValues = data.group_values || {};

  // Color map for display
  const colorMap = {
    '赤': '#EF4444', '緑': '#10B981', '黄': '#F59E0B',
    '青': '#3B82F6', 'オレンジ': '#F97316', '紫': '#8B5CF6',
    '白': '#E5E7EB', '黒': '#374151', 'ピンク': '#EC4899'
  };

  const resultMap = {};
  results.forEach(r => { resultMap[r.circle_id] = r; });

  el.innerHTML = state.groups.map(g => {
    const value = groupValues[g.id] !== undefined ? groupValues[g.id] : g.default_value;
    const groupCircles = state.circles.filter(c => c.group_id === g.id);

    const circleStatuses = groupCircles.map(c => {
      const r = resultMap[c.id];
      const colorName = r ? (r.detected_color || '未検出') : '未検出';
      const bgColor = colorMap[colorName] || '#9CA3AF';
      const blinkClass = r && r.is_blinking ? 'blink-indicator' : '';
      const blinkText = r && r.is_blinking ? ' (点滅)' : '';

      return `
        <div class="circle-status">
          <div class="circle-status-color ${blinkClass}" style="background:${bgColor}"></div>
          <span>${c.name || '円' + c.id}: ${colorName}${blinkText}</span>
        </div>
      `;
    }).join('');

    return `
      <div class="group-status">
        <div class="group-status-header">
          <span class="group-status-name">${g.name}</span>
          <span class="group-status-value">${value}</span>
        </div>
        ${circleStatuses}
      </div>
    `;
  }).join('');
}

function renderSendLog(log) {
  const el = document.getElementById('send-log');
  if (log.length === 0) {
    el.innerHTML = '<div class="empty-state">送信待機中...</div>';
    return;
  }

  el.innerHTML = log.slice(-15).reverse().map(entry =>
    `<div class="send-log-entry">
      <span class="time">${entry.time}</span>
      <span>${entry.sta_no3}</span>
      <span>&rarr; ${entry.value}</span>
      <span class="${entry.sent ? 'status-ok' : 'status-fail'}">${entry.sent ? '&#10003;' : '&#10007;'}</span>
    </div>`
  ).join('');
}

// =============================================================================
// Tab Navigation (Mobile)
// =============================================================================
function showTab(tab) {
  const btns = document.querySelectorAll('.tab-nav button');
  btns.forEach((b, i) => b.classList.toggle('active', i === (tab === 'video' ? 0 : 1)));

  document.getElementById('video-panel').setAttribute('data-hidden', tab !== 'video');
  document.getElementById('settings-panel').setAttribute('data-hidden', tab !== 'settings');
}

// =============================================================================
// Settings Tab Navigation
// =============================================================================
function showSettingsTab(tabId) {
  // Update tab buttons
  document.querySelectorAll('.settings-tab-nav button').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
  });
  // Update tab content
  document.querySelectorAll('.settings-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === tabId);
  });
}

// =============================================================================
// Toast Notifications
// =============================================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type === 'info' ? 'success' : type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3000);
}
