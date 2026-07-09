const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => Array.from(document.querySelectorAll(selector));

const stateEls = {
  connection: qs("#connectionStatus"),
  lastUpdatedAt: qs("#lastUpdatedAt"),
  heroTemp: qs("#heroTemp"),
  heroCamera: qs("#heroCamera"),
  heroLock: qs("#heroLock"),
  temperature: qs("#temperature"),
  door: qs("#doorState"),
  window: qs("#windowState"),
  light: qs("#lightLevel"),
  fan: qs("#fanState"),
  lock: qs("#lockState"),
  camera: qs("#cameraState"),
  history: qs("#historyTable"),
  historyHead: qs("#historyTableHead"),
  yoloHistory: qs("#yoloHistoryTable"),
  profile: qs("#hardwareProfile"),
  feedback: qs("#controlFeedback"),
  visionResult: qs("#visionResult"),
  visionUpdatedAt: qs("#visionUpdatedAt"),
  latestCameraImage: qs("#latestCameraImage"),
  visionModel: qs("#visionModel"),
  visionConfidence: qs("#visionConfidence"),
  visionLabels: qs("#visionLabels"),
  latestFaceImage: qs("#latestFaceImage"),
  accessLockState: qs("#accessLockState"),
  faceResultText: qs("#faceResultText"),
  faceUserText: qs("#faceUserText"),
  faceScoreText: qs("#faceScoreText"),
  faceTimeText: qs("#faceTimeText"),
  faceUserName: qs("#faceUserName"),
  faceIdentity: qs("#faceIdentity"),
  faceImagePath: qs("#faceImagePath"),
  copyToGallery: qs("#copyToGallery"),
  faceFeedback: qs("#faceFeedback"),
  faceUsersTable: qs("#faceUsersTable"),
  faceHistoryTable: qs("#faceHistoryTable"),
  galleryDir: qs("#galleryDir"),
  galleryImages: qs("#galleryImages"),
  edgeNodeCard: qs("#edgeNodeCard"),
  accessResultCard: qs("#accessResultCard"),
  modal: qs("#deviceModal"),
  modalTitle: qs("#modalTitle"),
  modalEyebrow: qs("#modalEyebrow"),
  modalBody: qs("#modalBody"),
};

const statusCards = {
  temperature: qs('[data-status-card="temperature"]'),
  door: qs('[data-status-card="door"]'),
  window: qs('[data-status-card="window"]'),
  light: qs('[data-status-card="light"]'),
  fan: qs('[data-status-card="fan"]'),
  lock: qs('[data-status-card="lock"]'),
  camera: qs('[data-status-card="camera"]'),
};

const historyFields = [
  { key: "temperature", label: "温度", format: (record) => record.temperature ?? "--" },
  { key: "door_open", label: "门", format: (record) => boolText(record.door_open, "开", "关") },
  { key: "window_open", label: "窗", format: (record) => boolText(record.window_open, "开", "关") },
  { key: "light_level", label: "灯光", format: (record) => record.light_level ?? "--" },
  { key: "fan_on", label: "风扇", format: (record) => boolText(record.fan_on, "开", "关") },
  { key: "lock_open", label: "门锁", format: (record) => boolText(record.lock_open, "开", "关") },
];

const previousStatus = {};
const charts = {};
let lastHistoryRecords = [];
let latestYoloRecord = null;
let latestFaceRecord = null;
let localOverrides = {};
let faceUsersCache = [];

function boolText(value, open = "开", closed = "关") {
  return value ? open : closed;
}

function shortTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (number >= 1024 ** 3) return `${(number / 1024 ** 3).toFixed(1)} GB`;
  if (number >= 1024 ** 2) return `${(number / 1024 ** 2).toFixed(1)} MB`;
  if (number >= 1024) return `${(number / 1024).toFixed(1)} KB`;
  return `${number} B`;
}

function formatMemoryKb(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return formatBytes(number * 1024);
}

function imageUrl(path, version = "") {
  if (!path) return "";
  const suffix = version ? `&v=${encodeURIComponent(version)}` : "";
  return `/api/files/image?path=${encodeURIComponent(path)}${suffix}`;
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: isFormData ? { ...(options.headers || {}) } : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { error: await response.text() };
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function mergedStatus(data) {
  return { ...data, ...localOverrides };
}

function setPage(pageName) {
  qsa(".page-view").forEach((page) => {
    page.classList.toggle("active", page.dataset.page === pageName);
  });
  qsa("[data-page-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.pageTarget === pageName);
  });
  if (pageName === "data") {
    setTimeout(() => Object.values(charts).forEach((chart) => chart && chart.resize()), 80);
  }
}

