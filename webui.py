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
<html lang=\"en\">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto Fly</title>
  <style>
    :root{--bg:#f1efe7;--panel:#fffdf8;--ink:#132127;--muted:#5e6b72;--line:#d9d1c2;--accent:#0f766e;--warn:#b45309;--alt:#334155}
    *{box-sizing:border-box} body{margin:0;color:var(--ink);font-family:Segoe UI,Noto Sans,sans-serif;background:var(--bg)}
    main{max-width:1180px;margin:0 auto;padding:18px;display:grid;grid-template-columns:1.1fr .9fr;gap:14px}
    section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}
    h1,h2{margin:0 0 10px} h1{font-size:26px} h2{font-size:17px;margin-top:14px}
    .muted{color:var(--muted)} .row{display:flex;gap:8px;flex-wrap:wrap} .row>*{flex:1 1 170px}
    input,select,button{width:100%;border-radius:10px;border:1px solid var(--line);padding:9px 10px;background:#fff}
    button{border:none;cursor:pointer;background:var(--accent);color:#fff;font-weight:600} button.alt{background:var(--alt)} button.warn{background:var(--warn)} button.light{border:1px solid var(--line);background:#fff;color:var(--ink)}
    .list{display:grid;gap:8px;margin-top:8px} .card{border:1px solid var(--line);border-radius:10px;padding:10px;background:#fff}
    .card strong{display:block;margin-bottom:4px} .toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.toolbar button{flex:1 1 115px}
    .badge{display:inline-block;font-size:12px;background:#d7eeeb;color:#0f766e;border-radius:999px;padding:2px 8px;font-weight:700}
    .param-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.field{border:1px solid var(--line);border-radius:10px;padding:9px;background:#fff}
    .field label{display:block;margin-bottom:5px;font-weight:700}.field small{display:block;margin-top:5px;color:var(--muted);line-height:1.35}
    pre{min-height:220px;background:#0f2028;color:#e8f2f0;border-radius:10px;padding:11px;white-space:pre-wrap;word-break:break-word;overflow:auto}
    .timer-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.timer-box{border:1px solid var(--line);border-radius:10px;padding:9px;background:#fff}.timer-box .label{font-size:12px;color:var(--muted)}.timer-box .value{font-size:20px;font-weight:700;margin-top:4px}
    @media(max-width:960px){main{grid-template-columns:1fr}.param-grid,.timer-grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Auto Fly</h1>
      <p class="muted">搜尋地址、選點、執行 set / route / clear。</p>

    <h2>1) Search</h2>
    <div class="row"><input id="query" placeholder="Example: Tokyo Tower, Tokyo, Japan"><input id="limit" type="number" min="1" max="8" value="5"><button id="searchBtn">Search</button></div>
    <div id="searchResults" class="list"></div>

    <h2>2) Selected Points <span class="badge" id="waypointCount">0 / 5</span></h2>
    <p class="muted">Point A is used for fixed set and as route start/end.</p>
    <div id="waypoints" class="list"></div>
    <div class="toolbar"><button class="light" id="clearPointsBtn">Clear All Points</button></div>

    <h2>3) Saved Routes</h2>
    <div class="row"><input id="routeName" placeholder="Route name"><button class="light" id="saveRouteBtn">Save Route</button></div>
    <div id="savedRoutes" class="list"></div>

    <h2>4) Route Config</h2>
    <div class="param-grid">
      <div class="field"><label for="configMode">configMode</label><select id="configMode"><option value="preset">preset</option><option value="manual">manual</option></select><small>preset auto-fills fields.</small></div>
      <div class="field"><label for="routeMode">routeMode</label><select id="routeMode"><option value="cycle">cycle</option><option value="walk">walk</option><option value="car-direct">car-direct</option><option value="car-road">car-road</option></select><small>car-direct=linear, car-road=osrm.</small></div>
      <div class="field"><label for="speedKph">speedKph</label><input id="speedKph" type="number" step="0.1" min="0.1" value="16.0"></div>
      <div class="field"><label for="stepMeters">stepMeters</label><input id="stepMeters" type="number" step="0.5" min="1" value="2.0"></div>
      <div class="field"><label for="routeSource">routeSource</label><select id="routeSource"><option value="osrm">osrm</option><option value="linear">linear</option></select></div>
      <div class="field"><label for="pauseSeconds">pauseSeconds</label><input id="pauseSeconds" type="number" step="1" min="0" value="0"></div>
      <div class="field"><label for="routeProfile">routeProfile</label><select id="routeProfile"><option value="cycling">cycling</option><option value="foot">foot</option><option value="driving">driving</option></select></div>
    </div>

    <h2>5) Actions</h2>
    <div class="toolbar"><button id="setBtn">Set Point A</button><button class="alt" id="routeBtn">Run Route</button><button class="warn" id="clearBtn">Clear</button><button class="light" id="statusBtn">Status</button><button class="light" id="doctorBtn">Doctor</button></div>
  </section>

  <section>
    <h2>Output</h2>
    <pre id="output">Ready.</pre>
    <h2 style="margin-top:16px;">Route Monitor</h2>
    <div class="timer-grid">
      <div class="timer-box"><div class="label">State</div><div class="value" id="timerStatus">Idle</div></div>
      <div class="timer-box"><div class="label">Started At</div><div class="value" id="timerStartedAt">--</div></div>
      <div class="timer-box"><div class="label">Elapsed</div><div class="value" id="timerElapsed">--:--:--</div></div>
      <div class="timer-box"><div class="label">Ended At</div><div class="value" id="timerEndedAt">--</div></div>
    </div>
    <p class="muted" id="timerNote">No active route session.</p>
  </section>
</main>

<script>
const ROUTE_PRESETS={cycle:{route_profile:"cycling",speed_kph:16,step_meters:2,route_source:"osrm",pause_seconds:0},walk:{route_profile:"foot",speed_kph:4.8,step_meters:2,route_source:"osrm",pause_seconds:0},"car-direct":{route_profile:"driving",speed_kph:100,step_meters:15,route_source:"linear",pause_seconds:0},"car-road":{route_profile:"driving",speed_kph:80,step_meters:5,route_source:"osrm",pause_seconds:0}};
const state={searchResults:[],waypoints:[],savedRoutes:[],routeMonitor:null};
const byId=(id)=>document.getElementById(id);
const setOutput=(v)=>{byId("output").textContent=typeof v==="string"?v:JSON.stringify(v,null,2)};
const formatSeconds=(s)=>{if(s==null||!Number.isFinite(s)||s<0)return"--:--:--";s=Math.floor(s);const h=String(Math.floor(s/3600)).padStart(2,"0"),m=String(Math.floor((s%3600)/60)).padStart(2,"0"),sec=String(s%60).padStart(2,"0");return `${h}:${m}:${sec}`;};
const renderRouteMonitor=(d)=>{state.routeMonitor=d;byId("timerStatus").textContent=d.label||"Idle";byId("timerElapsed").textContent=formatSeconds(d.elapsed_seconds);byId("timerStartedAt").textContent=d.started_at_label||"--";byId("timerEndedAt").textContent=d.ended_at_label||"--";byId("timerNote").textContent=d.note||"No route info.";};
const refreshRouteMonitor=async()=>{try{renderRouteMonitor(await (await fetch("/api/route-monitor")).json())}catch{renderRouteMonitor({label:"Monitor Error",elapsed_seconds:null,started_at_label:"--",ended_at_label:"--",note:"Failed to query route monitor."})}};
const updateWaypointCount=()=>{byId("waypointCount").textContent=`${state.waypoints.length} / 5`;};
const setManualDisabled=(d)=>{byId("speedKph").readOnly=d;byId("stepMeters").readOnly=d;byId("pauseSeconds").readOnly=d;byId("routeSource").disabled=d;byId("routeProfile").disabled=d;};
const syncRoutePresetFields=()=>{if(byId("configMode").value!=="preset"){setManualDisabled(false);return;}const p=ROUTE_PRESETS[byId("routeMode").value];byId("routeProfile").value=p.route_profile;byId("speedKph").value=p.speed_kph.toFixed(1);byId("stepMeters").value=p.step_meters.toFixed(1);byId("routeSource").value=p.route_source;byId("pauseSeconds").value=String(p.pause_seconds);setManualDisabled(true);};
const callApi=async(path,method="GET",body=null)=>{const r=await fetch(path,{method,headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):null});const d=await r.json();setOutput(d.output||d);if(!r.ok)throw new Error(d.output||"request failed");return d;};
function renderSearchResults(){const root=byId("searchResults");root.innerHTML="";state.searchResults.forEach((item,i)=>{const card=document.createElement("div");card.className="card";card.innerHTML=`<strong>[${i+1}] ${item.display_name}</strong><div class="muted">lat=${item.lat} / lng=${item.lng}</div>`;const tb=document.createElement("div");tb.className="toolbar";const add=document.createElement("button");add.className="light";add.textContent="Add Point";add.onclick=()=>addWaypoint(item);tb.appendChild(add);card.appendChild(tb);root.appendChild(card);});}
function renderWaypoints(){const root=byId("waypoints");root.innerHTML="";const labels="ABCDE";state.waypoints.forEach((item,i)=>{const card=document.createElement("div");card.className="card"+(i===0?" waypoint active":"");card.innerHTML=`<strong>${labels[i]}. ${item.name}</strong><div class="muted">lat=${item.lat} / lng=${item.lng}</div>`;const tb=document.createElement("div");tb.className="toolbar";if(i>0){const up=document.createElement("button");up.className="light";up.textContent="Move Up";up.onclick=()=>moveWaypoint(i,-1);tb.appendChild(up);}if(i<state.waypoints.length-1){const dn=document.createElement("button");dn.className="light";dn.textContent="Move Down";dn.onclick=()=>moveWaypoint(i,1);tb.appendChild(dn);}const rm=document.createElement("button");rm.className="light";rm.textContent="Remove";rm.onclick=()=>removeWaypoint(i);tb.appendChild(rm);card.appendChild(tb);root.appendChild(card);});updateWaypointCount();}
function renderSavedRoutes(){const root=byId("savedRoutes");root.innerHTML="";if(!state.savedRoutes.length){const card=document.createElement("div");card.className="card";card.textContent="No saved routes yet.";root.appendChild(card);return;}state.savedRoutes.forEach((route)=>{const card=document.createElement("div");card.className="card";card.innerHTML=`<strong>${route.name}</strong><div class="muted">points=${route.waypoints.length}, updated=${route.updated_at||"-"}</div>`;const tb=document.createElement("div");tb.className="toolbar";const load=document.createElement("button");load.className="light";load.textContent="Load";load.onclick=()=>loadSavedRoute(route.name);tb.appendChild(load);const run=document.createElement("button");run.className="light";run.textContent="Run";run.onclick=async()=>{await loadSavedRoute(route.name,false);await byId("routeBtn").onclick();};tb.appendChild(run);const del=document.createElement("button");del.className="light";del.textContent="Delete";del.onclick=()=>deleteSavedRoute(route.name);tb.appendChild(del);card.appendChild(tb);root.appendChild(card);});}
function addWaypoint(item){if(state.waypoints.length>=5){setOutput("Maximum 5 points.");return;}state.waypoints.push({name:item.display_name,lat:Number(item.lat),lng:Number(item.lng)});renderWaypoints();}
function removeWaypoint(i){state.waypoints.splice(i,1);renderWaypoints();}
function moveWaypoint(i,d){const t=i+d;[state.waypoints[i],state.waypoints[t]]=[state.waypoints[t],state.waypoints[i]];renderWaypoints();}
async function refreshSavedRoutes(){const data=await callApi("/api/routes");state.savedRoutes=data.routes||[];renderSavedRoutes();}
async function loadSavedRoute(name,showOutput=true){const data=await callApi(`/api/routes/load?name=${encodeURIComponent(name)}`);state.waypoints=data.route.waypoints||[];renderWaypoints();if(!showOutput)setOutput(`Loaded route: ${name}`);}
async function deleteSavedRoute(name){await callApi("/api/routes/delete","POST",{name});await refreshSavedRoutes();}

byId("searchBtn").onclick=async()=>{const q=byId("query").value.trim();const limit=Number(byId("limit").value||"5");if(!q){setOutput("Please enter a search query.");return;}const data=await callApi(`/api/search?q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`);state.searchResults=data.results||[];renderSearchResults();};
byId("clearPointsBtn").onclick=()=>{state.waypoints=[];renderWaypoints();setOutput("Cleared selected points.");};
byId("saveRouteBtn").onclick=async()=>{const name=byId("routeName").value.trim();if(!name){setOutput("Please enter a route name.");return;}if(state.waypoints.length<2){setOutput("Need at least 2 points to save route.");return;}await callApi("/api/routes/save","POST",{name,waypoints:state.waypoints});byId("routeName").value="";await refreshSavedRoutes();};
byId("setBtn").onclick=async()=>{if(!state.waypoints.length){setOutput("Add at least 1 point first.");return;}await callApi("/api/set","POST",state.waypoints[0]);};
byId("routeBtn").onclick=async()=>{if(state.waypoints.length<2){setOutput("Route needs at least 2 points.");return;}await callApi("/api/route","POST",{waypoints:state.waypoints,config_mode:byId("configMode").value,route_mode:byId("routeMode").value,speed_kph:Number(byId("speedKph").value||"16"),step_meters:Number(byId("stepMeters").value||"2"),pause_seconds:Number(byId("pauseSeconds").value||"0"),route_source:byId("routeSource").value,route_profile:byId("routeProfile").value});await refreshRouteMonitor();};
byId("clearBtn").onclick=async()=>{await callApi("/api/clear","POST",{});await refreshRouteMonitor();};
byId("statusBtn").onclick=async()=>{await callApi("/api/status");await refreshRouteMonitor();};
byId("doctorBtn").onclick=async()=>{await callApi("/api/doctor");};
byId("configMode").onchange=syncRoutePresetFields;byId("routeMode").onchange=syncRoutePresetFields;
syncRoutePresetFields();refreshSavedRoutes();refreshRouteMonitor();
setInterval(refreshRouteMonitor,3000);setInterval(()=>{if(!state.routeMonitor||state.routeMonitor.status!=="running")return;state.routeMonitor.elapsed_seconds+=1;renderRouteMonitor(state.routeMonitor);},1000);
</script>
</body>
</html>
"""


def run_fly_command(arguments):
    command = [sys.executable, str(FLY), *arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip() or "(no output)"


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
        raise ValueError("Route requires at least 2 points.")
    if len(waypoints) > MAX_ROUTE_POINTS:
        raise ValueError(f"Route supports at most {MAX_ROUTE_POINTS} points.")

    config_mode = payload.get("config_mode", "preset")
    route_mode = payload.get("route_mode", "cycle")
    presets = {
        "cycle": {"route_profile": "cycling", "speed_kph": 16.0, "step_meters": 2.0, "route_source": "osrm", "pause_seconds": 0},
        "walk": {"route_profile": "foot", "speed_kph": 4.8, "step_meters": 2.0, "route_source": "osrm", "pause_seconds": 0},
        "car-direct": {"route_profile": "driving", "speed_kph": 100.0, "step_meters": 15.0, "route_source": "linear", "pause_seconds": 0},
        "car-road": {"route_profile": "driving", "speed_kph": 80.0, "step_meters": 5.0, "route_source": "osrm", "pause_seconds": 0},
    }

    if config_mode == "preset":
        if route_mode not in presets:
            raise ValueError("Preset mode must be one of: cycle, walk, car-direct, car-road.")
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
        raise ValueError("config_mode must be 'preset' or 'manual'.")

    start = waypoints[0]
    destination = waypoints[-1]
    command = [
        "route",
        "--from-lat", str(start["lat"]),
        "--from-lng", str(start["lng"]),
        "--lat", str(destination["lat"]),
        "--lng", str(destination["lng"]),
        "--speed-kph", str(selected["speed_kph"]),
        "--step-meters", str(selected["step_meters"]),
        "--pause-seconds", str(selected["pause_seconds"]),
        "--route-source", selected["route_source"],
        "--route-profile", selected["route_profile"],
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
    if state.get("action") != "route":
        return {"status": "idle", "label": "Idle", "elapsed_seconds": None, "started_at_label": "--", "ended_at_label": "--", "note": "No route in progress."}

    started_at = parse_state_time(state.get("updated_at"))
    session_pid = state.get("session_pid")
    running = is_pid_running(session_pid) if session_pid else False

    if state.get("route_completed"):
        return {
            "status": "completed",
            "label": "Completed",
            "elapsed_seconds": state.get("estimated_duration_seconds"),
            "started_at_label": state.get("updated_at") or "--",
            "ended_at_label": state.get("completed_at") or "--",
            "note": f"Route finished at {state.get('completed_at') or '-'}",
        }

    if running and started_at is not None:
        elapsed = max(0, (datetime.now(started_at.tzinfo) - started_at).total_seconds())
        return {"status": "running", "label": "Running", "elapsed_seconds": elapsed, "started_at_label": state.get("updated_at") or "--", "ended_at_label": "--", "note": "Background route session is active."}

    if state.get("session_active") is False and not state.get("route_completed"):
        return {"status": "stopped", "label": "Stopped", "elapsed_seconds": None, "started_at_label": state.get("updated_at") or "--", "ended_at_label": "--", "note": "Route session was stopped or cleared."}

    return {"status": "unknown", "label": "Unknown", "elapsed_seconds": None, "started_at_label": state.get("updated_at") or "--", "ended_at_label": state.get("completed_at") or "--", "note": "Unable to determine current route state."}


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
        return json.loads(self.rfile.read(length).decode("utf-8"))

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
                self._send_json({"output": "Please provide a query."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                used_query, results, attempts = geocode_with_fallback(query, limit)
            except Exception as exc:
                self._send_json({"output": f"Geocode failed: {exc}"}, HTTPStatus.BAD_GATEWAY)
                return
            self._send_json({
                "used_query": used_query,
                "attempts": attempts,
                "results": [{"display_name": item.get("display_name", "(unknown)"), "lat": float(item["lat"]), "lng": float(item["lon"])} for item in results],
                "output": f"Found {len(results)} result(s)." if results else "No geocode result.",
            })
            return

        if parsed.path == "/api/status":
            code, output = run_fly_command(["status"])
            self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/doctor":
            code, output = run_fly_command(["doctor"])
            self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/route-monitor":
            self._send_json(build_route_monitor_payload())
            return

        if parsed.path == "/api/routes":
            self._send_json({"routes": load_saved_routes(), "output": "Loaded saved routes."})
            return

        if parsed.path == "/api/routes/load":
            name = (parse_qs(parsed.query).get("name") or [""])[0].strip()
            route = get_saved_route(name)
            if route is None:
                self._send_json({"output": "Saved route not found."}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"route": route, "output": f"Loaded route: {name}"})
            return

        self._send_json({"output": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = self._read_json()
        try:
            if parsed.path == "/api/set":
                code, output = run_fly_command(["set", "--lat", str(payload["lat"]), "--lng", str(payload["lng"])])
                self._send_json({"output": output}, HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/route":
                code, output = run_fly_command(build_route_command(payload))
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
                    raise ValueError("Please provide a route name.")
                if len(waypoints) < 2:
                    raise ValueError("Need at least 2 points to save route.")
                if len(waypoints) > MAX_ROUTE_POINTS:
                    raise ValueError(f"At most {MAX_ROUTE_POINTS} points are supported.")
                route = upsert_saved_route(name, waypoints)
                self._send_json({"route": route, "output": f"Saved route: {name}"})
                return
            if parsed.path == "/api/routes/delete":
                name = (payload.get("name") or "").strip()
                if not name:
                    raise ValueError("Please provide route name to delete.")
                if not delete_saved_route(name):
                    self._send_json({"output": "Saved route not found."}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"output": f"Deleted route: {name}"})
                return
        except ValueError as exc:
            self._send_json({"output": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except RuntimeError as exc:
            self._send_json({"output": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"output": f"Unexpected error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"output": "Not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        return


def parse_args():
    parser = argparse.ArgumentParser(description="Auto Fly local web UI")
    parser.add_argument("--host", default=HOST, help="Bind host")
    parser.add_argument("--port", type=int, default=PORT, help="Bind port")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Auto Fly 已啟動: http://{args.host}:{args.port}")
    print("請用瀏覽器打開這個網址。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAuto Fly 已停止。")
