import argparse
import ctypes
import getpass
import json
import math
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LAT = 23.9593
DEFAULT_LNG = 120.5743
STATE_FILE = Path(__file__).with_name(".fly_state.json")
SESSION_LOG_FILE = Path(__file__).with_name(".fly_session.log")
ROUTE_GPX_FILE = Path(__file__).with_name(".fly_route.gpx")
KEYCHAIN_SERVICE = "moving.fly.sudo"
IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"

# Default behavior can be adjusted here if needed.
AUTO_TUNNEL_DEFAULT = True
TUNNEL_USE_SUDO_DEFAULT = IS_MACOS
TUNNEL_START_TIMEOUT_SECONDS = 20
MANUAL_RSD_HOST = None
MANUAL_RSD_PORT = None
BACKGROUND_START_GRACE_SECONDS = 3
SUDO_PASSWORD_CACHE = None
ROUTING_API_BASE = "https://router.project-osrm.org/route/v1"
ROUTE_PROFILE_DEFAULT = "cycling"
ROUTE_SPEED_KPH_DEFAULT = 15.0
MAX_ROUTE_POINTS = 5
ROUTE_MIN_POINT_INTERVAL_SECONDS = 0.2


def run_command(command):
    return subprocess.run(command, capture_output=True, text=True)


def is_windows_admin():
    if not IS_WINDOWS:
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def probe_pymobiledevice3():
    result = run_command([sys.executable, "-m", "pymobiledevice3", "version"])
    if result.returncode != 0:
        return False, result.stderr.strip() or result.stdout.strip() or "pymobiledevice3 check failed"
    return True, (result.stdout or "").strip()


def list_usbmux_devices():
    result = run_command([sys.executable, "-m", "pymobiledevice3", "usbmux", "list"])
    if result.returncode != 0:
        return None, result.stderr.strip() or result.stdout.strip() or "usbmux list failed"

    text = (result.stdout or "").strip()
    if not text:
        return [], None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, "usbmux list returned non-JSON output"

    if not isinstance(payload, list):
        return None, "usbmux list returned unexpected payload"
    return payload, None


def fly_command_hint(subcommand):
    if IS_WINDOWS:
        return f".venv311\\Scripts\\python.exe fly.py {subcommand}"
    return f"python fly.py {subcommand}"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def build_base_command():
    return [
        sys.executable,
        "-m",
        "pymobiledevice3",
        "developer",
        "dvt",
        "simulate-location",
    ]


def save_state(data):
    STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_state():
    if not STATE_FILE.exists():
        return None

    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def update_state(
    action,
    lat=None,
    lng=None,
    from_lat=None,
    from_lng=None,
    rsd_host=None,
    rsd_port=None,
    connection_mode=None,
    session_pid=None,
    tunnel_pid=None,
    session_log=None,
    session_active=None,
    **extra_fields,
):
    state = {
        "action": action,
        "lat": lat,
        "lng": lng,
        "from_lat": from_lat,
        "from_lng": from_lng,
        "rsd_host": rsd_host,
        "rsd_port": rsd_port,
        "connection_mode": connection_mode,
        "session_pid": session_pid,
        "tunnel_pid": tunnel_pid,
        "session_log": session_log,
        "session_active": session_active,
        "updated_at": utc_now(),
    }
    state.update(extra_fields)
    save_state(state)


def current_username():
    return os.environ.get("USER") or os.environ.get("LOGNAME") or "moving-user"


