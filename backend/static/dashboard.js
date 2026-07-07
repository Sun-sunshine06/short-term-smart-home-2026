const qs = (selector) => document.querySelector(selector);

const stateEls = {
  connection: qs("#connectionStatus"),
  temperature: qs("#temperature"),
  door: qs("#doorState"),
  window: qs("#windowState"),
  light: qs("#lightLevel"),
  fan: qs("#fanState"),
  lock: qs("#lockState"),
  history: qs("#historyTable"),
  profile: qs("#hardwareProfile"),
  feedback: qs("#controlFeedback"),
  brightness: qs("#brightnessSlider"),
  brightnessOutput: qs("#brightnessOutput"),
  imagePath: qs("#imagePath"),
  visionResult: qs("#visionResult"),
  faceUserName: qs("#faceUserName"),
  faceIdentity: qs("#faceIdentity"),
  faceImagePath: qs("#faceImagePath"),
  copyToGallery: qs("#copyToGallery"),
  faceUserSelect: qs("#faceUserSelect"),
  extraFaceImagePath: qs("#extraFaceImagePath"),
  copyExtraToGallery: qs("#copyExtraToGallery"),
  faceFeedback: qs("#faceFeedback"),
  faceUsersTable: qs("#faceUsersTable"),
  galleryDir: qs("#galleryDir"),
  galleryImages: qs("#galleryImages"),
  edgeNodeCard: qs("#edgeNodeCard"),
};

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
    .replaceAll("\"", "&quot;")
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    stateEls.connection.textContent = data.hardware_online ? "硬件在线" : "后端在线";
    stateEls.connection.classList.remove("offline");
    stateEls.temperature.textContent = data.temperature == null ? "--" : `${Number(data.temperature).toFixed(1)}°C`;
    stateEls.door.textContent = boolText(data.door_open, "开启", "关闭");
    stateEls.window.textContent = boolText(data.window_open, "开启", "关闭");
    stateEls.light.textContent = `${data.light_level ?? 0}%`;
    stateEls.fan.textContent = boolText(data.fan_on, "运行", "停止");
    stateEls.lock.textContent = boolText(data.lock_open, "已开", "已锁");
  } catch (error) {
    stateEls.connection.textContent = "离线";
    stateEls.connection.classList.add("offline");
  }
}

async function refreshHistory() {
  const data = await api("/api/history?limit=8");
  stateEls.history.innerHTML = "";
  if (!data.records || data.records.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6">暂无记录</td>`;
    stateEls.history.appendChild(row);
    return;
  }
  for (const record of data.records) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${shortTime(record.created_at)}</td>
      <td>${record.temperature ?? "--"}</td>
      <td>${boolText(record.door_open, "开", "关")}</td>
      <td>${boolText(record.window_open, "开", "关")}</td>
      <td>${record.light_level ?? "--"}</td>
      <td>${boolText(record.fan_on, "开", "关")}</td>
    `;
    stateEls.history.appendChild(row);
  }
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
  stateEls.faceUsersTable.innerHTML = "";
  stateEls.faceUserSelect.innerHTML = "";

  if (users.length === 0) {
    stateEls.faceUsersTable.innerHTML = `<tr><td colspan="4">暂无授权人员</td></tr>`;
    stateEls.faceUserSelect.innerHTML = `<option value="">暂无人员</option>`;
    return users;
  }

  for (const user of users) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${user.id}</td>
      <td>${escapeHtml(user.identity || "--")}</td>
      <td>${escapeHtml(user.name || "--")}</td>
      <td>${user.image_count ?? 0}</td>
    `;
    stateEls.faceUsersTable.appendChild(row);

    const option = document.createElement("option");
    option.value = user.id;
    option.textContent = `${user.identity || user.id} / ${user.name || "--"}`;
    stateEls.faceUserSelect.appendChild(option);
  }
  return users;
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
  stateEls.feedback.textContent = `命令已入队 #${data.command_id}`;
}

async function runVision(kind) {
  const imagePath = stateEls.imagePath.value.trim();
  const path = kind === "face" ? "/api/face/verify" : "/api/yolo/detect";
  const data = await api(path, {
    method: "POST",
    body: JSON.stringify({ image_path: imagePath }),
  });
  stateEls.visionResult.textContent = JSON.stringify(data.record, null, 2);
}

async function createFaceUser() {
  const name = stateEls.faceUserName.value.trim();
  const identity = stateEls.faceIdentity.value.trim();
  const imagePath = stateEls.faceImagePath.value.trim();
  const payload = {
    name,
    copy_to_gallery: stateEls.copyToGallery.checked,
  };
  if (identity) payload.identity = identity;
  if (imagePath) payload.image_path = imagePath;

  const data = await api("/api/face/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  stateEls.faceFeedback.textContent = `已新增 ${data.user.identity}`;
  stateEls.faceUserName.value = "";
  stateEls.faceIdentity.value = "";
  stateEls.faceImagePath.value = "";
  await Promise.all([refreshFaceUsers(), refreshFaceGallery()]);
}

async function addFaceImage() {
  const userId = stateEls.faceUserSelect.value;
  const imagePath = stateEls.extraFaceImagePath.value.trim();
  if (!userId) throw new Error("请选择人员");
  if (!imagePath) throw new Error("请输入注册照路径");

  const data = await api(`/api/face/users/${userId}/images`, {
    method: "POST",
    body: JSON.stringify({
      image_path: imagePath,
      copy_to_gallery: stateEls.copyExtraToGallery.checked,
    }),
  });
  stateEls.faceFeedback.textContent = `注册照已添加 #${data.image.id}`;
  stateEls.extraFaceImagePath.value = "";
  await Promise.all([refreshFaceUsers(), refreshFaceGallery()]);
}

function bindEvents() {
  document.querySelectorAll("button[data-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await sendCommand(button.dataset.target, button.dataset.action);
      } catch (error) {
        stateEls.feedback.textContent = error.message;
      }
    });
  });

  stateEls.brightness.addEventListener("input", () => {
    stateEls.brightnessOutput.textContent = stateEls.brightness.value;
  });

  qs("#sendBrightness").addEventListener("click", async () => {
    try {
      await sendCommand("light", "set_brightness", Number(stateEls.brightness.value));
    } catch (error) {
      stateEls.feedback.textContent = error.message;
    }
  });

  qs("#runYolo").addEventListener("click", () => runVision("yolo").catch((error) => {
    stateEls.visionResult.textContent = error.message;
  }));

  qs("#runFace").addEventListener("click", () => runVision("face").catch((error) => {
    stateEls.visionResult.textContent = error.message;
  }));

  qs("#createFaceUser").addEventListener("click", () => createFaceUser().catch((error) => {
    stateEls.faceFeedback.textContent = error.message;
  }));

  qs("#addFaceImage").addEventListener("click", () => addFaceImage().catch((error) => {
    stateEls.faceFeedback.textContent = error.message;
  }));
}

async function refreshAll() {
  await Promise.allSettled([
    refreshStatus(),
    refreshHistory(),
    refreshProfile(),
    refreshEdgeNodes(),
    refreshFaceUsers(),
    refreshFaceGallery(),
  ]);
}

bindEvents();
refreshAll();
setInterval(() => {
  refreshStatus();
  refreshHistory();
  refreshEdgeNodes();
}, 3000);
