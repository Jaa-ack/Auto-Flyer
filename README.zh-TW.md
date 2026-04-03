# Auto Fly

Auto Fly 是一個支援 macOS 與 Windows 的 iPhone 模擬 GPS 專案。

[English](README.md)

## 下載方式

建議使用方式：直接到 GitHub Releases 下載對應系統與語言版本，不建議一般使用者用 `git clone`。

- Releases 頁面：https://github.com/Jaa-ack/Auto-Fly/releases
- 最新版本：https://github.com/Jaa-ack/Auto-Fly/releases/latest

目前提供的下載檔：

- macOS English：
  https://github.com/Jaa-ack/Auto-Fly/releases/download/v0.1.0/auto-fly-macos-en-0.1.0.zip
- macOS 繁體中文：
  https://github.com/Jaa-ack/Auto-Fly/releases/download/v0.1.0/auto-fly-macos-zh-TW-0.1.0.zip
- Windows English：
  https://github.com/Jaa-ack/Auto-Fly/releases/download/v0.1.0/auto-fly-windows-en-0.1.0.zip
- Windows 繁體中文：
  https://github.com/Jaa-ack/Auto-Fly/releases/download/v0.1.0/auto-fly-windows-zh-TW-0.1.0.zip

各版本使用說明：

- [macOS English](README.macos.en.md)
- [macOS 繁體中文](README.macos.zh-TW.md)
- [Windows English](README.windows.en.md)
- [Windows 繁體中文](README.windows.zh-TW.md)

## 功能

- 搜尋地址並轉成座標
- 將 iPhone 設定到固定模擬定位點
- 執行閉環路線，例如 `A -> B -> C -> A`
- 停止模擬並回到正常 GPS
- macOS 與 Windows 共用相同 Web UI 操作流程

## 快速開始

1. 下載上方對應的 release 壓縮檔。
2. 解壓縮。
3. 建立並啟用 Python 虛擬環境。
4. 使用 `requirements.txt` 安裝依賴。
5. 用 USB 接上 iPhone、信任電腦並開啟 Developer Mode。
6. 啟動 `webui.py` 或使用 `fly.py`。

完整安裝與使用方式，請直接打開符合你系統與語言的說明檔。

## 以 Release 為主

一般使用者建議直接從 Releases 下載，不需要 `git clone`。

只有要自行修改專案時，才建議使用原始碼方式。

## 原始碼開發

如果你要從原始碼使用：

```bash
git clone https://github.com/Jaa-ack/Auto-Fly.git
cd Auto-Fly
```

## 作者

作者：`jaaaaack`

## 授權

MIT License，請見 `LICENSE`。