function animateTextChange(element, nextValue) {
  if (!element) return;
  const value = String(nextValue);
  if (element.textContent === value) return;
  element.textContent = value;
  element.animate(
    [
      { opacity: 0.3, transform: "translateY(4px)" },
      { opacity: 1, transform: "translateY(0)" },
    ],
    { duration: 260, easing: "ease-out" },
  );
}

function setCardState(name, active, offline = false, rawValue = "") {
  const card = statusCards[name];
  if (!card) return;
  card.classList.toggle("is-active", Boolean(active));
  card.classList.toggle("is-offline", Boolean(offline));

  const previous = previousStatus[name];
  if (previous !== undefined && previous !== rawValue) {
    card.classList.remove("is-changed");
    void card.offsetWidth;
    card.classList.add("is-changed");
  }
  previousStatus[name] = rawValue;
}

function pulseFeedback(element) {
  if (!element) return;
  element.classList.remove("is-fresh");
  void element.offsetWidth;
  element.classList.add("is-fresh");
  setTimeout(() => element.classList.remove("is-fresh"), 800);
}

function applyStatusToUi(data) {
  const temperatureText = data.temperature == null ? "--" : `${Number(data.temperature).toFixed(1)}°C`;
  const doorText = boolText(data.door_open, "开启", "关闭");
  const windowText = boolText(data.window_open, "开启", "关闭");
  const lightText = `${data.light_level ?? 0}%`;
  const fanText = localOverrides.fan_level != null
    ? `${localOverrides.fan_level} 档`
    : boolText(data.fan_on, "运行", "停止");
  const lockText = boolText(data.lock_open, "已开", "已锁");
  const cameraText = boolText(data.camera_online, "在线", "离线");

  stateEls.connection.textContent = data.hardware_online ? "硬件在线" : "后端在线";
  stateEls.connection.classList.remove("offline");
  animateTextChange(stateEls.temperature, temperatureText);
  animateTextChange(stateEls.door, doorText);
  animateTextChange(stateEls.window, windowText);
  animateTextChange(stateEls.light, lightText);
  animateTextChange(stateEls.fan, fanText);
  animateTextChange(stateEls.lock, lockText);
  animateTextChange(stateEls.accessLockState, lockText);
  animateTextChange(stateEls.camera, cameraText);
  animateTextChange(stateEls.heroTemp, `温度 ${temperatureText}`);
  animateTextChange(stateEls.heroCamera, `摄像头 ${cameraText}`);
  animateTextChange(stateEls.heroLock, `门锁 ${lockText}`);
  animateTextChange(stateEls.lastUpdatedAt, `更新于 ${shortTime(data.updated_at)}`);

  setCardState("temperature", Number(data.temperature) >= 28, false, temperatureText);
  setCardState("door", Boolean(data.door_open), false, String(data.door_open));
  setCardState("window", Boolean(data.window_open), false, String(data.window_open));
  setCardState("light", Number(data.light_level) > 0, false, lightText);
  setCardState("fan", Boolean(data.fan_on), false, fanText);
  setCardState("lock", Boolean(data.lock_open), false, String(data.lock_open));
  setCardState("camera", Boolean(data.camera_online), !data.camera_online, String(data.camera_online));
}

async function refreshStatus() {
  try {
    const data = mergedStatus(await api("/api/status"));
    applyStatusToUi(data);
  } catch (error) {
    stateEls.connection.textContent = "离线";
    stateEls.connection.classList.add("offline");
    animateTextChange(stateEls.lastUpdatedAt, "连接失败");
  }
}

