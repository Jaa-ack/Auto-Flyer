import argparse
import ctypes
import getpass
import json
import math
import os
import queue
import re
import select
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
        raise RuntimeError("auth-store is only supported on macOS.")
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
        raise ValueError(f"無法解析 waypoint: {value}，格式必須為 'lat,lng'")
    lat = float(parts[0])
    lng = float(parts[1])
    validate_coordinates(lat, lng)
    return lat, lng


def print_command_error(result):
    message = result.stderr.strip() or result.stdout.strip()
    if message:
        print(message)
        return

    print("沒有收到 pymobiledevice3 的錯誤輸出，請確認 iPhone 仍在線、Developer Mode 已開啟，且 tunnel / RSD 仍有效。")


def validate_coordinates(lat, lng):
    if not (-90 <= lat <= 90):
        raise ValueError(f"緯度超出範圍: {lat}，必須介於 -90 到 90。")
    if not (-180 <= lng <= 180):
        raise ValueError(f"經度超出範圍: {lng}，必須介於 -180 到 180。")


def resolve_route_start(args):
    if args.from_lat is None or args.from_lng is None:
        raise ValueError("路線模式需要明確起點。請同時提供 --from-lat 與 --from-lng。")
    validate_coordinates(args.from_lat, args.from_lng)
    return args.from_lat, args.from_lng, "manual-start"


def normalize_route_waypoints(args):
    if args.from_lat is None or args.from_lng is None:
        raise ValueError("路線模式需要明確起點。請同時提供 --from-lat 與 --from-lng。")

    validate_coordinates(args.from_lat, args.from_lng)
    validate_coordinates(args.lat, args.lng)
    vias = []
    for value in args.via or []:
        vias.append(parse_waypoint_text(value))

    points = [(args.from_lat, args.from_lng), *vias, (args.lat, args.lng)]
    if len(points) > MAX_ROUTE_POINTS:
        raise ValueError(f"路線最多只支援 {MAX_ROUTE_POINTS} 個點（包含起點與終點）。")
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
            "User-Agent": "AutoFlyRouteHelper/1.0",
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
        raise RuntimeError("Windows does not use sudo tunnel startup. Run the terminal as Administrator instead.")

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
        raise RuntimeError("Windows does not support sudo tunnel startup. Run the terminal as Administrator.")
    if IS_WINDOWS and not is_windows_admin():
        raise RuntimeError(
            "Windows tunnel startup requires Administrator privileges.\n"
            "請用系統管理員權限重新開啟 PowerShell 或 Terminal 後再重試。"
        )

    command = build_tunnel_command(use_sudo)
    print("準備自動啟動 tunnel 以取得本次有效的 RSD 位址。")
    if use_sudo:
        print("這一步通常需要 sudo，終端機可能會要求你輸入密碼。")
    print("執行指令:", " ".join(command))

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
            raise RuntimeError("尚未準備 sudo 密碼，無法啟動 tunnel。")
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
            print(f"已取得本次 tunnel 的 RSD: {rsd_host} {rsd_port}")
            return process, rsd_host, rsd_port

    output = b"".join(collected_chunks).decode("utf-8", errors="replace").strip()
    if process.poll() is not None:
        raise RuntimeError(
            "自動啟動 tunnel 失敗。\n"
            f"{output or '沒有收到可用輸出。'}"
        )

    terminate_process(process)
    raise RuntimeError(
        "等待 tunnel 啟動逾時，未能取得 RSD_HOST / RSD_PORT。\n"
        f"{output or '沒有收到可解析的輸出。'}"
    )


def resolve_manual_rsd(args):
    rsd_host = args.rsd_host if args.rsd_host is not None else MANUAL_RSD_HOST
    rsd_port = args.rsd_port if args.rsd_port is not None else MANUAL_RSD_PORT
    if (rsd_host is None) != (rsd_port is None):
        raise ValueError("手動指定 RSD 時，必須同時提供 rsd_host 與 rsd_port。")
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
            raise ValueError("目前未提供手動 RSD，且已停用自動 tunnel，無法連線到 iPhone。")

        tunnel_process, rsd_host, rsd_port = start_tunnel(use_sudo=args.tunnel_use_sudo)
        yield rsd_host, rsd_port, "auto-tunnel"
    finally:
        terminate_process(tunnel_process)


