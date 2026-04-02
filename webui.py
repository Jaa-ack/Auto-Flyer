import argparse
import json
import subprocess
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from geocode import geocode_with_fallback
from fly import MAX_ROUTE_POINTS, is_pid_running, load_state

ROOT = Path(__file__).resolve().parent
FLY = ROOT / "fly.py"
ROUTES_FILE = ROOT / ".saved_routes.json"
HOST = "127.0.0.1"
PORT = 8765

HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moving UI</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255,255,255,0.9);
      --ink: #1f2a30;
      --accent: #0f766e;
      --accent-2: #b45309;
      --line: #d7cdbd;
      --soft: #6b7280;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "SF Pro TC", "PingFang TC", "Noto Sans TC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15,118,110,0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(180,83,9,0.12), transparent 26%),
        var(--bg);
    }
    main {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 20px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 18px 40px rgba(31,42,48,0.06);
    }
    h1, h2, h3 { margin: 0 0 10px; }
    h1 { font-size: 28px; }
    h2 { font-size: 18px; }
    p, li, label, button, input, select, textarea { font-size: 14px; }
    .muted { color: var(--soft); }
    .row { display: flex; gap: 10px; flex-wrap: wrap; }
    .row > * { flex: 1 1 180px; }
    .param-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }
    .field {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: rgba(255,255,255,0.82);
    }
    .field label {
      display: block;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .field small {
      display: block;
      color: var(--soft);
      margin-top: 6px;
      line-height: 1.45;
    }
    input, select, textarea, button {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 10px 12px;
      background: white;
    }
    textarea { min-height: 84px; resize: vertical; }
    button {
      cursor: pointer;
      background: var(--accent);
      color: white;
      border: none;
      font-weight: 600;
    }
    button.secondary { background: #334155; }
    button.warn { background: var(--accent-2); }
    button.light {
      background: white;
      color: var(--ink);
      border: 1px solid var(--line);
    }
    .list {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: rgba(255,255,255,0.9);
    }
    .card strong { display: block; margin-bottom: 6px; }
    .toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }
    .toolbar button { flex: 1 1 120px; }
    .waypoint-card.active {
      border-color: var(--accent);
      box-shadow: inset 0 0 0 1px var(--accent);
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #102028;
      color: #e5f2ef;
      border-radius: 14px;
      padding: 14px;
      min-height: 180px;
      overflow: auto;
    }
    .badge {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      background: rgba(15,118,110,0.12);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }
    .saved-route-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .timer-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .timer-box {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: rgba(255,255,255,0.88);
    }
    .timer-box .label {
      color: var(--soft);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .timer-box .value {
      font-size: 20px;
      font-weight: 700;
    }
    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; }
      .param-grid { grid-template-columns: 1fr; }
      .timer-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Moving UI</h1>
      <p class="muted">搜尋地址、挑點、執行 set / route / clear。多點 route 最多 5 點，會自動閉環回到第一點。</p>

      <h2>1. 搜尋地址</h2>
      <div class="row">
        <input id="query" placeholder="例如 Tokyo Tower, Tokyo, Japan">
        <input id="limit" type="number" min="1" max="8" value="5">
        <button id="searchBtn">搜尋</button>
      </div>
      <div id="searchResults" class="list"></div>

      <h2 style="margin-top:18px;">2. 已選點位 <span class="badge" id="waypointCount">0 / 5</span></h2>
      <p class="muted">第一個點永遠是起點 A。`set` 會直接把定位設到 A，`route` 也會從 A 依序跑到後面的點，再回到 A。</p>
      <div id="waypoints" class="list"></div>
      <div class="toolbar">
        <button class="light" id="clearPointsBtn">清空點位</button>
      </div>

      <h2 style="margin-top:18px;">3. 已儲存路線</h2>
      <div class="row">
        <input id="routeName" placeholder="輸入這條路線的名稱，例如 福岡夜騎">
        <button class="light" id="saveRouteBtn">保存目前點位</button>
      </div>
      <div id="savedRoutes" class="list"></div>

      <h2 style="margin-top:18px;">4. 操作參數</h2>
      <div class="param-grid">
        <div class="field">
          <label for="configMode">設定模式 `configMode`</label>
          <select id="configMode">
            <option value="preset">固定參數</option>
            <option value="manual">自己調整</option>
          </select>
          <small>固定參數適合快速使用；自己調整則可自由修改所有 route 參數。</small>
        </div>
        <div class="field">
          <label for="routeMode">移動模式 `routeMode`</label>
          <select id="routeMode">
            <option value="cycle">cycle</option>
            <option value="walk">walk</option>
            <option value="car-direct">car-direct</option>
            <option value="car-road">car-road</option>
          </select>
          <small>固定模式下，選完之後下面五個欄位會自動套用。`car-direct` 是直線高速，`car-road` 是沿道路高速。</small>
        </div>
        <div class="field">
          <label for="speedKph">移動速度 `speedKph`</label>
          <input id="speedKph" type="number" step="0.1" min="0.1" value="16.0">
          <small>固定模式會自動填入。手動模式下可自行修改 km/h。</small>
        </div>
        <div class="field">
          <label for="stepMeters">路徑點間距 `stepMeters`</label>
          <input id="stepMeters" type="number" step="0.5" min="1" value="2.0">
          <small>越小越平滑。固定模式會自動填入，手動模式可自行改。</small>
        </div>
        <div class="field">
          <label for="routeSource">路徑來源 `routeSource`</label>
          <select id="routeSource">
            <option value="osrm">osrm</option>
            <option value="linear">linear</option>
          </select>
          <small>`osrm` 走真實道路，`linear` 直線連點。</small>
        </div>
        <div class="field">
          <label for="pauseSeconds">停留秒數 `pauseSeconds`</label>
          <input id="pauseSeconds" type="number" step="1" min="0" value="0">
          <small>固定模式會自動填入，手動模式可自行改。</small>
        </div>
        <div class="field">
          <label for="routeProfile">路線類型 `routeProfile`</label>
          <select id="routeProfile">
            <option value="cycling">cycling</option>
            <option value="foot">foot</option>
            <option value="driving">driving</option>
          </select>
          <small>固定模式會自動填入；手動模式下可自由選擇。</small>
        </div>
      </div>

      <h2 style="margin-top:18px;">5. 操作</h2>
      <div class="toolbar">
        <button id="setBtn">set 到 A 點</button>
        <button class="secondary" id="routeBtn">route 閉環移動</button>
        <button class="warn" id="clearBtn">clear</button>
        <button class="light" id="statusBtn">status</button>
      </div>

    </section>

    <section>
      <h2>輸出</h2>
      <pre id="output">尚未執行任何操作。</pre>
      <h2 style="margin-top:18px;">Route 計時器</h2>
      <div class="timer-grid">
        <div class="timer-box">
          <div class="label">目前狀態</div>
          <div class="value" id="timerStatus">尚未開始</div>
        </div>
        <div class="timer-box">
          <div class="label">開始時間</div>
          <div class="value" id="timerStartedAt">--</div>
        </div>
        <div class="timer-box">
          <div class="label">已經過</div>
          <div class="value" id="timerElapsed">--:--:--</div>
        </div>
        <div class="timer-box">
          <div class="label">結束時間</div>
          <div class="value" id="timerEndedAt">--</div>
        </div>
      </div>
      <p class="muted" id="timerNote">只顯示狀態、已經過時間與時間戳記，不再顯示剩餘時間或時間到提醒。</p>
    </section>
  </main>

  <script>
    const ROUTE_PRESETS = {
      cycle: {
        route_profile: "cycling",
        speed_kph: 16.0,
        step_meters: 2.0,
        route_source: "osrm",
        pause_seconds: 0
      },
      walk: {
        route_profile: "foot",
        speed_kph: 4.8,
        step_meters: 2.0,
        route_source: "osrm",
        pause_seconds: 0
      },
      "car-direct": {
        route_profile: "driving",
        speed_kph: 100.0,
        step_meters: 15.0,
        route_source: "linear",
        pause_seconds: 0
      },
      "car-road": {
        route_profile: "driving",
        speed_kph: 80.0,
        step_meters: 5.0,
        route_source: "osrm",
        pause_seconds: 0
      }
    };

    const state = { searchResults: [], waypoints: [], savedRoutes: [], routeMonitor: null };

    function byId(id) { return document.getElementById(id); }

    function setOutput(value) {
      byId("output").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function formatSeconds(totalSeconds) {
      if (totalSeconds == null || !Number.isFinite(totalSeconds) || totalSeconds < 0) {
        return "--:--:--";
      }
      const seconds = Math.max(0, Math.floor(totalSeconds));
      const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
      const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
      const secs = String(seconds % 60).padStart(2, "0");
      return `${hours}:${minutes}:${secs}`;
    }

    function renderRouteMonitor(data) {
      state.routeMonitor = data;
      byId("timerStatus").textContent = data.label || "尚未開始";
      byId("timerElapsed").textContent = formatSeconds(data.elapsed_seconds);
      byId("timerStartedAt").textContent = data.started_at_label || "--";
      byId("timerEndedAt").textContent = data.ended_at_label || "--";
      byId("timerNote").textContent = data.note || "當 route 開始後，這裡會持續更新進度。";
    }

    async function refreshRouteMonitor() {
      try {
        const response = await fetch("/api/route-monitor");
        const data = await response.json();
        renderRouteMonitor(data);
      } catch (error) {
        renderRouteMonitor({
          label: "監看失敗",
          elapsed_seconds: null,
          started_at_label: "--",
          ended_at_label: "--",
          note: "目前無法取得 route 狀態。"
        });
      }
    }

    function updateWaypointCount() {
      byId("waypointCount").textContent = `${state.waypoints.length} / 5`;
    }

    function setManualDisabled(disabled) {
      byId("speedKph").readOnly = disabled;
      byId("stepMeters").readOnly = disabled;
      byId("pauseSeconds").readOnly = disabled;
      byId("routeSource").disabled = disabled;
      byId("routeProfile").disabled = disabled;
      byId("routeMode").disabled = false;
    }

    function syncRoutePresetFields() {
      if (byId("configMode").value !== "preset") {
        setManualDisabled(false);
        return;
      }
      const mode = byId("routeMode").value;
      const preset = ROUTE_PRESETS[mode];
      byId("routeProfile").value = preset.route_profile;
      byId("speedKph").value = preset.speed_kph.toFixed(1);
      byId("stepMeters").value = preset.step_meters.toFixed(1);
      byId("routeSource").value = preset.route_source;
      byId("pauseSeconds").value = String(preset.pause_seconds);
      setManualDisabled(true);
    }

    function renderSavedRoutes() {
      const root = byId("savedRoutes");
      root.innerHTML = "";
      if (!state.savedRoutes.length) {
        const card = document.createElement("div");
        card.className = "card";
        card.textContent = "目前沒有已儲存路線。";
        root.appendChild(card);
        return;
      }
      state.savedRoutes.forEach((route) => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <div class="saved-route-title">
            <strong>${route.name}</strong>
            <span class="badge">${route.waypoints.length} 點</span>
          </div>
          <div class="muted">建立時間: ${route.updated_at || "-"}</div>
        `;
        const toolbar = document.createElement("div");
        toolbar.className = "toolbar";
        const loadBtn = document.createElement("button");
        loadBtn.className = "light";
        loadBtn.textContent = "套用到目前點位";
        loadBtn.onclick = () => loadSavedRoute(route.name);
        toolbar.appendChild(loadBtn);
        const routeBtn = document.createElement("button");
        routeBtn.className = "light";
        routeBtn.textContent = "直接開始 route";
        routeBtn.onclick = async () => {
          await loadSavedRoute(route.name, false);
          await byId("routeBtn").onclick();
        };
        toolbar.appendChild(routeBtn);
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "light";
        deleteBtn.textContent = "刪除";
        deleteBtn.onclick = () => deleteSavedRoute(route.name);
        toolbar.appendChild(deleteBtn);
        card.appendChild(toolbar);
        root.appendChild(card);
      });
    }

    function renderSearchResults() {
      const root = byId("searchResults");
      root.innerHTML = "";
      state.searchResults.forEach((item, index) => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <strong>[${index + 1}] ${item.display_name}</strong>
          <div class="muted">lat=${item.lat} / lng=${item.lng}</div>
        `;
        const toolbar = document.createElement("div");
        toolbar.className = "toolbar";
        const addBtn = document.createElement("button");
        addBtn.className = "light";
        addBtn.textContent = "加入點位";
        addBtn.onclick = () => addWaypoint(item);
        toolbar.appendChild(addBtn);
        card.appendChild(toolbar);
        root.appendChild(card);
      });
    }

    function renderWaypoints() {
      const root = byId("waypoints");
      root.innerHTML = "";
      state.waypoints.forEach((item, index) => {
        const labels = "ABCDE";
        const card = document.createElement("div");
        card.className = "card waypoint-card" + (index === 0 ? " active" : "");
        card.innerHTML = `
          <strong>${labels[index]}. ${item.name}</strong>
          <div class="muted">lat=${item.lat} / lng=${item.lng}</div>
        `;
        const toolbar = document.createElement("div");
        toolbar.className = "toolbar";
        if (index > 0) {
          const upBtn = document.createElement("button");
          upBtn.className = "light";
          upBtn.textContent = "上移";
          upBtn.onclick = () => moveWaypoint(index, -1);
          toolbar.appendChild(upBtn);
        }
        if (index < state.waypoints.length - 1) {
          const downBtn = document.createElement("button");
          downBtn.className = "light";
          downBtn.textContent = "下移";
          downBtn.onclick = () => moveWaypoint(index, 1);
          toolbar.appendChild(downBtn);
        }
        const removeBtn = document.createElement("button");
        removeBtn.className = "light";
        removeBtn.textContent = "移除";
        removeBtn.onclick = () => removeWaypoint(index);
        toolbar.appendChild(removeBtn);
        card.appendChild(toolbar);
        root.appendChild(card);
      });
      updateWaypointCount();
    }

    function addWaypoint(item) {
      if (state.waypoints.length >= 5) {
        setOutput("最多只能保留 5 個點。");
        return;
      }
      state.waypoints.push({
        name: item.display_name,
        lat: Number(item.lat),
        lng: Number(item.lng)
      });
      renderWaypoints();
    }

    function removeWaypoint(index) {
      state.waypoints.splice(index, 1);
      renderWaypoints();
    }

    function moveWaypoint(index, delta) {
      const target = index + delta;
      const temp = state.waypoints[index];
      state.waypoints[index] = state.waypoints[target];
      state.waypoints[target] = temp;
      renderWaypoints();
    }

    async function callApi(path, method = "GET", body = null) {
      const response = await fetch(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : null
      });
      const data = await response.json();
      setOutput(data.output || data);
      if (!response.ok) {
        throw new Error(data.output || "request failed");
      }
      return data;
    }

    async function refreshSavedRoutes() {
      const data = await callApi("/api/routes");
      state.savedRoutes = data.routes || [];
      renderSavedRoutes();
      return data;
    }

    async function loadSavedRoute(name, showOutput = true) {
      const data = await callApi(`/api/routes/load?name=${encodeURIComponent(name)}`);
      state.waypoints = data.route.waypoints || [];
      renderWaypoints();
      if (!showOutput) {
        setOutput(`已套用路線: ${name}`);
      }
    }

    async function deleteSavedRoute(name) {
      await callApi("/api/routes/delete", "POST", { name });
      await refreshSavedRoutes();
    }

    byId("searchBtn").onclick = async () => {
      const query = byId("query").value.trim();
      const limit = Number(byId("limit").value || "5");
      if (!query) {
        setOutput("請先輸入地址。");
        return;
      }
      const data = await callApi(`/api/search?q=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`);
      state.searchResults = data.results || [];
      renderSearchResults();
    };

    byId("clearPointsBtn").onclick = () => {
      state.waypoints = [];
      renderWaypoints();
      setOutput("已清空點位。");
    };

    byId("saveRouteBtn").onclick = async () => {
      const name = byId("routeName").value.trim();
      if (!name) {
        setOutput("請先輸入路線名稱。");
        return;
      }
      if (state.waypoints.length < 2) {
        setOutput("至少要有 2 個點才能保存成 route。");
        return;
      }
      await callApi("/api/routes/save", "POST", { name, waypoints: state.waypoints });
      byId("routeName").value = "";
      await refreshSavedRoutes();
    };

    byId("setBtn").onclick = async () => {
      if (!state.waypoints.length) {
        setOutput("請先加入至少 1 個點。");
        return;
      }
      const point = state.waypoints[0];
      await callApi("/api/set", "POST", point);
    };

    byId("routeBtn").onclick = async () => {
      if (state.waypoints.length < 2) {
        setOutput("route 至少需要 2 個點。");
        return;
      }
      await callApi("/api/route", "POST", {
        waypoints: state.waypoints,
        config_mode: byId("configMode").value,
        route_mode: byId("routeMode").value,
        speed_kph: Number(byId("speedKph").value || "16"),
        step_meters: Number(byId("stepMeters").value || "2"),
        pause_seconds: Number(byId("pauseSeconds").value || "0"),
        route_source: byId("routeSource").value,
        route_profile: byId("routeProfile").value
      });
      await refreshRouteMonitor();
    };

    byId("configMode").onchange = () => syncRoutePresetFields();
    byId("routeMode").onchange = () => syncRoutePresetFields();
    byId("clearBtn").onclick = async () => {
      await callApi("/api/clear", "POST", {});
      await refreshRouteMonitor();
    };
    byId("statusBtn").onclick = async () => {
      await callApi("/api/status");
      await refreshRouteMonitor();
    };
    syncRoutePresetFields();
    refreshSavedRoutes();
    refreshRouteMonitor();
    setInterval(refreshRouteMonitor, 3000);
    setInterval(() => {
      if (!state.routeMonitor) return;
      if (state.routeMonitor.status !== "running") return;
      state.routeMonitor.elapsed_seconds += 1;
      renderRouteMonitor(state.routeMonitor);
    }, 1000);
  </script>