function renderLatestYolo(record) {
  latestYoloRecord = record || null;
  if (!record) {
    stateEls.visionUpdatedAt.textContent = "等待摄像头画面";
    stateEls.visionModel.textContent = "--";
    stateEls.visionConfidence.textContent = "--";
    stateEls.visionLabels.innerHTML = `<span class="label-chip">暂无</span>`;
    stateEls.latestCameraImage.removeAttribute("src");
    stateEls.latestCameraImage.parentElement.classList.remove("has-image");
    stateEls.visionResult.textContent = "等待 YOLO 识别结果";
    return;
  }

  const imagePath = record.result_image_path || record.image_path;
  const labels = Array.isArray(record.labels) && record.labels.length ? record.labels : ["未识别"];
  const model = record.model_name || "--";
  const confidence = Number(record.confidence);

  stateEls.visionUpdatedAt.textContent = shortTime(record.created_at);
  stateEls.visionModel.textContent = model;
  stateEls.visionConfidence.textContent = Number.isFinite(confidence) ? confidence.toFixed(2) : "--";
  stateEls.visionLabels.innerHTML = labels
    .map((label) => `<span class="label-chip">${escapeHtml(label)}</span>`)
    .join("");
  stateEls.visionResult.textContent = JSON.stringify(record, null, 2);

  if (imagePath) {
    stateEls.latestCameraImage.src = imageUrl(imagePath, record.id || record.created_at || Date.now());
    stateEls.latestCameraImage.parentElement.classList.add("has-image");
  } else {
    stateEls.latestCameraImage.removeAttribute("src");
    stateEls.latestCameraImage.parentElement.classList.remove("has-image");
  }
}

async function refreshLatestYolo() {
  const data = await api("/api/yolo/latest").catch(() => ({ record: null }));
  renderLatestYolo(data.record);
}

async function refreshYoloHistory() {
  const data = await api("/api/yolo/history?limit=8").catch(() => ({ records: [] }));
  const records = data.records || [];
  if (!stateEls.yoloHistory) return;
  if (!records.length) {
    stateEls.yoloHistory.innerHTML = `<tr><td colspan="4">暂无检测记录</td></tr>`;
    return;
  }
  stateEls.yoloHistory.innerHTML = "";
  for (const record of records) {
    const labels = Array.isArray(record.labels) && record.labels.length ? record.labels.join(" / ") : "未识别";
    const confidence = Number(record.confidence);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${shortTime(record.created_at)}</td>
      <td>${escapeHtml(labels)}</td>
      <td>${Number.isFinite(confidence) ? confidence.toFixed(2) : "--"}</td>
      <td>${escapeHtml(record.model_name || "--")}</td>
    `;
    stateEls.yoloHistory.appendChild(row);
  }
}

function renderLatestFace(record) {
  latestFaceRecord = record || null;
  if (!record) {
    stateEls.faceFeedback.textContent = "等待门禁识别";
    stateEls.accessResultCard?.classList.remove("granted", "denied");
    stateEls.accessResultCard.querySelector("strong").textContent = "等待识别";
    stateEls.faceResultText.textContent = "--";
    stateEls.faceUserText.textContent = "--";
    stateEls.faceScoreText.textContent = "--";
    stateEls.faceTimeText.textContent = "--";
    stateEls.latestFaceImage?.removeAttribute("src");
    stateEls.latestFaceImage?.parentElement.classList.remove("has-image");
    return;
  }

  const matched = Boolean(record.matched);
  const action = matched ? "门禁通过" : "门禁拒绝";
  const user = record.user_name || record.user_id || "未知人员";
  const score = Number(record.score);
  const scoreText = Number.isFinite(score) ? `，相似度 ${score.toFixed(2)}` : "";
  const text = `${action}：${user}${scoreText}，${shortTime(record.created_at)}`;
  stateEls.faceFeedback.textContent = text;
  stateEls.accessResultCard?.classList.toggle("granted", matched);
  stateEls.accessResultCard?.classList.toggle("denied", !matched);
  stateEls.accessResultCard.querySelector("strong").textContent = action;
  stateEls.faceResultText.textContent = matched ? "通过" : "拒绝";
  stateEls.faceUserText.textContent = user;
  stateEls.faceScoreText.textContent = Number.isFinite(score) ? score.toFixed(3) : "--";
  stateEls.faceTimeText.textContent = shortTime(record.created_at);

  const imagePath = record.image_path || latestYoloRecord?.image_path || latestYoloRecord?.result_image_path;
  if (imagePath && stateEls.latestFaceImage) {
    stateEls.latestFaceImage.src = imageUrl(imagePath, record.id || record.created_at || Date.now());
    stateEls.latestFaceImage.parentElement.classList.add("has-image");
  }
}

async function refreshLatestFace() {
  const data = await api("/api/face/latest").catch(() => ({ record: null }));
  renderLatestFace(data.record);
}

async function refreshFaceHistory() {
  const data = await api("/api/face/history?limit=8").catch(() => ({ records: [] }));
  const records = data.records || [];
  if (!stateEls.faceHistoryTable) return;
  if (!records.length) {
    stateEls.faceHistoryTable.innerHTML = `<tr><td colspan="4">暂无门禁记录</td></tr>`;
    return;
  }
  stateEls.faceHistoryTable.innerHTML = "";
  for (const record of records) {
    const score = Number(record.score);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${shortTime(record.created_at)}</td>
      <td>${record.matched ? "通过" : "拒绝"}</td>
      <td>${escapeHtml(record.user_name || record.user_id || "未知人员")}</td>
      <td>${Number.isFinite(score) ? score.toFixed(3) : "--"}</td>
    `;
    stateEls.faceHistoryTable.appendChild(row);
  }
}

