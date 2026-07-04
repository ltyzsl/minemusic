"""
核心功能测试 —— 无 GUI
用法: python test_core.py [speed]
  speed: 动画速度倍数 (默认 1.0, 2.0=快一倍, 0.5=慢一倍)
"""

import sys, os, io, math, time
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception: pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import load_config

cfg = load_config()
print("=" * 50)
print("  Bubble App - 核心测试")
print("=" * 50)

# 配置
print("\n[配置]")
print(f"  气泡: {cfg['bubble']['size']}px 圆形")
print(f"  跳动条: {cfg['beatbar']['width']}x{cfg['beatbar']['height']}px")
print(f"  柱条数: {cfg['beatbar']['bar_count']}")
print(f"  帧率: {cfg['beatbar']['fps']}fps")
print(f"  速度: {cfg['beatbar']['speed']}")
print(f"  展开动画: {cfg['beatbar']['expand_duration_ms']}ms")
bar_color = cfg['beatbar']['bar_color']
print(f"  柱条颜色: RGBA({bar_color[0]},{bar_color[1]},{bar_color[2]},{bar_color[3]})")

# 动画参数计算
print("\n[动画参数模拟]")
speed = cfg['beatbar']['speed']
fps = cfg['beatbar']['fps']
bar_count = cfg['beatbar']['bar_count']
min_h = cfg['beatbar']['min_height_ratio']
max_h = cfg['beatbar']['max_height_ratio']

print(f"  每帧相位增量: {speed/fps:.3f} rad")
print(f"  完整周期约: {2*math.pi/(speed/fps)/fps:.1f} 秒")
print(f"  柱高范围: {min_h*100:.0f}% ~ {max_h*100:.0f}%")

# 模拟 5 帧输出
print("\n[5 帧柱高模拟]")
for frame in range(5):
    phase = frame * speed / fps
    heights = []
    for i in range(bar_count):
        offset = (i / (bar_count - 1)) * math.pi if bar_count > 1 else 0
        sin_val = math.sin(phase + offset)
        ratio = min_h + (sin_val + 1) / 2 * (max_h - min_h)
        heights.append(f"{ratio*100:.0f}%")
    print(f"  帧{frame+1} (phase={phase:.2f}): {', '.join(heights)}")

print("\n[QQ音乐]")
print(f"  auto_launch: {cfg['qqmusic']['auto_launch']}")
print(f"  path: {cfg['qqmusic']['path']}")

# 歌曲信息读取测试
print("\n[歌曲信息读取]")
sc = cfg.get("song_info", {})
print(f"  轮询间隔: {sc.get('poll_seconds', 2)}s")
print(f"  日志间隔: {sc.get('log_seconds', 5)}s")
print(f"  UIA 超时: {sc.get('uia_timeout', 3.0)}s")
print(f"  搜索深度: {sc.get('search_depth', 8)}")

try:
    from main import SongInfoReader
    reader = SongInfoReader(cfg)
    info = reader.read()
    if info:
        print(f"\n  当前播放:")
        print(f"    歌名: {info.get('title', '—')}")
        print(f"    歌手: {info.get('artist', '—')}")
        if info.get('lyric'):
            print(f"    歌词: {info['lyric']}")
    else:
        print(f"  ⚠ 未检测到 QQ 音乐窗口（请先打开 QQ 音乐并播放歌曲）")
except Exception as e:
    print(f"  ⚠ 读取失败: {e}")

print("\n" + "=" * 50)
print("  运行 main.py 查看完整效果")
print("=" * 50)
