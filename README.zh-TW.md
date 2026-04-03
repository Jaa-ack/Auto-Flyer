# Auto Fly

Auto Fly 是一個跨 macOS 與 Windows 的 iPhone 模擬 GPS 專案，兩個系統共用相同的 Web UI 與 CLI 操作流程。

語言版本：

- English: `README.md`
- 繁體中文：`README.zh-TW.md`

## 下載版本

Release 會提供四個版本：

- macOS English
- macOS 繁體中文
- Windows English
- Windows 繁體中文

各平台快速說明：

- macOS English: `README.macos.en.md`
- macOS 繁體中文：`README.macos.zh-TW.md`
- Windows English: `README.windows.en.md`
- Windows 繁體中文：`README.windows.zh-TW.md`

## 內含工具

- `webui.py`
  - 本機瀏覽器介面
- `fly.py`
  - 命令列工具
- `geocode.py`
  - 地址轉座標工具

## 快速開始

1. 下載專案

```bash
git clone <your-repo-url>
cd Auto-Fly
```

2. 建立並啟用虛擬環境

macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

3. 安裝依賴

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. 準備 iPhone

- 用 USB 接上電腦
- 信任這台電腦
- 開啟 Developer Mode
- Windows 需要時請用系統管理員開啟 PowerShell 或 Terminal

5. 啟動 Web UI

macOS：

```bash
python webui.py
```

Windows：

```powershell
.venv\Scripts\python.exe webui.py
```

打開：

```text
http://127.0.0.1:8765
```

## 日常使用流程

主要流程：

1. 搜尋地址
2. 加入點位
3. 用 `set` 把 A 點設為定位
4. 用 `route` 跑 `A -> B -> C ... -> A`
5. 用 `clear` 停止模擬

固定路線模式：

- `walk`
- `cycle`
- `car-direct`
- `car-road`

Route 計時器會顯示：

- 目前狀態
- 開始時間
- 已經過時間
- 結束時間

## 常用 CLI 指令

查地址：

```bash
python geocode.py "Tokyo Tower, Tokyo, Japan"
```

固定到 A 點：

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

執行閉環 route：

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --via 25.0340,121.5660 \
  --lat 25.0345 --lng 121.5670
```

查看狀態：

```bash
python fly.py status
```

停止模擬：

```bash
python fly.py clear
```

也支援負經緯度：

```bash
python fly.py set --lat 40.6860733 --lng -74.019077
```

## 產生 Release 壓縮檔

執行：

```bash
python build_release.py
```

會產生四個壓縮檔：

```text
dist/auto-fly-macos-en-<version>.zip
dist/auto-fly-macos-zh-TW-<version>.zip
dist/auto-fly-windows-en-<version>.zip
dist/auto-fly-windows-zh-TW-<version>.zip
```

目前版本號放在 `VERSION`。

## Release 相關檔案

- GitHub repo description：`GITHUB_DESCRIPTION.md`
- 英文 release notes：`RELEASE_NOTES_v<version>.md`
- 繁中 release notes：`RELEASE_NOTES_v<version>.zh-TW.md`

## 作者

作者：`jaaaaack`

## 授權

MIT License，請見 `LICENSE`。

## 不要上傳的本機檔案

這些檔案建議留在本機：

- `.fly_state.json`
- `.fly_session.log`
- `.fly_route.gpx`
- `.saved_routes.json`
- `__pycache__/`
- `.venv/`
- `dist/`
- `backups/`

專案已經有 `.gitignore`，會自動忽略它們。