function ensureChart(id, config) {
  if (!window.Chart) return null;
  if (charts[id]) return charts[id];
  const canvas = qs(`#${id}`);
  if (!canvas) return null;
  charts[id] = new Chart(canvas, config);
  return charts[id];
}

function updateChart(chart, labels, datasets) {
  if (!chart) return;
  chart.data.labels = labels;
  chart.data.datasets.forEach((dataset, index) => {
    dataset.data = datasets[index] || [];
    dataset.hidden = datasets[index] === null;
  });
  chart.update("none");
}

function initCharts() {
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 260 },
    plugins: {
      legend: { labels: { color: "#5d7880", usePointStyle: true, boxWidth: 8 } },
      tooltip: { mode: "index", intersect: false },
    },
    scales: {
      x: { ticks: { color: "#789097", maxRotation: 0 }, grid: { display: false } },
      y: { ticks: { color: "#789097" }, grid: { color: "rgba(20,75,82,0.08)" } },
    },
  };

  ensureChart("temperatureChart", {
    type: "line",
    data: { labels: [], datasets: [{ label: "温度 °C", data: [], borderColor: "#f39b35", backgroundColor: "rgba(243,155,53,0.16)", fill: true, tension: 0.38 }] },
    options: commonOptions,
  });

  ensureChart("lightChart", {
    type: "line",
    data: { labels: [], datasets: [{ label: "亮度 %", data: [], borderColor: "#20c4c7", backgroundColor: "rgba(32,196,199,0.18)", fill: true, tension: 0.38 }] },
    options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, min: 0, max: 100 } } },
  });

  ensureChart("binaryChart", {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "门", data: [], borderColor: "#4b91e2", stepped: true, tension: 0 },
        { label: "窗", data: [], borderColor: "#20c4c7", stepped: true, tension: 0 },
        { label: "风扇", data: [], borderColor: "#20a66a", stepped: true, tension: 0 },
        { label: "门锁", data: [], borderColor: "#e5554f", stepped: true, tension: 0 },
      ],
    },
    options: {
      ...commonOptions,
      scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, min: -0.1, max: 1.1, ticks: { color: "#789097", stepSize: 1 } } },
    },
  });
}

function selectedHistoryFields() {
  const selected = qsa("[data-history-field]:checked").map((input) => input.dataset.historyField);
  return selected.length ? selected : ["temperature"];
}

function sampleHistoryRecords() {
  const now = Date.now();
  return Array.from({ length: 12 }, (_, index) => {
    const step = 11 - index;
    return {
      created_at: new Date(now - step * 180000).toISOString(),
      temperature: Number((25.4 + Math.sin(index / 2) * 2.3).toFixed(1)),
      door_open: index % 5 === 0,
      window_open: index % 4 === 1,
      light_level: 35 + ((index * 7) % 55),
      fan_on: index % 3 === 0,
      lock_open: index % 6 === 0,
    };
  }).reverse();
}

function renderHistoryCharts(records) {
  initCharts();
  const selected = selectedHistoryFields();
  const ordered = [...records].reverse();
  const labels = ordered.map((record) => shortTime(record.created_at));
  updateChart(charts.temperatureChart, labels, [selected.includes("temperature") ? ordered.map((record) => record.temperature) : null]);
  updateChart(charts.lightChart, labels, [selected.includes("light_level") ? ordered.map((record) => record.light_level) : null]);
  updateChart(charts.binaryChart, labels, [
    selected.includes("door_open") ? ordered.map((record) => Number(Boolean(record.door_open))) : null,
    selected.includes("window_open") ? ordered.map((record) => Number(Boolean(record.window_open))) : null,
    selected.includes("fan_on") ? ordered.map((record) => Number(Boolean(record.fan_on))) : null,
    selected.includes("lock_open") ? ordered.map((record) => Number(Boolean(record.lock_open))) : null,
  ]);
}