def build_hold_set_command(lat, lng, rsd_host, rsd_port):
    command = [
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
    return command


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
            "目前已有模擬定位 session 在執行。\n"
            f"PID: {existing_state['session_pid']}\n"
            "請先執行 `python fly.py clear` 後再重新 set。"
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
            raise ValueError("停用自動 tunnel 時，必須提供 --rsd-host 與 --rsd-port。")

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

    deadline = time.monotonic() + BACKGROUND_START_GRACE_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log_text = ""
            if SESSION_LOG_FILE.exists():
                log_text = SESSION_LOG_FILE.read_text(encoding="utf-8", errors="replace").strip()
            terminate_process(tunnel_process)
            raise RuntimeError(
                "背景模擬定位 session 啟動失敗。\n"
                f"{log_text or '請檢查 .fly_session.log 取得詳細錯誤。'}"
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

    print(f"已在背景啟動模擬定位 session，PID: {process.pid}")
    print(f"目標座標: {args.lat}, {args.lng}")
    print(f"背景日誌: {SESSION_LOG_FILE}")
    print("若要停止模擬定位，請執行: python fly.py clear")


def start_route_session(args):
    existing_state = load_state()
    if existing_state and existing_state.get("session_active") and is_pid_running(existing_state.get("session_pid")):
        raise RuntimeError(
            "目前已有模擬定位 session 在執行。\n"
            f"PID: {existing_state['session_pid']}\n"
            "請先執行 `python fly.py clear` 後再重新 route。"
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
            raise ValueError("停用自動 tunnel 時，必須提供 --rsd-host 與 --rsd-port。")

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

    deadline = time.monotonic() + BACKGROUND_START_GRACE_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log_text = ""
            if SESSION_LOG_FILE.exists():
                log_text = SESSION_LOG_FILE.read_text(encoding="utf-8", errors="replace").strip()
            terminate_process(tunnel_process)
            raise RuntimeError(
                "背景路線模擬 session 啟動失敗。\n"
                f"{log_text or '請檢查 .fly_session.log 取得詳細錯誤。'}"
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
        route_mode="closed-loop",
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
    print(f"已在背景啟動路線模擬 session，PID: {process.pid}")
    print(f"路線模式: {trip_label}")
    for index, (lat, lng) in enumerate(waypoints):
        print(f"點位 {labels[index]}: {lat}, {lng}")
    print(f"路線來源: {route_source_used}")
    print(f"移動速度: {speed_kph:.1f} km/h")
    print(f"總距離: {format_distance(total_distance_m)}")
    print(f"預估完成時間: {format_duration(estimated_duration_seconds)}")
    print(f"GPX 路徑檔: {ROUTE_GPX_FILE}")
    print(f"背景日誌: {SESSION_LOG_FILE}")
    print("若要停止模擬定位，請執行: python fly.py clear")


def hold_set_session(args):
    validate_coordinates(args.lat, args.lng)
    rsd_host, rsd_port = resolve_manual_rsd(args)
    if not rsd_host or not rsd_port:
        raise ValueError("_hold-set 需要明確的 --rsd-host 與 --rsd-port。")

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

    print(f"準備將 iPhone 模擬定位到座標: {args.lat}, {args.lng}", flush=True)
    print("這是 simulated location，這個背景 session 會保持執行，直到你執行 clear。", flush=True)
    print("執行指令:", " ".join(command), flush=True)

    result = run_command(command)
    if result.returncode == 0:
        print("simulate-location set 已啟動，session 將保持執行。", flush=True)
        return

    print("設定模擬定位失敗，錯誤訊息如下：", flush=True)
    print_command_error(result)
    sys.exit(result.returncode)


def hold_play_session(args):
    rsd_host, rsd_port = resolve_manual_rsd(args)
    if not rsd_host or not rsd_port:
        raise ValueError("_hold-play 需要明確的 --rsd-host 與 --rsd-port。")

    command = [
        *build_base_command(),
        "play",
        "--rsd",
        rsd_host,
        str(rsd_port),
        str(args.gpx_file),
    ]

    print(f"準備重播 GPX 路線: {args.gpx_file}", flush=True)
    print("這個背景 session 會持續依路線移動，直到你執行 clear 或路線播完。", flush=True)
    print("執行指令:", " ".join(command), flush=True)

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
        send_completion_notification(
            "fly.py route finished",
            "Route playback completed and returned to the first waypoint.",
        )
        print("simulate-location play 已完成，路線已播放結束。", flush=True)
        return

    print("路線模擬失敗，錯誤訊息如下：", flush=True)
    if args.tunnel_pid:
        terminate_pid(args.tunnel_pid)
    print_command_error(result)
    sys.exit(result.returncode)


def send_completion_notification(title, message):
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
            print("現有 RSD 無法連線，改用新的 tunnel 重新嘗試 clear。")
            if args.tunnel_use_sudo:
                ensure_sudo_session()
            retry_context = rsd_session(args)
            retry_rsd_host, retry_rsd_port, retry_connection_mode = retry_context.__enter__()
            try:
                retry_result = run_clear_command(retry_rsd_host, retry_rsd_port)
                if retry_result.returncode == 0:
                    rsd_host, rsd_port, connection_mode = retry_rsd_host, retry_rsd_port, retry_connection_mode
                    result = retry_result
                else:
                    result = retry_result
            finally:
                retry_context.__exit__(None, None, None)

        if result.returncode == 0:
            if existing_pid and is_pid_running(existing_pid):
                print(f"終止背景模擬定位 session，PID: {existing_pid}")
                terminate_session_pid(existing_pid)
            if existing_tunnel_pid and is_pid_running(existing_tunnel_pid):
                print(f"終止背景 tunnel session，PID: {existing_tunnel_pid}")
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
            print("已停止模擬定位，iPhone 應恢復真實位置。")
            return

        print("停止模擬定位失敗，錯誤訊息如下：")
        print_command_error(result)
        sys.exit(result.returncode)
    finally:
        if rsd_context is not None:
            rsd_context.__exit__(None, None, None)


def show_status():
    state = load_state()
    if state is None:
        print("本機尚未記錄任何 set / clear 操作。")
        print("這不代表 iPhone 一定沒有模擬定位，只代表這支腳本尚未留下狀態檔。")
        return

    pid = state.get("session_pid")
    tunnel_pid = state.get("tunnel_pid")
    running = is_pid_running(pid) if pid else False
    tunnel_running = is_pid_running(tunnel_pid) if tunnel_pid else False
    state["session_pid_running"] = running
    state["tunnel_pid_running"] = tunnel_running

    if state.get("session_active") and pid and not running:
        state["session_active"] = False

    print("本機最後一次送出的定位命令：")
    print(json.dumps(state, indent=2, ensure_ascii=False))

    if state["action"] == "set" and state.get("session_active") and running:
        print("解讀：模擬定位背景 session 仍在執行。")
        print("若要回復真實 GPS，請執行: python fly.py clear")
    elif state["action"] == "route" and state.get("session_active") and running:
        print("解讀：路線模擬背景 session 仍在執行。")
        print("若要回復真實 GPS，請執行: python fly.py clear")
        if state.get("waypoint_count"):
            print(f"路線點數: {state['waypoint_count']}（最終會回到第一個點）")
        if state.get("estimated_duration_seconds"):
            print(f"預估總時長: {format_duration(state['estimated_duration_seconds'])}")
        if state.get("distance_m"):
            print(f"預估總距離: {format_distance(state['distance_m'])}")
    elif state["action"] == "set":
        print("解讀：最後一次是 set，但背景 session 目前不在執行。")
        print("若手機仍顯示模擬位置，請直接執行: python fly.py clear")
    elif state["action"] == "route":
        if state.get("route_completed"):
            print("解讀：路線模擬已完成。")
            if state.get("completed_at"):
                print(f"完成時間: {state['completed_at']}")
        else:
            print("解讀：最後一次是 route，但背景 session 目前不在執行。")
            print("若手機仍顯示模擬位置，請直接執行: python fly.py clear")
    else:
        print("解讀：最後一次命令是 clear。若命令成功，iPhone 應已恢復真實 GPS。")


def run_doctor(args):
    manual_rsd_host, manual_rsd_port = resolve_manual_rsd(args)
    pmd3_ok, pmd3_info = probe_pymobiledevice3()
    devices, devices_error = list_usbmux_devices()

    print("檢查目前腳本設定：")
    print(f"- Python executable: {sys.executable}")
    print(f"- auto_tunnel: {args.auto_tunnel}")
    print(f"- tunnel_use_sudo: {args.tunnel_use_sudo}")
    print(f"- manual_rsd_host: {manual_rsd_host or '(未設定)'}")
    print(f"- manual_rsd_port: {manual_rsd_port or '(未設定)'}")
    print(f"- tunnel_timeout_seconds: {TUNNEL_START_TIMEOUT_SECONDS}")
    print(f"- state_file: {STATE_FILE}")
    print(f"- session_log_file: {SESSION_LOG_FILE}")
    if IS_WINDOWS:
        print(f"- windows_admin: {'yes' if is_windows_admin() else 'no'}")
    print()
    print("基礎檢查：")
    print(f"- pymobiledevice3: {'ok' if pmd3_ok else 'failed'}")
    print(f"  detail: {pmd3_info}")
    if devices_error:
        print(f"- device_detect: failed ({devices_error})")
    else:
        print(f"- device_detect: {len(devices)} device(s)")
    print()
    print("預設行為：")
    print("1. set 會在背景啟動一個模擬定位 session。")
    print("2. set 會先在前景建立 tunnel，避免背景 session 無法互動輸入 sudo 密碼。")
    print("3. tunnel 啟動後，腳本會自動解析本次有效的 RSD_HOST / RSD_PORT。")
    print("4. 然後背景 session 會用這組 RSD 執行 simulate-location set。")
    print("5. clear 會先沿用現有 RSD 送出 simulate-location clear，再終止背景 session 與 tunnel。")
    print()
    print("路線模式：")
    print("1. `route` 需要明確起點，並支援 A -> B -> C ... -> A 的閉環路線。")
    print(f"2. 最多支援 {MAX_ROUTE_POINTS} 個點（包含起點與終點，不含最後自動回到起點）。")
    print("3. 你必須手動提供 --from-lat 與 --from-lng。")
    print("4. 程式目前無法直接讀取 iPhone 真實當前 GPS。")
    print("5. `route` 會優先嘗試抓真實道路路線，抓不到時才退回直線。")
    print()
    print("地址搜尋建議：")
    print("1. 優先使用「地標, 城市, 國家」格式。")
    print("2. 若是街道地址，盡量寫成「門牌, 街道, 區, 城市, 郵遞區號, 國家」。")
    print("3. 日文地址可優先改成英文或羅馬字，通常比較容易命中。")
    print("4. 例如把 `...819-0031日本` 改成 `..., Fukuoka, 819-0031, Japan`。")
    print()
    print("密碼管理：")
    if IS_MACOS:
        print("1. 可用 `python fly.py auth-store` 把 sudo 密碼存入 macOS Keychain。")
        print("2. 可用 `python fly.py auth-status` 檢查是否已保存。")
        print("3. 可用 `python fly.py auth-clear` 刪除已保存的 sudo 密碼。")
    else:
        print("1. Windows 不使用 macOS Keychain。")
        print("2. 若 tunnel 需要權限，請用系統管理員權限重新開啟終端機。")


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
        description="Auto Fly CLI for simulated iPhone GPS on iOS 18+."
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
    route_parser.add_argument(
        "--via",
        action="append",
        default=[],
        help="Intermediate waypoint in 'lat,lng' format. Repeat up to 3 times.",
    )
    route_parser.add_argument("--speed-kph", type=float, default=ROUTE_SPEED_KPH_DEFAULT, help="Movement speed in kilometers per hour")
    route_parser.add_argument("--step-meters", type=float, default=5.0, help="Approximate meters between route points")
    route_parser.add_argument("--pause-seconds", type=float, default=0.0, help="Pause duration at the turnaround point")
    route_parser.add_argument("--route-source", choices=["osrm", "linear"], default="osrm", help="Route generation source")
    route_parser.add_argument("--route-profile", choices=["foot", "cycling", "driving"], default=ROUTE_PROFILE_DEFAULT, help="Routing profile for real-road route generation")

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

    status_parser = subparsers.add_parser("status", help="Show last local set/clear state recorded by this script")
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
                raise RuntimeError("auth-status 只支援 macOS。")
            if has_keychain_password():
                print("目前已在 macOS Keychain 保存 sudo 密碼。")
            else:
                print("目前沒有保存 sudo 密碼。")
        elif args.action == "auth-store":
            if not IS_MACOS:
                raise RuntimeError("auth-store 只支援 macOS。")
            password = getpass.getpass("請輸入要保存到 macOS Keychain 的 sudo 密碼: ")
            if not password:
                raise ValueError("密碼不可為空。")
            result = subprocess.run(["sudo", "-S", "-v"], input=password + "\n", text=True, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "sudo 驗證失敗")
            store_keychain_password(password)
            SUDO_PASSWORD_CACHE = password
            print("已保存 sudo 密碼到 macOS Keychain。")
        elif args.action == "auth-clear":
            if not IS_MACOS:
                raise RuntimeError("auth-clear 只支援 macOS。")
            if delete_keychain_password():
                print("已從 macOS Keychain 刪除保存的 sudo 密碼。")
            else:
                print("macOS Keychain 中沒有可刪除的 sudo 密碼。")
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