def read_keychain_password():
    if not IS_MACOS:
        return None
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            current_username(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


def store_keychain_password(password):
    if not IS_MACOS:
        raise RuntimeError("auth-store is only supported on macOS Keychain.")
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            current_username(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            password,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "failed to store password in Keychain"
        raise RuntimeError(message)


def delete_keychain_password():
    if not IS_MACOS:
        return False
    result = subprocess.run(
        [
            "security",
            "delete-generic-password",
            "-a",
            current_username(),
            "-s",
            KEYCHAIN_SERVICE,
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def has_keychain_password():
    return read_keychain_password() is not None


def parse_waypoint_text(value):
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Invalid waypoint format: {value}. Use 'lat,lng'.")
    lat = float(parts[0])
    lng = float(parts[1])
    validate_coordinates(lat, lng)
    return lat, lng


def print_command_error(result):
    message = result.stderr.strip() or result.stdout.strip()
    if message:
        print(message)
        return

    print(
        "No detailed error output from pymobiledevice3. "
        "Check device connectivity, trust pairing, Developer Mode, and tunnel/RSD state."
    )


def validate_coordinates(lat, lng):
    if not (-90 <= lat <= 90):
        raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90.")
    if not (-180 <= lng <= 180):
        raise ValueError(f"Invalid longitude: {lng}. Must be between -180 and 180.")


def resolve_route_start(args):
    if args.from_lat is None or args.from_lng is None:
        raise ValueError("Route requires --from-lat and --from-lng.")
    validate_coordinates(args.from_lat, args.from_lng)
    return args.from_lat, args.from_lng, "manual-start"


def normalize_route_waypoints(args):
    if args.from_lat is None or args.from_lng is None:
        raise ValueError("Route requires --from-lat and --from-lng.")

    validate_coordinates(args.from_lat, args.from_lng)
    validate_coordinates(args.lat, args.lng)
    vias = []
    for value in args.via or []:
        vias.append(parse_waypoint_text(value))

    points = [(args.from_lat, args.from_lng), *vias, (args.lat, args.lng)]
    if len(points) > MAX_ROUTE_POINTS:
        raise ValueError(f"Route supports at most {MAX_ROUTE_POINTS} points.")
    return points


def haversine_distance_m(lat1, lng1, lat2, lng2):
    radius_m = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))
def compute_path_distance_m(points):
    if len(points) < 2:
        return 0.0
    total = 0.0
    for index in range(1, len(points)):
        total += haversine_distance_m(points[index - 1][0], points[index - 1][1], points[index][0], points[index][1])
    return total


def format_duration(seconds):
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def format_distance(distance_m):
    if distance_m >= 1000:
        return f"{distance_m / 1000:.2f} km"
    return f"{distance_m:.0f} m"


def interpolate_line(start_lat, start_lng, end_lat, end_lng, step_distance_m):
    distance = haversine_distance_m(start_lat, start_lng, end_lat, end_lng)
    steps = max(1, math.ceil(distance / step_distance_m))
    points = []
    for index in range(steps + 1):
        ratio = index / steps
        lat = start_lat + (end_lat - start_lat) * ratio
        lng = start_lng + (end_lng - start_lng) * ratio
        points.append((lat, lng))
    return points


def fetch_real_route_points(waypoints, profile):
    coordinates = ";".join(f"{lng:.7f},{lat:.7f}" for lat, lng in waypoints)
    params = urllib.parse.urlencode(
        {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
            "continue_straight": "true",
        }
    )
    url = f"{ROUTING_API_BASE}/{profile}/{coordinates}?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MovingRouteHelper/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("routing service did not return any routes")

    geometry = routes[0]["geometry"]["coordinates"]
    points = [(lat, lng) for lng, lat in geometry]
    return points


def densify_path(points, step_distance_m):
    if len(points) < 2:
        return points

    dense_points = []
    for index in range(1, len(points)):
        start_lat, start_lng = points[index - 1]
        end_lat, end_lng = points[index]
        segment_points = interpolate_line(start_lat, start_lng, end_lat, end_lng, step_distance_m)
        if dense_points:
            dense_points.extend(segment_points[1:])
        else:
            dense_points.extend(segment_points)
    return dense_points


def build_route_points(waypoints, step_distance_m, route_source, route_profile):
    closed_waypoints = [*waypoints, waypoints[0]]

    if route_source == "osrm":
        try:
            road_points = fetch_real_route_points(closed_waypoints, route_profile)
            return densify_path(road_points, step_distance_m), "osrm"
        except Exception:
            pass

    points = []
    for index in range(1, len(closed_waypoints)):
        start_lat, start_lng = closed_waypoints[index - 1]
        end_lat, end_lng = closed_waypoints[index]
        segment_points = interpolate_line(start_lat, start_lng, end_lat, end_lng, step_distance_m)
        if points:
            points.extend(segment_points[1:])
        else:
            points.extend(segment_points)
    return points, "linear"


def format_gpx_timestamp(epoch_seconds):
    dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_route_gpx(path, points, speed_mps, pause_seconds_at_turnaround, return_trip):
    now = time.time()
    timestamps = []
    current_time = now

    for index, point in enumerate(points):
        if index == 0:
            timestamps.append(current_time)
            continue

        previous = points[index - 1]
        segment_distance = haversine_distance_m(previous[0], previous[1], point[0], point[1])
        current_time += max(segment_distance / speed_mps, ROUTE_MIN_POINT_INTERVAL_SECONDS)
        timestamps.append(current_time)

    if pause_seconds_at_turnaround > 0 and len(points) >= 2:
        pause_index = len(points) - 1
        if return_trip:
            pause_index = len(points) // 2
        for idx in range(pause_index, len(timestamps)):
            timestamps[idx] += pause_seconds_at_turnaround

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="fly.py" xmlns="http://www.topografix.com/GPX/1/1">',
        "  <trk>",
        "    <name>fly.py route</name>",
        "    <trkseg>",
    ]

    for (lat, lng), ts in zip(points, timestamps):
        lines.append(f'      <trkpt lat="{lat:.7f}" lon="{lng:.7f}"><time>{format_gpx_timestamp(ts)}</time></trkpt>')

    lines.extend(
        [
            "    </trkseg>",
            "  </trk>",
            "</gpx>",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return timestamps[-1] - timestamps[0] if len(timestamps) >= 2 else 0.0


def parse_rsd_line(line):
    match = re.match(r"^(\S+)\s+(\d+)$", line.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def parse_rsd_from_text(text):
    for line in text.splitlines():
        parsed = parse_rsd_line(line)
        if parsed:
            return parsed
    return None


def build_tunnel_command(use_sudo):
    command = []
    if use_sudo:
        command.extend(["sudo", "-S"])
    command.extend(
        [
            sys.executable,
            "-u",
            "-m",
            "pymobiledevice3",
            "lockdown",
            "start-tunnel",
            "--script-mode",
        ]
    )
    return command


def ensure_sudo_session():
    global SUDO_PASSWORD_CACHE

    if IS_WINDOWS:
        raise RuntimeError(
            "sudo tunnel startup is not available on Windows. "
            "Use --no-sudo-for-tunnel (or rely on default Windows behavior)."
        )
    print("準備確認 sudo 權限，讓背景 session 可以自動建立 tunnel。")
    if SUDO_PASSWORD_CACHE is None:
        SUDO_PASSWORD_CACHE = read_keychain_password()
    if SUDO_PASSWORD_CACHE is None:
        try:
            SUDO_PASSWORD_CACHE = getpass.getpass("sudo password: ")
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("目前無法互動輸入 sudo 密碼。若你使用 webui，請先執行 `python fly.py auth-store` 保存到 macOS Keychain。")

    result = subprocess.run(["sudo", "-S", "-v"], input=SUDO_PASSWORD_CACHE + "\n", text=True, capture_output=True)
    if result.returncode == 0:
        return

    keychain_password = read_keychain_password()
    if keychain_password and keychain_password == SUDO_PASSWORD_CACHE:
        try:
            SUDO_PASSWORD_CACHE = getpass.getpass("stored sudo password failed, please re-enter: ")
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("Keychain 中保存的 sudo 密碼已失效，且目前無法互動重新輸入。請先在終端機執行 `python fly.py auth-store` 更新密碼。")
        retry = subprocess.run(["sudo", "-S", "-v"], input=SUDO_PASSWORD_CACHE + "\n", text=True, capture_output=True)
        if retry.returncode == 0:
            return
        result = retry

    SUDO_PASSWORD_CACHE = None
    message = result.stderr.strip() or result.stdout.strip() or "sudo 驗證失敗"
    raise RuntimeError(f"無法取得 sudo 權限，背景模擬定位 session 無法啟動。\n{message}")


def terminate_process(process):
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def is_pid_running(pid):
    if not pid:
        return False

    if IS_WINDOWS:
        # Use Win32 APIs for reliable process liveness checks on Windows.
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            return False

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_int)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if not ok:
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_session_pid(pid):
    terminate_pid(pid)


def terminate_pid(pid):
    if not pid:
        return

    if IS_WINDOWS:
        # Windows has no os.killpg; ask taskkill to terminate the process tree.
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not is_pid_running(pid):
            return
        time.sleep(0.2)

    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def start_tunnel(use_sudo):
    global SUDO_PASSWORD_CACHE

    if use_sudo and IS_WINDOWS:
        raise RuntimeError("Windows does not support sudo tunnel startup. Use --no-sudo-for-tunnel.")
    if IS_WINDOWS and not is_windows_admin():
        raise RuntimeError(
            "Windows tunnel startup requires Administrator privileges.\n"
            "Reopen PowerShell as Administrator, then rerun your set/route command."
        )

    command = build_tunnel_command(use_sudo)
    print("Starting tunnel to acquire a fresh RSD endpoint...")
    print("Command:", " ".join(command))

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if use_sudo else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        bufsize=0,
        start_new_session=True,
    )

    collected_chunks = []
    deadline = time.monotonic() + TUNNEL_START_TIMEOUT_SECONDS

    if use_sudo:
        if SUDO_PASSWORD_CACHE is None:
            raise RuntimeError("sudo password is not prepared; cannot start tunnel.")
        process.stdin.write((SUDO_PASSWORD_CACHE + "\n").encode("utf-8"))
        process.stdin.flush()
        process.stdin.close()

    output_queue = queue.Queue()

    def _read_output_stream(stream):
        try:
            while True:
                chunk = os.read(stream.fileno(), 4096)
                if not chunk:
                    break
                output_queue.put(chunk)
        except Exception:
            pass
        finally:
            output_queue.put(None)

    if process.stdout is not None:
        threading.Thread(target=_read_output_stream, args=(process.stdout,), daemon=True).start()

    stream_closed = False
    while time.monotonic() < deadline:
        if process.poll() is not None and stream_closed:
            break
        try:
            chunk = output_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if chunk is None:
            stream_closed = True
            continue

        collected_chunks.append(chunk)
        output = b"".join(collected_chunks).decode("utf-8", errors="replace")
        parsed = parse_rsd_from_text(output)
        if parsed:
            rsd_host, rsd_port = parsed
            print(f"Tunnel ready. RSD: {rsd_host} {rsd_port}")
            return process, rsd_host, rsd_port

    output = b"".join(collected_chunks).decode("utf-8", errors="replace").strip()
    if process.poll() is not None:
        if IS_WINDOWS and "requires admin privileges" in output.lower():
            output += "\n\nTip: run PowerShell as Administrator and retry."
        raise RuntimeError("Failed to start tunnel.\n" + (output or "No output."))

    terminate_process(process)
    raise RuntimeError("Tunnel startup timed out; no RSD detected.\n" + (output or "No parseable output."))
def resolve_manual_rsd(args):
    rsd_host = args.rsd_host if args.rsd_host is not None else MANUAL_RSD_HOST
    rsd_port = args.rsd_port if args.rsd_port is not None else MANUAL_RSD_PORT
    if (rsd_host is None) != (rsd_port is None):
        raise ValueError("Manual RSD requires both --rsd-host and --rsd-port.")
    return rsd_host, rsd_port


@contextmanager
def rsd_session(args):
    manual_rsd_host, manual_rsd_port = resolve_manual_rsd(args)
    tunnel_process = None

    try:
        if manual_rsd_host and manual_rsd_port:
            yield manual_rsd_host, str(manual_rsd_port), "manual-rsd"
            return

        if not args.auto_tunnel:
            raise ValueError("No manual RSD provided and auto-tunnel is disabled.")

        tunnel_process, rsd_host, rsd_port = start_tunnel(use_sudo=args.tunnel_use_sudo)
        yield rsd_host, rsd_port, "auto-tunnel"
    finally:
        terminate_process(tunnel_process)


def build_hold_set_command(lat, lng, rsd_host, rsd_port):
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "_hold-set",
        "--lat",
        str(lat),
        "--lng",
        str(lng),
        "--no-auto-tunnel",
        "--rsd-host",
        str(rsd_host),
        "--rsd-port",
        str(rsd_port),
    ]


def build_hold_play_command(gpx_file, rsd_host, rsd_port):
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "_hold-play",
        "--gpx-file",
        str(gpx_file),
        "--no-auto-tunnel",
        "--rsd-host",
        str(rsd_host),
        "--rsd-port",
        str(rsd_port),
    ]
