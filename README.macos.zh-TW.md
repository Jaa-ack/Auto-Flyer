# Auto Fly for macOS

Auto Fly for macOS 可用瀏覽器介面或 CLI 來執行 iPhone 模擬 GPS。

下載：

- Releases 頁面：https://github.com/Jaa-ack/Auto-Flyer/releases
- 直接下載：
  https://github.com/Jaa-ack/Auto-Flyer/releases/download/v0.1.0/auto-fly-macos-zh-TW-0.1.0.zip

## 安裝

```bash
git clone <your-repo-url>
cd Auto-Fly
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果你是下載 release 壓縮檔，請先解壓縮再進入該資料夾執行上述指令。

## 準備 iPhone

- 用 USB 接上 Mac
- 信任這台 Mac
- 開啟 Developer Mode

## 啟動 Web UI

```bash
source .venv/bin/activate
python webui.py
```

打開：

```text
http://127.0.0.1:8765
```

## 常用指令

固定到 A 點：

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

執行 route：

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --via 25.0340,121.5660 \
  --lat 25.0345 --lng 121.5670
```

停止模擬：

```bash
python fly.py clear
```
