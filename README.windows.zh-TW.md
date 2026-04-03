# Auto Fly for Windows

Auto Fly for Windows 可用瀏覽器介面或 CLI 來執行 iPhone 模擬 GPS。

下載：

- Releases 頁面：https://github.com/Jaa-ack/Auto-Fly/releases
- 直接下載：
  https://github.com/Jaa-ack/Auto-Fly/releases/download/v0.1.0/auto-fly-windows-zh-TW-0.1.0.zip

## 安裝

```powershell
git clone <your-repo-url>
cd Auto-Fly
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果你是下載 release 壓縮檔，請先解壓縮再進入該資料夾執行上述指令。

## 準備 iPhone

- 用 USB 接上電腦
- 信任這台電腦
- 開啟 Developer Mode
- 需要時請用系統管理員權限開啟 PowerShell 或 Terminal

## 啟動 Web UI

```powershell
.venv\Scripts\python.exe webui.py
```

打開：

```text
http://127.0.0.1:8765
```

## 常用指令

固定到 A 點：

```powershell
.venv\Scripts\python.exe fly.py set --lat 25.0330 --lng 121.5654
```

執行 route：

```powershell
.venv\Scripts\python.exe fly.py route --from-lat 25.0330 --from-lng 121.5654 --via 25.0340,121.5660 --lat 25.0345 --lng 121.5670
```

停止模擬：

```powershell
.venv\Scripts\python.exe fly.py clear
```