def run_clear_command(rsd_host, rsd_port):
    command = [
        *build_base_command(),
        "clear",
        "--rsd",
        rsd_host,
        rsd_port,
    ]
    print("準備停止模擬定位，恢復 iPhone 正常 GPS。")
    print("執行指令:", " ".join(command))
    return run_command(command)


def start_set_session(args):
    validate_coordinates(args.lat, args.lng)

    existing_state = load_state()
    if existing_state and existing_state.get("session_active") and is_pid_running(existing_state.get("session_pid")):
        raise RuntimeError(
            "A simulated-location session is already running.\n"
            f"PID: {existing_state['session_pid']}\n"
            f"Run `{fly_command_hint('clear')}` before starting another set session."
        )

    tunnel_process = None
    rsd_host = None
    rsd_port = None
    connection_mode = "manual-rsd-session"

    if args.auto_tunnel:
        if args.tunnel_use_sudo:
            ensure_sudo_session()
        tunnel_process, rsd_host, rsd_port = start_tunnel(use_sudo=args.tunnel_use_sudo)
        connection_mode = "auto-tunnel-session"
    else:
        rsd_host, rsd_port = resolve_manual_rsd(args)
        if not rsd_host or not rsd_port:
            raise ValueError("When auto-tunnel is disabled, you must provide --rsd-host and --rsd-port.")

    command = build_hold_set_command(args.lat, args.lng, rsd_host, rsd_port)
    log_handle = SESSION_LOG_FILE.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    log_handle.close()

    start_grace_seconds = max(BACKGROUND_START_GRACE_SECONDS, 7 if IS_WINDOWS else BACKGROUND_START_GRACE_SECONDS)
    deadline = time.monotonic() + start_grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log_text = ""
            if SESSION_LOG_FILE.exists():
                log_text = SESSION_LOG_FILE.read_text(encoding="utf-8", errors="replace").strip()
            terminate_process(tunnel_process)
            raise RuntimeError(
                "Background set session exited during startup.\n"
                f"{log_text or 'Check .fly_session.log for details.'}"
            )
        time.sleep(0.2)

    update_state(
        "set",
        lat=args.lat,
        lng=args.lng,
        rsd_host=rsd_host,
        rsd_port=rsd_port,
        connection_mode=connection_mode,
        session_pid=process.pid,
        tunnel_pid=tunnel_process.pid if tunnel_process else None,
        session_log=str(SESSION_LOG_FILE),
        session_active=True,
    )

    print(f"Set session started in background. PID: {process.pid}")
    print(f"Target coordinates: {args.lat}, {args.lng}")
    print(f"Session log: {SESSION_LOG_FILE}")
    print(f"To stop simulation: {fly_command_hint('clear')}")


