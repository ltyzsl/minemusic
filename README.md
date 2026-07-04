# 🎵 minemusic

> 桌面悬浮音乐控制气泡 — 支持 QQ 音乐，真实音频频谱可视化

![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![python](https://img.shields.io/badge/python-3.12%2B-green)
![license](https://img.shields.io/badge/license-MIT-yellow)

一个优雅的桌面悬浮气泡，点击展开为频谱跳动条，控制 QQ 音乐播放。支持 WASAPI 真实音频环回 + FFT 频谱可视化，5 种频谱样式可切换。

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 🫧 **悬浮气泡** | 毛玻璃圆形气泡，悬停放大，可拖拽移动 |
| 🎵 **播放控制** | 播放/暂停、上一首/下一首、进度条拖动 |
| 📊 **真实频谱** | WASAPI 环回系统音频 + FFT，柱子随音乐真实跳动 |
| 🔄 **双向绑定** | QQ 音乐播放/暂停 ↔ 气泡收起/展开，自动同步 |
| 🎨 **5 种样式** | 柱状图 · 心电波 · 辐射圆环 · 粒子喷射 · 水波纹 |
| 🔊 **滚轮音量** | 在气泡 / 跳动条 / 面板上滚动滚轮调节系统音量 |
| 📋 **歌曲信息** | UIAutomation 读取 QQ 音乐歌名、歌手、歌词 |
| 📌 **托盘 + 任务栏** | 系统托盘右键菜单（显示/隐藏/退出），任务栏图标 |
| 🔒 **单实例** | 多次启动自动合并，双击桌面图标切换播放/暂停 |

## 📥 下载

前往 [Releases](https://github.com/ltyzsl/minemusic/releases) 下载最新版 `minemusic.exe`（56 MB）。

双击运行，**无需安装 Python 或任何依赖**。首次启动自动在同目录生成 `config.json`。

> 如果 Windows Defender 报警，点击「更多信息」→「仍要运行」即可（PyInstaller 打包的 exe 偶有误报）。

## 🚀 开发

```bash
# 克隆仓库
git clone https://github.com/ltyzsl/minemusic.git
cd minemusic

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

## ⚙️ 配置

首次运行时自动生成 `config.json`，各字段说明：

```jsonc
{
  "bubble": {
    "size": 55,           // 气泡直径 (px)
    "opacity": 0.82,      // 透明度
    "icon": "♪",          // 气泡显示的文字/符号
    "icon_size": 28,      // 图标大小
    "hover_scale": 1.35   // 悬停放大倍数
  },
  "beatbar": {
    "width": 180,         // 跳动条宽度
    "height": 55,         // 跳动条高度
    "bar_count": 5,       // 柱/频段数量
    "fps": 30,            // 刷新帧率
    "speed": 5.0,         // 动效速度
    "expand_duration_ms": 280  // 展开动画时长
  },
  "qqmusic": {
    "auto_launch": true,  // 自动启动 QQ 音乐
    "startup_wait": 3.0   // 启动等待秒数
  },
  "song_info": {
    "poll_seconds": 0.5,  // 歌曲信息轮询间隔
    "uia_timeout": 1.0    // UIA 搜索超时
  },
  "panel": {
    "width": 320,         // 面板宽度
    "height": 250,        // 面板高度
    "bg_alpha": 140       // 背景透明度 (0-255)
  },
  "spectrum": {
    "style": "bars"       // 默认频谱样式: bars|wave|circle|particle|water
  }
}
```

## 🎨 频谱样式

在控制面板点击 `☰` 按钮切换：

| 样式 | 效果 |
|------|------|
| **柱状图** | 5 根经典竖柱，跟真实音频 |
| **心电波** | 尖锐折线 + 光晕，随机尖峰 |
| **辐射圆环** | 半圆五方向辐射柱 |
| **粒子喷射** | 光点飞升 + 渐淡拖尾 |
| **水波纹** | 3 层正弦波浪叠加，横向流动 |

## 🏗 技术栈

| 组件 | 技术 |
|------|------|
| GUI | PyQt5 |
| 音频捕获 | soundcard (WASAPI loopback) |
| 频谱分析 | numpy (FFT) |
| 歌曲信息 | uiautomation (UI Automation) |
| 打包 | PyInstaller |

## 📄 License

MIT