function renderHistoryTable(records) {
  const selected = selectedHistoryFields();
  const fields = historyFields.filter((field) => selected.includes(field.key));
  const tableRecords = records.slice(0, 8);
  stateEls.historyHead.innerHTML = `<tr><th>时间</th>${fields.map((field) => `<th>${field.label}</th>`).join("")}</tr>`;
  stateEls.history.innerHTML = "";
  if (!tableRecords.length) {
    stateEls.history.innerHTML = `<tr><td colspan="${fields.length + 1}">暂无记录</td></tr>`;
    return;
  }
  for (const record of tableRecords) {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${shortTime(record.created_at)}</td>${fields.map((field) => `<td>${field.format(record)}</td>`).join("")}`;
    stateEls.history.appendChild(row);
  }
}

async function refreshHistory() {
  const data = await api("/api/history?limit=50").catch(() => ({ records: [] }));
  lastHistoryRecords = (data.records && data.records.length ? data.records : sampleHistoryRecords());
  renderHistoryTable(lastHistoryRecords);
  renderHistoryCharts(lastHistoryRecords);
}

async function refreshProfile() {
  const data = await api("/api/hardware/profile").catch(() => ({
    name: "Orange Pi AIpro",
    spec_json: {
      ai_compute: "按实际昇腾型号确认",
      memory: "按实际昇腾型号确认",
      networking: "Ethernet / Wi-Fi depending on setup",
      expansion: "40-pin GPIO, UART, I2C, SPI, I2S, PWM",
      supported_os: "Ubuntu, openEuler",
    },
  }));
  const spec = data.spec_json || {};
  const rows = [
    ["设备", data.name],
    ["AI 算力", spec.ai_compute],
    ["内存", spec.memory],
    ["网络", spec.networking],
    ["扩展", spec.expansion],
    ["系统", spec.supported_os],
  ];
  stateEls.profile.innerHTML = "";
  for (const [key, value] of rows) {
    const item = document.createElement("div");
    item.innerHTML = `<dt>${key}</dt><dd>${value || "--"}</dd>`;
    stateEls.profile.appendChild(item);
  }
}

async function refreshEdgeNodes() {
  const data = await api("/api/edge/nodes").catch(() => ({ nodes: [] }));
  const nodes = data.nodes || [];
  if (!nodes.length) {
    stateEls.edgeNodeCard.innerHTML = `<div class="empty-state">暂无节点心跳</div>`;
    return;
  }

  const node = nodes[0];
  const metrics = node.latest_metrics_json || {};
  const ips = Array.isArray(node.ip_addresses) ? node.ip_addresses.join(" / ") : node.ip_addresses;
  stateEls.edgeNodeCard.innerHTML = `
    <div class="edge-node-title">
      <strong>${escapeHtml(node.name || node.node_id)}</strong>
      <span>${escapeHtml(node.latest_status || "unknown")}</span>
    </div>
    <dl class="edge-node-list">
      <div><dt>节点 ID</dt><dd>${escapeHtml(node.node_id)}</dd></div>
      <div><dt>IP</dt><dd>${escapeHtml(ips || "--")}</dd></div>
      <div><dt>系统</dt><dd>${escapeHtml(node.os_name || "--")}</dd></div>
      <div><dt>架构</dt><dd>${escapeHtml(node.arch || "--")}</dd></div>
      <div><dt>最后心跳</dt><dd>${shortTime(node.latest_heartbeat_at || node.last_seen_at)}</dd></div>
      <div><dt>磁盘可用</dt><dd>${formatBytes(metrics.disk_free_bytes)}</dd></div>
      <div><dt>内存可用</dt><dd>${formatMemoryKb(metrics.mem_available_kb)}</dd></div>
    </dl>
  `;
}

async function refreshFaceUsers() {
  const data = await api("/api/face/users");
  const users = data.users || [];
  faceUsersCache = users;
  stateEls.faceUsersTable.innerHTML = "";

  if (users.length === 0) {
    stateEls.faceUsersTable.innerHTML = `<tr><td colspan="5">暂无授权人员</td></tr>`;
    return users;
  }

  for (const user of users) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${user.id}</td>
      <td>${escapeHtml(user.identity || "--")}</td>
      <td>${escapeHtml(user.name || "--")}</td>
      <td>${user.image_count ?? 0}</td>
      <td>
        <div class="table-actions">
          <button class="table-action" data-edit-face-user="${user.id}">编辑</button>
          <button class="table-action danger" data-delete-face-user="${user.id}">删除</button>
        </div>
      </td>
    `;
    stateEls.faceUsersTable.appendChild(row);
  }
  return users;
}