def start_route_session(args):
    existing_state = load_state()
    if existing_state and existing_state.get("session_active") and is_pid_running(existing_state.get("session_pid")):
        raise RuntimeError(
            "A simulated-location session is already running.\n"
            f"PID: {existing_state['session_pid']}\n"
            f"Run `{fly_command_hint('clear')}` before starting a route session."
        )

    waypoints = normalize_route_waypoints(args)
    start_lat, start_lng = waypoints[0]
    step_distance_m = max(args.step_meters, 1)
    speed_kph = max(args.speed_kph, 0.1)
    speed_mps = speed_kph / 3.6
    points, route_source_used = build_route_points(waypoints, step_distance_m, args.route_source, args.route_profile)
    total_distance_m = compute_path_distance_m(points)
    estimated_duration_seconds = write_route_gpx(ROUTE_GPX_FILE, points, speed_mps, args.pause_seconds, False)

    tunnel_process = None
    rsd_host = None
    rsd_port = None
    connection_mode = "route-manual-start"

    if args.auto_tunnel:
        if args.tunnel_use_sudo:
            ensure_sudo_session()
        tunnel_process, rsd_host, rsd_port = start_tunnel(use_sudo=args.tunnel_use_sudo)
        connection_mode = "auto-tunnel-route-manual-start"
    else:
        rsd_host, rsd_port = resolve_manual_rsd(args)
        if not rsd_host or not rsd_port:
            raise ValueError("When auto-tunnel is disabled, you must provide --rsd-host and --rsd-port.")

    command = build_hold_play_command(ROUTE_GPX_FILE, rsd_host, rsd_port)
    if tunnel_process:
        command.extend(["--tunnel-pid", str(tunnel_process.pid)])
    log_handle = SESSION_LOG_FILE.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    log_handle.close()

    start_grace_seconds = max(BACKGROUND_START_GRACE_SECONDS, 7 if IS_WINDOWS else BACKGROUND_START_GRACE_SECONDS)
    deadline = time.monotonic() + start_grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log_text = ""
            if SESSION_LOG_FILE.exists():
                log_text = SESSION_LOG_FILE.read_text(encoding="utf-8", errors="replace").strip()
            terminate_process(tunnel_process)
            raise RuntimeError(
                "Background route session exited during startup.\n"
                f"{log_text or 'Check .fly_session.log for details.'}"
            )
        time.sleep(0.2)

    update_state(
        "route",
        lat=start_lat,
        lng=start_lng,
        from_lat=start_lat,
        from_lng=start_lng,
        rsd_host=rsd_host,
        rsd_port=rsd_port,
        connection_mode=connection_mode,
        session_pid=process.pid,
        tunnel_pid=tunnel_process.pid if tunnel_process else None,
        session_log=str(SESSION_LOG_FILE),
        session_active=True,
        route_mode="manual-waypoints",
        route_profile=args.route_profile,
        route_source_requested=args.route_source,
        route_source_used=route_source_used,
        speed_kph=speed_kph,
        distance_m=round(total_distance_m, 2),
        estimated_duration_seconds=round(estimated_duration_seconds, 2),
        route_completed=False,
        target_lat=args.lat,
        target_lng=args.lng,
        waypoints=[{"lat": lat, "lng": lng} for lat, lng in waypoints],
        waypoint_count=len(waypoints),
    )

    labels = [chr(ord("A") + index) for index in range(len(waypoints))]
    trip_label = " -> ".join(labels + ["A"])
    print(f"Route session started in background. PID: {process.pid}")
    print(f"Waypoint order: {trip_label}")
    for index, (lat, lng) in enumerate(waypoints):
        print(f"Point {labels[index]}: {lat}, {lng}")
    print(f"Route source used: {route_source_used}")
    print(f"Speed: {speed_kph:.1f} km/h")
    print(f"Distance: {format_distance(total_distance_m)}")
    print(f"Estimated duration: {format_duration(estimated_duration_seconds)}")
    print(f"Generated GPX: {ROUTE_GPX_FILE}")
    print(f"Session log: {SESSION_LOG_FILE}")
    print(f"To stop simulation: {fly_command_hint('clear')}")

