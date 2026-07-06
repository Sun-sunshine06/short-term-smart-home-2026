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
    name: "Orange Pi AIpro 20T",
    spec_json: {
      ai_compute: "20 TOPS",
      memory: "12GB/24GB LPDDR4X",
      networking: "dual 2.5G Ethernet, Wi-Fi, Bluetooth",
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
  await Promise.allSettled([refreshStatus(), refreshHistory(), refreshProfile(), refreshFaceUsers(), refreshFaceGallery()]);
}

bindEvents();
refreshAll();
setInterval(() => {
  refreshStatus();
  refreshHistory();
}, 3000);