</body>
</html>
"""


def run_fly_command(arguments):
    command = [sys.executable, str(FLY), *arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip() or "(沒有輸出)"


def load_saved_routes():
    if not ROUTES_FILE.exists():
        return []
    try:
        data = json.loads(ROUTES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


def save_saved_routes(routes):
    ROUTES_FILE.write_text(json.dumps(routes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upsert_saved_route(name, waypoints):
    routes = load_saved_routes()
    route = {
        "name": name,
        "waypoints": waypoints,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    filtered = [item for item in routes if item.get("name") != name]
    filtered.append(route)
    filtered.sort(key=lambda item: item.get("name", "").lower())
    save_saved_routes(filtered)
    return route


def delete_saved_route(name):
    routes = load_saved_routes()
    filtered = [item for item in routes if item.get("name") != name]
    if len(filtered) == len(routes):
        return False
    save_saved_routes(filtered)
    return True


def get_saved_route(name):
    for route in load_saved_routes():
        if route.get("name") == name:
            return route
    return None


def build_route_command(payload):
    waypoints = payload.get("waypoints") or []
    if len(waypoints) < 2:
        raise ValueError("route 至少需要 2 個點。")
    if len(waypoints) > MAX_ROUTE_POINTS:
        raise ValueError(f"route 最多只支援 {MAX_ROUTE_POINTS} 個點。")

    config_mode = payload.get("config_mode", "preset")
    route_mode = payload.get("route_mode", "cycle")
    presets = {
        "cycle": {
            "route_profile": "cycling",
            "speed_kph": 16.0,
            "step_meters": 2.0,
            "route_source": "osrm",
            "pause_seconds": 0,
        },
        "walk": {
            "route_profile": "foot",
            "speed_kph": 4.8,
            "step_meters": 2.0,
            "route_source": "osrm",
            "pause_seconds": 0,
        },
        "car-direct": {
            "route_profile": "driving",
            "speed_kph": 100.0,
            "step_meters": 15.0,
            "route_source": "linear",
            "pause_seconds": 0,
        },
        "car-road": {
            "route_profile": "driving",
            "speed_kph": 80.0,
            "step_meters": 5.0,
            "route_source": "osrm",
            "pause_seconds": 0,
        },
    }
    if config_mode == "preset":
        if route_mode not in presets:
            raise ValueError("只支援 walk、cycle、car-direct 或 car-road 四種固定模式。")
        selected = presets[route_mode]
    elif config_mode == "manual":
        selected = {
            "route_profile": payload.get("route_profile", "cycling"),
            "speed_kph": float(payload.get("speed_kph", 16.0)),
            "step_meters": float(payload.get("step_meters", 2.0)),
            "route_source": payload.get("route_source", "osrm"),
            "pause_seconds": float(payload.get("pause_seconds", 0)),
        }
    else:
        raise ValueError("config_mode 只支援 preset 或 manual。")

    start = waypoints[0]
    destination = waypoints[-1]
    command = [
        "route",
        "--from-lat",
        str(start["lat"]),
        "--from-lng",
        str(start["lng"]),
        "--lat",
        str(destination["lat"]),
        "--lng",
        str(destination["lng"]),
        "--speed-kph",
        str(selected["speed_kph"]),
        "--step-meters",
        str(selected["step_meters"]),
        "--pause-seconds",
        str(selected["pause_seconds"]),
        "--route-source",
        selected["route_source"],
        "--route-profile",
        selected["route_profile"],
    ]

    for point in waypoints[1:-1]:
        command.extend(["--via", f'{point["lat"]},{point["lng"]}'])
    return command


def parse_state_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_route_monitor_payload():
    state = load_state() or {}
    action = state.get("action")
    if action != "route":
        return {
            "status": "idle",
            "label": "尚未開始",
            "elapsed_seconds": None,
            "started_at_label": "--",
            "ended_at_label": "--",
            "note": "目前沒有 route 在執行。",
        }

    started_at = parse_state_time(state.get("updated_at"))
    completed_at = parse_state_time(state.get("completed_at"))
    session_pid = state.get("session_pid")
    running = is_pid_running(session_pid) if session_pid else False

    if state.get("route_completed"):
        return {
            "status": "completed",
            "label": "已完成",
            "elapsed_seconds": state.get("estimated_duration_seconds"),
            "started_at_label": state.get("updated_at") or "--",
            "ended_at_label": state.get("completed_at") or "--",
            "note": f"route 已完成，完成時間: {state.get('completed_at') or '-'}",
        }

    if running and started_at is not None:
        elapsed_seconds = max(0, (datetime.now(started_at.tzinfo) - started_at).total_seconds())
        return {
            "status": "running",
            "label": "進行中",
            "elapsed_seconds": elapsed_seconds,
            "started_at_label": state.get("updated_at") or "--",
            "ended_at_label": "--",
            "note": "route 背景 session 仍在執行。",
        }

    if state.get("session_active") is False and not state.get("route_completed"):
        return {
            "status": "stopped",
            "label": "已停止",
            "elapsed_seconds": None,
            "started_at_label": state.get("updated_at") or "--",
            "ended_at_label": "--",
            "note": "route 已被 clear 或背景 session 已停止。",
        }

    return {
        "status": "unknown",
        "label": "狀態未明",
        "elapsed_seconds": None,
        "started_at_label": state.get("updated_at") or "--",
        "ended_at_label": state.get("completed_at") or "--",
        "note": "route 狀態目前無法明確判定，建議再看一次 status。",
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = (params.get("q") or [""])[0].strip()
            limit = int((params.get("limit") or ["5"])[0])
            if not query:
                self._send_json({"output": "請提供搜尋關鍵字。"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                used_query, results, attempts = geocode_with_fallback(query, limit)
            except Exception as exc:
                self._send_json({"output": f"搜尋失敗: {exc}"}, HTTPStatus.BAD_GATEWAY)
                return
            self._send_json(
                {
                    "used_query": used_query,
                    "attempts": attempts,
                    "results": [
                        {
                            "display_name": item.get("display_name", "(無描述)"),
                            "lat": float(item["lat"]),
                            "lng": float(item["lon"]),
                        }
                        for item in results
                    ],
                    "output": f"找到 {len(results)} 筆候選結果。" if results else "找不到符合的地址。",
                }
            )
            return

        if parsed.path == "/api/status":
            code, output = run_fly_command(["status"])
            self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/route-monitor":
            self._send_json(build_route_monitor_payload())
            return

        if parsed.path == "/api/routes":
            self._send_json({"routes": load_saved_routes(), "output": "已載入已儲存路線。"})
            return

        if parsed.path == "/api/routes/load":
            params = parse_qs(parsed.query)
            name = (params.get("name") or [""])[0].strip()
            route = get_saved_route(name)
            if route is None:
                self._send_json({"output": "找不到指定的已儲存路線。"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"route": route, "output": f"已載入路線: {name}"})
            return

        self._send_json({"output": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = self._read_json()

        try:
            if parsed.path == "/api/set":
                code, output = run_fly_command(
                    ["set", "--lat", str(payload["lat"]), "--lng", str(payload["lng"])]
                )
                self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
                return

            if parsed.path == "/api/route":
                command = build_route_command(payload)
                code, output = run_fly_command(command)
                self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
                return

            if parsed.path == "/api/clear":
                code, output = run_fly_command(["clear"])
                self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
                return

            if parsed.path == "/api/routes/save":
                name = (payload.get("name") or "").strip()
                waypoints = payload.get("waypoints") or []
                if not name:
                    raise ValueError("請提供路線名稱。")
                if len(waypoints) < 2:
                    raise ValueError("至少要有 2 個點才能保存 route。")
                if len(waypoints) > MAX_ROUTE_POINTS:
                    raise ValueError(f"最多只能保存 {MAX_ROUTE_POINTS} 個點。")
                route = upsert_saved_route(name, waypoints)
                self._send_json({"route": route, "output": f"已保存路線: {name}"})
                return

            if parsed.path == "/api/routes/delete":
                name = (payload.get("name") or "").strip()
                if not name:
                    raise ValueError("請提供要刪除的路線名稱。")
                deleted = delete_saved_route(name)
                if not deleted:
                    self._send_json({"output": "找不到指定的已儲存路線。"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"output": f"已刪除路線: {name}"})
                return

        except ValueError as exc:
            self._send_json({"output": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except RuntimeError as exc:
            self._send_json({"output": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"output": f"伺服器錯誤: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"output": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        return


def parse_args():
    parser = argparse.ArgumentParser(description="Simple local web UI for fly.py")
    parser.add_argument("--host", default=HOST, help="Bind host")
    parser.add_argument("--port", type=int, default=PORT, help="Bind port")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Moving UI 已啟動: http://{args.host}:{args.port}")
    print("請用瀏覽器打開這個網址。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMoving UI 已停止。")