def hold_set_session(args):
    validate_coordinates(args.lat, args.lng)
    rsd_host, rsd_port = resolve_manual_rsd(args)
    if not rsd_host or not rsd_port:
        raise ValueError("_hold-set requires --rsd-host and --rsd-port.")

    command = [
        *build_base_command(),
        "set",
        "--rsd",
        rsd_host,
        str(rsd_port),
        "--",
        str(args.lat),
        str(args.lng),
    ]

    print(f"Preparing simulated location set: {args.lat}, {args.lng}", flush=True)
    print("This hold session stays alive until clear is called.", flush=True)
    print("Command:", " ".join(command), flush=True)

    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=sys.stdout,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.monotonic() + max(BACKGROUND_START_GRACE_SECONDS, 6)
    while time.monotonic() < deadline:
        if child.poll() is not None:
            print("simulate-location set failed during startup.", flush=True)
            sys.exit(child.returncode or 1)
        time.sleep(0.2)

    print("simulate-location set is now holding.", flush=True)
    try:
        child.wait()
    except KeyboardInterrupt:
        terminate_process(child)

def hold_play_session(args):
    rsd_host, rsd_port = resolve_manual_rsd(args)
    if not rsd_host or not rsd_port:
        raise ValueError("_hold-play requires --rsd-host and --rsd-port.")

    command = [
        *build_base_command(),
        "play",
        "--rsd",
        rsd_host,
        str(rsd_port),
        str(args.gpx_file),
    ]

    print(f"Starting GPX playback: {args.gpx_file}", flush=True)
    print("This session runs until playback completes or clear is called.", flush=True)
    print("Command:", " ".join(command), flush=True)

    result = run_command(command)
    if result.returncode == 0:
        if args.tunnel_pid:
            terminate_pid(args.tunnel_pid)
        previous_state = load_state() or {}
        update_state(
            "route",
            lat=previous_state.get("from_lat"),
            lng=previous_state.get("from_lng"),
            from_lat=previous_state.get("from_lat"),
            from_lng=previous_state.get("from_lng"),
            rsd_host=previous_state.get("rsd_host"),
            rsd_port=previous_state.get("rsd_port"),
            connection_mode=previous_state.get("connection_mode"),
            session_pid=None,
            tunnel_pid=None,
            session_log=str(SESSION_LOG_FILE),
            session_active=False,
            route_mode=previous_state.get("route_mode"),
            route_profile=previous_state.get("route_profile"),
            route_source_requested=previous_state.get("route_source_requested"),
            route_source_used=previous_state.get("route_source_used"),
            speed_kph=previous_state.get("speed_kph"),
            distance_m=previous_state.get("distance_m"),
            estimated_duration_seconds=previous_state.get("estimated_duration_seconds"),
            route_completed=True,
            completed_at=utc_now(),
            completion_message="route finished and returned to the first waypoint",
            target_lat=previous_state.get("target_lat"),
            target_lng=previous_state.get("target_lng"),
            waypoints=previous_state.get("waypoints"),
            waypoint_count=previous_state.get("waypoint_count"),
        )
        send_completion_notification("fly.py route finished", "Route playback completed.")
        print("simulate-location play finished.", flush=True)
        return

    print("simulate-location play failed.", flush=True)
    if args.tunnel_pid:
        terminate_pid(args.tunnel_pid)
    print_command_error(result)
    sys.exit(result.returncode)
