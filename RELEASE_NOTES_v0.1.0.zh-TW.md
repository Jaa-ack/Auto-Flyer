# Auto Fly v0.1.0

Auto Fly 第一版公開釋出。

## 重點功能

- 瀏覽器介面，可搜尋、選點、`set`、`route`、`clear`
- CLI 工具，可直接用終端機操作
- 地址轉座標工具
- 內建固定移動模式：
  - `walk`
  - `cycle`
  - `car-direct`
  - `car-road`
- 可自行調整 route 參數的手動模式
- Web UI 可保存常用路線
- Route 計時器，可顯示狀態、開始時間、已經過時間、結束時間
- 可用 `python build_release.py` 產生 release 壓縮檔

## 包含檔案

- `webui.py`
- `fly.py`
- `geocode.py`
- `requirements.txt`
- `README.md`
- `README.zh-TW.md`

## 注意事項

- 僅支援 macOS
- 需要 iOS 18+ 的 iPhone
- 需要先開啟 Developer Mode
- 這是 simulated location，不是永久修改硬體 GPS
