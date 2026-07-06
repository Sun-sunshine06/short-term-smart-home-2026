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
}

async function refreshAll() {
  await Promise.allSettled([refreshStatus(), refreshHistory(), refreshProfile()]);
}

bindEvents();
refreshAll();
setInterval(() => {
  refreshStatus();
  refreshHistory();
}, 3000);