def send_completion_notification(title, message):
    if not IS_MACOS:
        return
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    except Exception:
        pass


def clear_location(args):
    state = load_state()
    existing_pid = state.get("session_pid") if state else None
    existing_tunnel_pid = state.get("tunnel_pid") if state else None
    state_rsd_host = state.get("rsd_host") if state else None
    state_rsd_port = state.get("rsd_port") if state else None

    used_existing_rsd = False
    if state_rsd_host and state_rsd_port and (existing_tunnel_pid is None or is_pid_running(existing_tunnel_pid)):
        rsd_context = None
        rsd_values = (state_rsd_host, str(state_rsd_port), "existing-session-rsd")
        used_existing_rsd = True
    else:
        rsd_context = rsd_session(args)
        rsd_values = rsd_context.__enter__()

    try:
        rsd_host, rsd_port, connection_mode = rsd_values
        result = run_clear_command(rsd_host, rsd_port)

        if result.returncode != 0 and used_existing_rsd and args.auto_tunnel:
            print("Existing RSD failed; retrying clear with a fresh tunnel.")
            if args.tunnel_use_sudo:
                ensure_sudo_session()
            retry_context = rsd_session(args)
            retry_rsd_host, retry_rsd_port, retry_connection_mode = retry_context.__enter__()
            try:
                retry_result = run_clear_command(retry_rsd_host, retry_rsd_port)
                if retry_result.returncode == 0:
                    rsd_host, rsd_port, connection_mode = retry_rsd_host, retry_rsd_port, retry_connection_mode
                result = retry_result
            finally:
                retry_context.__exit__(None, None, None)

        if result.returncode == 0:
            if existing_pid and is_pid_running(existing_pid):
                print(f"Stopping background session PID: {existing_pid}")
                terminate_session_pid(existing_pid)
            if existing_tunnel_pid and is_pid_running(existing_tunnel_pid):
                print(f"Stopping tunnel PID: {existing_tunnel_pid}")
                terminate_pid(existing_tunnel_pid)
            update_state(
                "clear",
                rsd_host=rsd_host,
                rsd_port=rsd_port,
                connection_mode=connection_mode,
                session_pid=None,
                tunnel_pid=None,
                session_log=str(SESSION_LOG_FILE),
                session_active=False,
            )
            print("Simulated location cleared. Device should be back to real GPS.")
            return

        print("Failed to clear simulated location.")
        print_command_error(result)
        sys.exit(result.returncode)
    finally:
        if rsd_context is not None:
            rsd_context.__exit__(None, None, None)