function openFaceEditModal(userId) {
  const user = faceUsersCache.find((item) => String(item.id) === String(userId));
  if (!user) throw new Error("未找到认证人员");

  stateEls.modal.classList.add("open");
  stateEls.modal.setAttribute("aria-hidden", "false");
  stateEls.modalEyebrow.textContent = "Access Database";
  stateEls.modalTitle.textContent = "编辑认证人员";
  stateEls.modalBody.innerHTML = `
    <div class="form-grid modal-form-grid">
      <label>
        <span>姓名</span>
        <input id="editFaceUserName" value="${escapeHtml(user.name || "")}" />
      </label>
      <label>
        <span>身份 ID</span>
        <input id="editFaceUserIdentity" value="${escapeHtml(user.identity || "")}" />
      </label>
    </div>
    <div class="modal-actions">
      <button data-modal-cancel>取消</button>
      <button class="primary" id="confirmEditFaceUser">确认修改</button>
    </div>
  `;

  qs("[data-modal-cancel]")?.addEventListener("click", closeModal);
  qs("#confirmEditFaceUser")?.addEventListener("click", async () => {
    try {
      const nextName = qs("#editFaceUserName").value.trim();
      const nextIdentity = qs("#editFaceUserIdentity").value.trim();
      const data = await api(`/api/face/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: nextName,
          identity: nextIdentity,
        }),
      });
      stateEls.faceFeedback.textContent = `已更新 ${data.user.identity}`;
      closeModal();
      await Promise.all([refreshFaceUsers(), refreshFaceGallery()]);
    } catch (error) {
      stateEls.faceFeedback.textContent = error.message;
    }
  });
}

function openFaceDeleteModal(userId) {
  const user = faceUsersCache.find((item) => String(item.id) === String(userId));
  if (!user) throw new Error("未找到认证人员");

  stateEls.modal.classList.add("open");
  stateEls.modal.setAttribute("aria-hidden", "false");
  stateEls.modalEyebrow.textContent = "Access Database";
  stateEls.modalTitle.textContent = "删除认证人员";
  stateEls.modalBody.innerHTML = `
    <div class="delete-warning">
      <strong>${escapeHtml(user.identity || user.name || user.id)}</strong>
      <p>确认删除该认证人员？这会同步删除数据库记录、注册照记录和本地 gallery 目录。</p>
    </div>
    <div class="modal-actions">
      <button data-modal-cancel>取消</button>
      <button class="primary danger-primary" id="confirmDeleteFaceUser">确认删除</button>
    </div>
  `;

  qs("[data-modal-cancel]")?.addEventListener("click", closeModal);
  qs("#confirmDeleteFaceUser")?.addEventListener("click", async () => {
    try {
      await api(`/api/face/users/${userId}`, { method: "DELETE" });
      stateEls.faceFeedback.textContent = `已删除 ${user.identity || user.name || userId}`;
      closeModal();
      await Promise.all([refreshFaceUsers(), refreshFaceGallery()]);
    } catch (error) {
      stateEls.faceFeedback.textContent = error.message;
    }
  });
}

async function refreshFaceGallery() {
  const data = await api("/api/face/gallery");
  stateEls.galleryDir.textContent = data.gallery_dir || "Gallery 未配置";
  stateEls.galleryImages.innerHTML = "";
  const images = data.images || [];
  if (images.length === 0) {
    stateEls.galleryImages.innerHTML = `<div class="gallery-item"><strong>注册照</strong><span>暂无</span></div>`;
    return;
  }

  for (const image of images.slice(-4).reverse()) {
    const item = document.createElement("div");
    item.className = "gallery-item";
    item.innerHTML = `
      <strong>${escapeHtml(image.identity || image.user_id)}</strong>
      <span>${escapeHtml(image.image_path || "--")}</span>
    `;
    stateEls.galleryImages.appendChild(item);
  }
}

async function sendCommand(target, action, value = null) {
  const payload = { target, action };
  if (value !== null) payload.value = value;
  const data = await api("/api/device/control", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (stateEls.feedback) {
    stateEls.feedback.textContent = `命令已入队 #${data.command_id}`;
    pulseFeedback(stateEls.feedback);
  }
  return data;
}

async function toggleSimpleDevice(kind) {
  const fieldMap = { door: "door_open", window: "window_open", lock: "lock_open" };
  const actionMap = { door: ["open", "close"], window: ["open", "close"], lock: ["open", "close"] };
  const field = fieldMap[kind];
  const current = Boolean(localOverrides[field] ?? statusCards[kind]?.classList.contains("is-active"));
  const next = !current;
  localOverrides[field] = next ? 1 : 0;
  applyStatusToUi(mergedStatus(await api("/api/status").catch(() => ({}))));
  await sendCommand(kind, next ? actionMap[kind][0] : actionMap[kind][1]);
}

function openModal(type) {
  stateEls.modal.classList.add("open");
  stateEls.modal.setAttribute("aria-hidden", "false");
  stateEls.modalEyebrow.textContent = type === "light" ? "Lighting" : "Fan";
  stateEls.modalTitle.textContent = type === "light" ? "灯光设置" : "风扇挡位";
  stateEls.modalBody.innerHTML = type === "light" ? lightModalHtml() : fanModalHtml();
  bindModalActions(type);
}

function closeModal() {
  stateEls.modal.classList.remove("open");
  stateEls.modal.setAttribute("aria-hidden", "true");
}

function lightModalHtml() {
  const current = Number(localOverrides.light_level ?? 55);
  return `
    <div class="option-grid">
      <button class="option-card" data-light-mode="relax" data-light-level="60"><strong>休闲</strong><span>亮度 60%</span></button>
      <button class="option-card" data-light-mode="reading" data-light-level="80"><strong>阅读</strong><span>亮度 80%</span></button>
      <button class="option-card" data-light-mode="office" data-light-level="95"><strong>电脑办公</strong><span>亮度 95%</span></button>
      <button class="option-card" data-light-mode="custom"><strong>自定义</strong><span>使用下方滑杆</span></button>
    </div>
    <label class="modal-slider">
      <input id="modalLightLevel" type="range" min="0" max="100" value="${current}" />
      <output id="modalLightOutput">${current}</output>
    </label>
    <button class="primary modal-confirm" data-close-modal>确认设定</button>
  `;
}

function fanModalHtml() {
  const current = Number(localOverrides.fan_level ?? (localOverrides.fan_on ? 1 : 0));
  return `
    <div class="option-grid">
      ${[0, 1, 2, 3].map((level) => `
        <button class="option-card ${current === level ? "active" : ""}" data-fan-level="${level}">
          <strong>${level} 档</strong><span>${level === 0 ? "停止" : `风量 ${level}`}</span>
        </button>
      `).join("")}
    </div>
  `;
}

function bindModalActions(type) {
  if (type === "light") {
    const slider = qs("#modalLightLevel");
    const output = qs("#modalLightOutput");
    slider.addEventListener("input", () => {
      output.textContent = slider.value;
    });
    qsa("[data-light-mode]").forEach((button) => {
      button.addEventListener("click", async () => {
        qsa("[data-light-mode]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        const level = Number(button.dataset.lightLevel || slider.value);
        slider.value = level;
        output.textContent = level;
        localOverrides.light_level = level;
        applyStatusToUi(mergedStatus(await api("/api/status").catch(() => ({}))));
        await sendCommand("light", "set_mode", { mode: button.dataset.lightMode, brightness: level });
      });
    });
    slider.addEventListener("change", async () => {
      const level = Number(slider.value);
      localOverrides.light_level = level;
      applyStatusToUi(mergedStatus(await api("/api/status").catch(() => ({}))));
      await sendCommand("light", "set_brightness", level);
    });
    qs(".modal-confirm")?.addEventListener("click", closeModal);
    return;
  }

  qsa("[data-fan-level]").forEach((button) => {
    button.addEventListener("click", async () => {
      const level = Number(button.dataset.fanLevel);
      qsa("[data-fan-level]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      localOverrides.fan_level = level;
      localOverrides.fan_on = level > 0 ? 1 : 0;
      applyStatusToUi(mergedStatus(await api("/api/status").catch(() => ({}))));
      await sendCommand("fan", "set_level", level);
      closeModal();
    });
  });
}

function normalizeFaceResponse(data) {
  return data.record || data.face_record || data.access_record || data;
}

async function verifyLatestFace() {
  stateEls.faceFeedback.textContent = "正在进行门禁识别...";
  pulseFeedback(stateEls.faceFeedback);
  let data;
  try {
    data = await api("/api/face/verify-latest", {
      method: "POST",
      body: JSON.stringify({}),
    });
  } catch (error) {
    const latestImagePath = latestYoloRecord?.image_path || latestYoloRecord?.result_image_path;
    if (!latestImagePath) throw error;
    data = await api("/api/face/verify", {
      method: "POST",
      body: JSON.stringify({ image_path: latestImagePath, trigger: "verify_latest_fallback" }),
    });
  }
  const record = normalizeFaceResponse(data);
  renderLatestFace(record);
  await refreshFaceHistory();
  await refreshStatus();
}

async function runYoloDetect() {
  const imagePath = latestYoloRecord?.image_path || latestYoloRecord?.result_image_path;
  if (!imagePath) throw new Error("暂无可用于 YOLO 识别的摄像头图片");
  const data = await api("/api/yolo/detect", {
    method: "POST",
    body: JSON.stringify({ image_path: imagePath }),
  });
  stateEls.visionResult.textContent = JSON.stringify(data.record, null, 2);
  renderLatestYolo(data.record);
  await refreshYoloHistory();
}

async function createFaceUser() {
  const name = stateEls.faceUserName.value.trim();
  const identity = stateEls.faceIdentity.value.trim();
  const imageFile = stateEls.faceImagePath.files?.[0];
  const payload = new FormData();
  payload.append("name", name);
  payload.append("copy_to_gallery", stateEls.copyToGallery.checked ? "1" : "0");
  if (identity) payload.append("identity", identity);
  if (imageFile) payload.append("image", imageFile);

  const data = await api("/api/face/users", {
    method: "POST",
    body: payload,
  });
  stateEls.faceFeedback.textContent = `已新增 ${data.user.identity}`;
  stateEls.faceUserName.value = "";
  stateEls.faceIdentity.value = "";
  stateEls.faceImagePath.value = "";
  await Promise.all([refreshFaceUsers(), refreshFaceGallery()]);
}

function bindEvents() {
  qsa("[data-page-target]").forEach((button) => {
    button.addEventListener("click", () => setPage(button.dataset.pageTarget));
  });

  qsa("[data-card-control]").forEach((card) => {
    card.addEventListener("click", () => {
      const type = card.dataset.cardControl;
      if (type === "light" || type === "fan") openModal(type);
      if (type === "door" || type === "window" || type === "lock") toggleSimpleDevice(type).catch((error) => {
        if (stateEls.feedback) stateEls.feedback.textContent = error.message;
      });
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        card.click();
      }
    });
  });

  qsa("[data-close-modal]").forEach((item) => item.addEventListener("click", closeModal));
  qsa("[data-history-field]").forEach((input) => input.addEventListener("change", () => {
    renderHistoryTable(lastHistoryRecords);
    renderHistoryCharts(lastHistoryRecords);
  }));

  qs("#runFaceVerifyLatest").addEventListener("click", () => verifyLatestFace().catch((error) => {
    stateEls.faceFeedback.textContent = error.message;
  }));

  qs("#createFaceUser").addEventListener("click", () => createFaceUser().catch((error) => {
    stateEls.faceFeedback.textContent = error.message;
  }));

  stateEls.faceUsersTable.addEventListener("click", (event) => {
    const editButton = event.target.closest("[data-edit-face-user]");
    const deleteButton = event.target.closest("[data-delete-face-user]");
    if (editButton) {
      try {
        openFaceEditModal(editButton.dataset.editFaceUser);
      } catch (error) {
        stateEls.faceFeedback.textContent = error.message;
      }
    }
    if (deleteButton) {
      try {
        openFaceDeleteModal(deleteButton.dataset.deleteFaceUser);
      } catch (error) {
        stateEls.faceFeedback.textContent = error.message;
      }
    }
  });
}

async function refreshAll() {
  await Promise.allSettled([
    refreshStatus(),
    refreshHistory(),
    refreshProfile(),
    refreshEdgeNodes(),
    refreshFaceUsers(),
    refreshFaceGallery(),
    refreshLatestYolo(),
    refreshYoloHistory(),
    refreshLatestFace(),
    refreshFaceHistory(),
  ]);
}

bindEvents();
refreshAll();
setInterval(() => {
  refreshStatus();
  refreshLatestYolo();
}, 1000);

setInterval(() => {
  refreshHistory();
  refreshEdgeNodes();
  refreshLatestYolo();
  refreshYoloHistory();
  refreshLatestFace();
  refreshFaceHistory();
}, 3000);
