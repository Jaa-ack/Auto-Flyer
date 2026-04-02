# Auto Fly

Auto Fly 是一個 macOS 專案，用來在 iPhone 上執行 simulated location。

語言版本：

- English: `README.md`
- 繁體中文：`README.zh-TW.md`

包含三個工具：

- `webui.py`
  - 瀏覽器介面
- `fly.py`
  - 終端機主程式
- `geocode.py`
  - 地址轉座標

## 作者

作者：`jaaaaack`

## 授權

MIT License，請見 `LICENSE`。

## 安裝

1. 下載專案

```bash
git clone <your-repo-url>
cd Auto-Fly
```

2. 建立虛擬環境

```bash
python3 -m venv .venv
```

3. 啟用虛擬環境

```bash
source .venv/bin/activate
```

4. 安裝依賴

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

5. 準備 iPhone

- 用 USB 接上 Mac
- 信任這台 Mac
- 開啟 Developer Mode

Developer Mode 通常在：

```text
設定 > 隱私權與安全性 > Developer Mode
```

## 快速開始

### 用瀏覽器介面

```bash
source .venv/bin/activate
python webui.py
```

打開：

```text
http://127.0.0.1:8765
```

### 用終端機

查地址：

```bash
python geocode.py "Tokyo Tower, Tokyo, Japan"
```

固定到一個點：

```bash
python fly.py set --lat 35.6584491 --lng 139.7455368
```

停止模擬：

```bash
python fly.py clear
```

## Web UI

主要流程：

1. 搜尋地址
2. 加入點位
3. 用 `set` 把 `A` 點設為定位
4. 用 `route` 跑 `A -> B -> C ... -> A`
5. 用 `clear` 停止模擬

### 設定模式

- `preset`
- `manual`

### 固定路線模式

- `walk`
- `cycle`
- `car-direct`
- `car-road`

### Route 計時器

會顯示：

- 目前狀態
- 開始時間
- 已經過時間
- 結束時間

## 常用 CLI 指令

固定到一個點：

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

負經緯度也支援：

```bash
python fly.py set --lat 40.6860733 --lng -74.019077
```

跑 route：

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --via 25.0340,121.5660 \
  --lat 25.0345 --lng 121.5670
```

看狀態：

```bash
python fly.py status
```

停止模擬：

```bash
python fly.py clear
```

## 產生 Release 壓縮檔

執行：

```bash
python build_release.py
```

會產生：

```text
dist/auto-fly-<version>.zip
```

目前版本號放在：

```text
VERSION
```

## GitHub Release 建議流程

1. 更新 `VERSION`
2. 執行 `python build_release.py`
3. 到 GitHub 建立 Release
4. 上傳 `dist/` 內產生的 zip

Release 說明檔：

- 英文：`RELEASE_NOTES_v0.1.0.md`
- 繁中：`RELEASE_NOTES_v0.1.0.zh-TW.md`

GitHub repo description 文字：

- `GITHUB_DESCRIPTION.md`

## 不要上傳的本機檔案

這些檔案建議留在本機：

- `.fly_state.json`
- `.fly_session.log`
- `.fly_route.gpx`
- `.saved_routes.json`
- `__pycache__/`
- `.venv/`
- `dist/`

專案已經有 `.gitignore`，會自動忽略它們。