def show_status():
    state = load_state()
    if state is None:
        print("No local state found yet.")
        print("This only means fly.py has not written a state file on this machine.")
        return

    pid = state.get("session_pid")
    tunnel_pid = state.get("tunnel_pid")
    running = is_pid_running(pid) if pid else False
    tunnel_running = is_pid_running(tunnel_pid) if tunnel_pid else False
    state["session_pid_running"] = running
    state["tunnel_pid_running"] = tunnel_running

    if state.get("session_active") and pid and not running:
        state["session_active"] = False

    print("Last local fly.py state:")
    print(json.dumps(state, indent=2, ensure_ascii=False))

    if state["action"] == "set" and state.get("session_active") and running:
        print("Interpretation: set session is still running.")
        print(f"To restore real GPS: {fly_command_hint('clear')}")
    elif state["action"] == "route" and state.get("session_active") and running:
        print("Interpretation: route session is still running.")
        print(f"To restore real GPS: {fly_command_hint('clear')}")
        if state.get("waypoint_count"):
            print(f"Waypoint count: {state['waypoint_count']} (route ends back at A)")
        if state.get("estimated_duration_seconds"):
            print(f"Estimated duration: {format_duration(state['estimated_duration_seconds'])}")
        if state.get("distance_m"):
            print(f"Estimated distance: {format_distance(state['distance_m'])}")
    elif state["action"] == "set":
        print("Interpretation: last action was set, but session is not running now.")
        print(f"If phone still shows simulated GPS, run: {fly_command_hint('clear')}")
    elif state["action"] == "route":
        if state.get("route_completed"):
            print("Interpretation: route session completed.")
            if state.get("completed_at"):
                print(f"Completed at: {state['completed_at']}")
        else:
            print("Interpretation: last action was route, but session is not running now.")
            print(f"If phone still shows simulated GPS, run: {fly_command_hint('clear')}")
    else:
        print("Interpretation: last action was clear.")


def run_doctor(args):
    manual_rsd_host, manual_rsd_port = resolve_manual_rsd(args)
    pmd3_ok, pmd3_info = probe_pymobiledevice3()
    devices, devices_error = list_usbmux_devices()
    windows_admin_ok = is_windows_admin() if IS_WINDOWS else True

    print("Current configuration:")
    print(f"- Python executable: {sys.executable}")
    print(f"- auto_tunnel: {args.auto_tunnel}")
    print(f"- tunnel_use_sudo: {args.tunnel_use_sudo}")
    print(f"- manual_rsd_host: {manual_rsd_host or '(not set)'}")
    print(f"- manual_rsd_port: {manual_rsd_port or '(not set)'}")
    print(f"- tunnel_timeout_seconds: {TUNNEL_START_TIMEOUT_SECONDS}")
    print(f"- state_file: {STATE_FILE}")
    print(f"- session_log_file: {SESSION_LOG_FILE}")
    if IS_WINDOWS:
        print(f"- windows_admin: {'yes' if windows_admin_ok else 'no'}")

    print()
    print("Quick readiness checks:")
    print(f"- pymobiledevice3: {'ok' if pmd3_ok else 'failed'}")
    print(f"  detail: {pmd3_info}")
    if devices_error:
        print("- device_detect: failed")
        print(f"  detail: {devices_error}")
    else:
        print(f"- device_detect: {len(devices)} device(s)")
        for device in devices:
            name = device.get("DeviceName", "(unknown)")
            conn_type = device.get("ConnectionType", "(unknown)")
            ios_version = device.get("ProductVersion", "?")
            print(f"  - {name} / iOS {ios_version} / {conn_type}")

    if IS_WINDOWS:
        print(f"- windows_ready_for_tunnel: {'yes' if (windows_admin_ok and pmd3_ok) else 'no'}")
        if not windows_admin_ok:
            print("  action: reopen PowerShell as Administrator")
        if devices is not None and len(devices) == 0:
            print("  action: reconnect iPhone and accept Trust prompt")

    print()
    print("Recommended troubleshooting order:")
    print(f"1. {fly_command_hint('status')}")
    print(f"2. Inspect session log: {SESSION_LOG_FILE}")
    print(f"3. {fly_command_hint('clear')}")


def add_connection_options(parser):
    parser.add_argument(
        "--no-auto-tunnel",
        dest="auto_tunnel",
        action="store_false",
        help="Disable automatic tunnel creation. You must provide --rsd-host and --rsd-port.",
    )
    parser.add_argument(
        "--no-sudo-for-tunnel",
        dest="tunnel_use_sudo",
        action="store_false",
        help="Do not use sudo when auto-starting tunnel.",
    )
    parser.add_argument("--rsd-host", default=None, help="Use a manual RSD host instead of auto-starting tunnel.")
    parser.add_argument("--rsd-port", default=None, help="Use a manual RSD port instead of auto-starting tunnel.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Simulate or clear iPhone GPS location on iOS 18+ with pymobiledevice3 DVT."
    )
    parser.set_defaults(auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(parser)
    subparsers = parser.add_subparsers(dest="action")

    set_parser = subparsers.add_parser("set", help="Start a background simulated location session")
    set_parser.set_defaults(auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(set_parser)
    set_parser.add_argument("--lat", type=float, required=True, help="Target latitude")
    set_parser.add_argument("--lng", type=float, required=True, help="Target longitude")

    route_parser = subparsers.add_parser("route", help="Start a background moving route session")
    route_parser.set_defaults(auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(route_parser)
    route_parser.add_argument("--lat", type=float, required=True, help="Destination latitude")
    route_parser.add_argument("--lng", type=float, required=True, help="Destination longitude")
    route_parser.add_argument("--from-lat", type=float, required=True, help="Route start latitude")
    route_parser.add_argument("--from-lng", type=float, required=True, help="Route start longitude")
    route_parser.add_argument("--via", action="append", default=[], help="Intermediate waypoint in 'lat,lng' format. Repeat up to 3 times.")
    route_parser.add_argument("--speed-kph", type=float, default=ROUTE_SPEED_KPH_DEFAULT, help="Movement speed in kilometers per hour")
    route_parser.add_argument("--step-meters", type=float, default=5.0, help="Approximate meters between route points")
    route_parser.add_argument("--pause-seconds", type=float, default=0.0, help="Pause duration at turnaround")
    route_parser.add_argument("--route-source", choices=["osrm", "linear"], default="osrm", help="Route generation source")
    route_parser.add_argument("--route-profile", choices=["foot", "cycling", "driving"], default=ROUTE_PROFILE_DEFAULT, help="Routing profile for road route generation")

    if IS_MACOS:
        auth_status_parser = subparsers.add_parser("auth-status", help="Show whether a sudo password is stored in macOS Keychain")
        auth_status_parser.set_defaults(action="auth-status")
        auth_store_parser = subparsers.add_parser("auth-store", help="Store sudo password in macOS Keychain for future tunnel startup")
        auth_store_parser.set_defaults(action="auth-store")
        auth_clear_parser = subparsers.add_parser("auth-clear", help="Delete stored sudo password from macOS Keychain")
        auth_clear_parser.set_defaults(action="auth-clear")

    hold_set_parser = subparsers.add_parser("_hold-set", help=argparse.SUPPRESS)
    hold_set_parser.set_defaults(auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(hold_set_parser)
    hold_set_parser.add_argument("--lat", type=float, required=True)
    hold_set_parser.add_argument("--lng", type=float, required=True)

    hold_play_parser = subparsers.add_parser("_hold-play", help=argparse.SUPPRESS)
    hold_play_parser.set_defaults(auto_tunnel=False, tunnel_use_sudo=False)
    add_connection_options(hold_play_parser)
    hold_play_parser.add_argument("--gpx-file", required=True)
    hold_play_parser.add_argument("--tunnel-pid", type=int, default=None)

    clear_parser = subparsers.add_parser("clear", help="Clear simulated location and restore real GPS")
    clear_parser.set_defaults(action="clear", auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(clear_parser)

    status_parser = subparsers.add_parser("status", help="Show last local state recorded by this script")
    status_parser.set_defaults(action="status", auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(status_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Show validation tips and current script config")
    doctor_parser.set_defaults(action="doctor", auto_tunnel=AUTO_TUNNEL_DEFAULT, tunnel_use_sudo=TUNNEL_USE_SUDO_DEFAULT)
    add_connection_options(doctor_parser)

    parser.set_defaults(action="set", lat=DEFAULT_LAT, lng=DEFAULT_LNG)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        if args.action == "clear":
            clear_location(args)
        elif args.action == "auth-status":
            if not IS_MACOS:
                raise RuntimeError("auth-status is only supported on macOS.")
            print("macOS Keychain password is stored." if has_keychain_password() else "No stored macOS Keychain password.")
        elif args.action == "auth-store":
            if not IS_MACOS:
                raise RuntimeError("auth-store is only supported on macOS.")
            password = getpass.getpass("Enter sudo password to store in macOS Keychain: ")
            if not password:
                raise ValueError("Password cannot be empty.")
            result = subprocess.run(["sudo", "-S", "-v"], input=password + "\n", text=True, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "sudo validation failed")
            store_keychain_password(password)
            SUDO_PASSWORD_CACHE = password
            print("Stored sudo password in macOS Keychain.")
        elif args.action == "auth-clear":
            if not IS_MACOS:
                raise RuntimeError("auth-clear is only supported on macOS.")
            print("Deleted stored sudo password." if delete_keychain_password() else "No stored password to delete.")
        elif args.action == "status":
            show_status()
        elif args.action == "doctor":
            run_doctor(args)
        elif args.action == "_hold-set":
            hold_set_session(args)
        elif args.action == "_hold-play":
            hold_play_session(args)
        elif args.action == "route":
            start_route_session(args)
        else:
            start_set_session(args)
    except ValueError as exc:
        print(str(exc))
        sys.exit(2)
    except RuntimeError as exc:
        print(str(exc))
        sys.exit(1)
