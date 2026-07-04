"""
悬浮气泡 → 点击展开跳动条
===========================
- 圆形态：毛玻璃圆形气泡，音符图标，悬停放大，拖拽移动
- 展开态：透明背景，5 根黑色频谱柱，正弦波动画
- 柱子随音乐节奏跳动（假动效），单击控制 QQ 音乐播放/暂停
"""

import sys, json, os, time, subprocess, threading, ctypes, math, re
from ctypes import wintypes
import uiautomation as uia
from audio_capture import AudioCapture
from renderers import BarRenderer, WaveRenderer, CircleRenderer, ParticleRenderer, WaterRenderer

# ── Windows 消息结构体 & 自定义消息 ──────────────────────────

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class _MSG(ctypes.Structure):
    """Windows MSG 结构体，用于 nativeEvent 中解析消息"""
    _fields_ = [
        ("hwnd",    wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam",  wintypes.WPARAM),
        ("lParam",  wintypes.LPARAM),
        ("time",    wintypes.DWORD),
        ("pt",      _POINT),
    ]

# 自定义窗口消息：第二个实例通知已有实例恢复播放并展开
WM_BUBBLE_ACTIVATE = 0x8001  # WM_APP + 1

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QGraphicsBlurEffect,
    QSlider, QTextEdit, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy,
    QSystemTrayIcon, QMenu, QAction,
)
from PyQt5.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty,
    QEvent, QObject, QRect, pyqtSignal,
)
from PyQt5.QtGui import (
    QFont, QPainter, QColor, QLinearGradient, QPen, QBrush, QFontMetrics,
    QIcon,
)


# ═══════════════════════════════════════════════════════════════
# 路径 & 配置
# ═══════════════════════════════════════════════════════════════

def _exe_dir() -> str:
    """获取 exe 所在目录（开发模式 = 脚本目录），用于可写文件"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _data_dir() -> str:
    """获取数据目录，用于读取打包的只读资源（图标等）

    --onefile 打包后资源在 sys._MEIPASS（临时解压目录），
    --onedir 或开发模式下与 exe/脚本 同目录。
    """
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        return base
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(_exe_dir(), "config.json")
LOG_PATH    = os.path.join(_exe_dir(), "bubble.log")

DEFAULT_CONFIG = {
    "bubble": {
        "size": 55,
        "opacity": 0.82,
        "icon": "♪",
        "icon_size": 28,
        "hover_scale": 1.35,
        "blur_radius": 10,
        "color_bg": [32, 32, 32, 195],
        "color_icon": [255, 255, 255],
    },
    "beatbar": {
        "width": 180,
        "height": 55,
        "bar_count": 5,
        "bar_width": 10,
        "bar_gap": 8,
        "bar_radius": 5,
        "fps": 30,
        "speed": 5.0,
        "min_height_ratio": 0.12,
        "max_height_ratio": 0.95,
        "expand_duration_ms": 280,
        "bar_color": [0, 0, 0, 200],
    },
    "qqmusic": {
        "path": "auto",
        "auto_launch": True,
        "startup_wait": 3.0,
    },
    "spectrum": {
        "style": "bars",
    },
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    return DEFAULT_CONFIG.copy()


def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Windows API — QQ 音乐控制
# ═══════════════════════════════════════════════════════════════

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_VOLUME_UP = 0xAF
VK_VOLUME_DOWN = 0xAE
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ki", _KEYBDINPUT)]


def _send_media_key(vk: int):
    """通过 SendInput 发送多媒体键（原子操作：按下+释放）

    系统级键盘注入，Windows 自动路由到当前媒体播放器。
    """
    inputs = (_INPUT * 2)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki.wVk = vk
    inputs[0].ki.dwFlags = KEYEVENTF_EXTENDEDKEY
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki.wVk = vk
    inputs[1].ki.dwFlags = KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP

    sent = ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(_INPUT))
    if sent != 2:
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def _send_media_play_pause():
    """播放/暂停"""
    _send_media_key(VK_MEDIA_PLAY_PAUSE)


def _send_media_next():
    """下一首"""
    _send_media_key(VK_MEDIA_NEXT_TRACK)


def _send_media_prev():
    """上一首"""
    _send_media_key(VK_MEDIA_PREV_TRACK)


def _send_seek(delta_pct: int):
    """通过发送左右方向键来调整播放位置

    delta_pct > 0 → 快进（右箭头）
    delta_pct < 0 → 快退（左箭头）
    每 1% 约等于 1 次按键（QQ 音乐约 5 秒/次）
    """
    vk = 0x27 if delta_pct > 0 else 0x25  # VK_RIGHT / VK_LEFT
    count = min(abs(delta_pct), 50)       # 最多 50 次，避免过度
    for _ in range(count):
        inp = (_INPUT * 2)()
        inp[0].type = INPUT_KEYBOARD
        inp[0].ki.wVk = vk
        inp[1].type = INPUT_KEYBOARD
        inp[1].ki.wVk = vk
        inp[1].ki.dwFlags = KEYEVENTF_KEYUP
        ctypes.windll.user32.SendInput(2, ctypes.byref(inp), ctypes.sizeof(_INPUT))
        time.sleep(0.015)


# ═══════════════════════════════════════════════════════════════
# QQ 音乐自动启动
# ═══════════════════════════════════════════════════════════════

QQMUSIC_PATHS = [
    r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
    r"C:\Program Files\Tencent\QQMusic\QQMusic.exe",
    r"D:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
    r"D:\应用\QQMusic\QQMusic.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Tencent\QQMusic\QQMusic.exe"),
]

def _find_qqmusic_path(cfg: dict) -> str | None:
    p = cfg.get("qqmusic", {}).get("path", "auto")
    if p and p != "auto" and os.path.exists(p): return p
    for p in QQMUSIC_PATHS:
        if os.path.exists(p): return p
    try:
        import winreg
        for root, key in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQMusic"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQMusic"),
        ]:
            try:
                with winreg.OpenKey(root, key) as h:
                    for i in range(32):
                        try:
                            n, v, _ = winreg.EnumValue(h, i)
                            if n.lower() in ("installpath", "installdir", "displayicon"):
                                exe = os.path.join(v.rstrip("\\"), "QQMusic.exe")
                                if os.path.exists(exe): return exe
                        except OSError: break
            except OSError: continue
    except Exception: pass
    return None

def _is_qqmusic_running() -> bool:
    try:
        r = subprocess.run(['tasklist', '/fi', 'IMAGENAME eq QQMusic.exe'],
                           capture_output=True, text=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return 'QQMusic.exe' in r.stdout
    except Exception: return False

def _try_launch_qqmusic(cfg: dict):
    if _is_qqmusic_running(): return
    path = _find_qqmusic_path(cfg)
    if not path: return
    try:
        subprocess.Popen([path], shell=False,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(cfg.get("qqmusic", {}).get("startup_wait", 3.0))
    except OSError: pass

def _do_media_control(cfg: dict):
    """控制 QQ 音乐播放/暂停

    使用系统级多媒体键 SendInput → Windows 自动路由到当前媒体播放器。
    如果需要，先自动启动 QQ 音乐。
    """
    if cfg.get("qqmusic", {}).get("auto_launch", False):
        _try_launch_qqmusic(cfg)
    _send_media_play_pause()


# ═══════════════════════════════════════════════════════════════
# 歌曲信息读取（UIAutomation 后台轮询 QQ 音乐窗口）
# ═══════════════════════════════════════════════════════════════

class SongInfoReader:
    """后台读取 QQ 音乐当前播放信息（歌名/歌手/歌词）

    回退策略：
    1. 窗口标题正则解析 — 最可靠，QQ 音乐标题格式为 "歌名 - 歌手 - QQ音乐"
    2. UIA 控件树遍历 — 尝试从 Text 控件中提取歌词等补充信息
    3. 失败保持旧数据不动
    """

    # 窗口标题正则（兼容中文/英文破折号）
    # QQ 音乐标题格式通常为 "歌名 - 歌手"（末尾可能含空格，部分版本含 " - QQ音乐"）
    _TITLE_RE = re.compile(
        r'^(.+?)\s*[-—–]\s*(.+?)(?:\s*[-—–]\s*QQ音乐)?\s*$'
    )

    # 歌词相关关键词（用于从 UIA 控件 Name 中筛选歌词文本）
    _ARTIST_KEYWORDS = ('歌手', '演唱', '专辑', '艺人')
    _LYRIC_KEYWORDS = ('歌词', '作词', '纯音乐')

    def __init__(self, config: dict):
        sc = config.get("song_info", {})
        self._poll = sc.get("poll_seconds", 0.5)
        self._log_interval = sc.get("log_seconds", 5)
        self._timeout = sc.get("uia_timeout", 1.0)
        self._depth = sc.get("search_depth", 8)
        uia.uiautomation.SetGlobalSearchTimeout(self._timeout)

    # ── 找 QQ 音乐主窗口 ──────────────────────────────────

    def _find_qqmusic_control(self):
        """查找 QQ 音乐主窗口的 UIA Control（按 ClassName 匹配）"""
        # QQ 音乐使用 TXGuiFoundation 作为主窗口类名
        for cls in ('TXGuiFoundation', 'QQMusic_Window'):
            try:
                w = uia.WindowControl(searchDepth=1, ClassName=cls)
                if w.Exists(0.5):
                    return w
            except Exception:
                continue
        return None

    # ── 方法 A：窗口标题解析 ──────────────────────────────

    def _read_window_title(self, window) -> dict | None:
        """从 QQ 音乐窗口标题提取歌名和歌手

        典型标题格式:
          "晴天 - 周杰伦 - QQ音乐"
          "稻香 — 周杰伦 — QQ音乐"
        """
        try:
            title = window.Name
            if not title:
                return None
            m = self._TITLE_RE.match(title)
            if m:
                return {
                    "title": m.group(1).strip(),
                    "artist": m.group(2).strip(),
                }
        except Exception:
            pass
        return None

    # ── 方法 B：UIA 控件树遍历 ────────────────────────────

    def _read_uia_controls(self, window) -> dict | None:
        """遍历 QQ 音乐窗口的 UIA 控件树，收集所有 Text 控件的 Name

        返回格式: {"title": "", "artist": "", "lyric": ""}
        通过启发式规则从收集到的文本中推断歌名/歌手/歌词。
        """
        try:
            all_texts = []

            def _walk(ctrl, depth=0):
                if depth > self._depth:
                    return
                try:
                    if ctrl.ControlTypeName == "TextControl" and ctrl.Name:
                        all_texts.append(ctrl.Name.strip())
                except Exception:
                    pass
                try:
                    for child in ctrl.GetChildren():
                        _walk(child, depth + 1)
                except Exception:
                    pass

            _walk(window, 0)

            if not all_texts:
                return None

            result = {}
            # 按关键词推断
            for text in all_texts:
                if any(kw in text for kw in self._ARTIST_KEYWORDS):
                    val = re.sub(r'^(歌手|演唱|专辑|艺人)[：:]\s*', '', text)
                    if val and val != text:
                        result.setdefault("artist", val)
                if any(kw in text for kw in self._LYRIC_KEYWORDS):
                    # 歌词行通常较长（> 5 字），不含特殊前缀
                    cleaned = re.sub(r'^(歌词|作词)[：:]\s*', '', text)
                    if len(cleaned) > 5:
                        result.setdefault("lyric", cleaned)

            # 如果还没有 artist，找短文本（2-8 字），可能含中文常见姓名字
            if "artist" not in result:
                for text in all_texts:
                    if 2 <= len(text) <= 8 and not any(
                        kw in text for kw in ('QQ', '音乐', '播放', '下载', '设置')
                    ):
                        result.setdefault("artist_guess", text)

            # 取较长文本作为候选歌词（> 8 字）
            if "lyric" not in result:
                long_texts = [t for t in all_texts if len(t) > 8]
                if long_texts:
                    result["lyric"] = max(long_texts, key=len)

            return result if result else None
        except Exception:
            return None

    # ── 方法 C：检测播放/暂停状态 ──────────────────────────

    def _detect_playback_state(self, window) -> bool | None:
        """通过 UIA 控件树查找播放/暂停按钮，检测当前播放状态

        QQ 音乐的播放/暂停按钮是一个 Button 控件：
        - 按钮 Name = "暂停" → 正在播放（显示暂停按钮）
        - 按钮 Name = "播放" → 已暂停（显示播放按钮）
        """
        try:
            def _find(ctrl, depth=0):
                if depth > self._depth:
                    return None
                try:
                    if ctrl.ControlTypeName == "ButtonControl":
                        name = ctrl.Name
                        if name == "暂停":
                            return True   # 显示暂停按钮 → 正在播放
                        if name == "播放":
                            return False  # 显示播放按钮 → 已暂停
                except Exception:
                    pass
                try:
                    for child in ctrl.GetChildren():
                        result = _find(child, depth + 1)
                        if result is not None:
                            return result
                except Exception:
                    pass
                return None

            return _find(window)
        except Exception:
            return None

    # ── 主入口 ────────────────────────────────────────────

    def read(self) -> dict | None:
        """读取一次 QQ 音乐当前播放信息

        Returns:
            dict with keys "title", "artist", "lyric", "is_playing" — 或 None
        """
        info = {}

        window = self._find_qqmusic_control()
        if window is None:
            return None

        # 方法 A：窗口标题 → 歌名 + 歌手（最高优先级）
        title_info = self._read_window_title(window)
        if title_info:
            info.update(title_info)

        # 方法 B：UIA 控件遍历 → 歌词等补充信息
        uia_info = self._read_uia_controls(window)
        if uia_info:
            for key in ("artist", "lyric"):
                if key not in info and key in uia_info:
                    info[key] = uia_info[key]
            if "artist" not in info and "artist_guess" in uia_info:
                info["artist"] = uia_info["artist_guess"]

        # 方法 C：播放状态检测
        is_playing = self._detect_playback_state(window)
        if is_playing is not None:
            info["is_playing"] = is_playing

        return info if info else None

    # ── 后台轮询线程 ──────────────────────────────────────

    def run(self, callback):
        """后台循环：每隔 poll_seconds 读取，通过 callback(info) 回传

        Args:
            callback: callable(dict | None) — 在主线程安全的情况下调用
            info 为本次 read() 的返回值，可能为 None（未读到数据）
        """
        # UIAutomation 在非主线程使用前必须初始化 COM
        ctypes.windll.ole32.CoInitialize(0)

        last_log = 0
        last_info = None

        while True:
            try:
                info = self.read()
            except Exception:
                info = None

            if info:
                last_info = info

            # 回调始终传本次读取结果（None 表示未读到）
            try:
                callback(info)
            except Exception:
                pass

            # 控制台日志（每 log_seconds 秒）
            now = time.time()
            if now - last_log >= self._log_interval:
                last_log = now
                current = info or last_info
                if current:
                    log(f"♫ {current.get('title', '—')} — {current.get('artist', '—')}"
                        + (f"  [{current['lyric']}]" if current.get('lyric') else ""))
                else:
                    log("[SongInfo] 等待 QQ 音乐…")

            time.sleep(self._poll)


# ═══════════════════════════════════════════════════════════════
# 跑马灯标签（文本过长时自动滚动）
# ═══════════════════════════════════════════════════════════════

class MarqueeLabel(QWidget):
    """歌名过长时自动滚动的标签"""

    def __init__(self, parent=None, font_size=14, color=(255, 255, 255)):
        super().__init__(parent)
        self._text = ""
        self._offset = 0
        self._text_width = 0
        self._needs_scroll = False
        self._color = QColor(*color)
        self._font = QFont("Microsoft YaHei", font_size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(font_size + 14)
        self.setMinimumWidth(100)

    def setText(self, text: str):
        self._text = text
        self._offset = 0
        fm = QFontMetrics(self._font)
        self._text_width = fm.horizontalAdvance(text) if text else 0
        self._needs_scroll = self._text_width > self.width() - 10
        if self._needs_scroll:
            self._timer.start(35)
        else:
            self._timer.stop()
        self.update()

    def _tick(self):
        self._offset += 1
        if self._offset > self._text_width - self.width() + 30:
            self._offset = -30  # 滚出后停顿再循环
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._needs_scroll = self._text_width > self.width() - 10
        if self._needs_scroll and not self._timer.isActive():
            self._timer.start(35)
        elif not self._needs_scroll:
            self._timer.stop()
            self._offset = 0

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._font)
        p.setPen(self._color)
        if not self._text:
            return
        if self._needs_scroll:
            p.drawText(QRect(-self._offset, 0, self._text_width + 60, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self._text)
        else:
            p.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, self._text)


# ═══════════════════════════════════════════════════════════════
# 操作面板（跳动条上方的半透明控制面板）
# ═══════════════════════════════════════════════════════════════

class MediaButton(QPushButton):
    """手绘简约媒体图标按钮 — 与毛玻璃背景融为一体

    正常态：透明底 + 半透明黑色图标
    悬停态：浅灰底
    按下态：深灰底
    """

    ICON_PREV = 0   # ⏮ 上一首
    ICON_PLAY = 1   # ⏯ 播放
    ICON_NEXT = 2   # ⏭ 下一首

    def __init__(self, icon_type: int, parent=None):
        super().__init__(parent)
        self._icon_type = icon_type
        self._hovered = False
        self._pressed = False
        self.setFixedSize(44, 44)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, e):
        self._hovered = True
        self.update()

    def leaveEvent(self, e):
        self._hovered = False
        self.update()

    def mousePressEvent(self, e):
        self._pressed = True
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # 背景（悬停/按下时显示）
        if self._pressed:
            p.setBrush(QColor(0, 0, 0, 30))
        elif self._hovered:
            p.setBrush(QColor(0, 0, 0, 15))
        else:
            p.setBrush(Qt.NoBrush)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(cx, cy), 20, 20)

        # 图标颜色 — 与背景融合的半透明黑
        p.setPen(QPen(QColor(0, 0, 0, 110), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor(0, 0, 0, 110))

        if self._icon_type == self.ICON_PLAY:
            # 右三角 (▶)
            s = 8
            triangle = [
                QPoint(cx - s + 3, cy - s),
                QPoint(cx + s - 1, cy),
                QPoint(cx - s + 3, cy + s),
            ]
            p.drawPolygon(*triangle)
        elif self._icon_type == self.ICON_PREV:
            # 双左三角 + 竖线
            s = 7
            g = 3
            p.drawPolygon(QPoint(cx - g, cy - s), QPoint(cx - s - g, cy), QPoint(cx - g, cy + s))
            p.drawPolygon(QPoint(cx + g, cy - s), QPoint(cx - s + g, cy), QPoint(cx + g, cy + s))
            p.setPen(QPen(QColor(0, 0, 0, 110), 2.0))
            p.drawLine(cx - s - g - 3, cy - s + 1, cx - s - g - 3, cy + s - 1)
        elif self._icon_type == self.ICON_NEXT:
            # 双右三角 + 竖线
            s = 7
            g = 3
            p.drawPolygon(QPoint(cx + g, cy - s), QPoint(cx + s + g, cy), QPoint(cx + g, cy + s))
            p.drawPolygon(QPoint(cx - g, cy - s), QPoint(cx + s - g, cy), QPoint(cx - g, cy + s))
            p.setPen(QPen(QColor(0, 0, 0, 110), 2.0))
            p.drawLine(cx + s + g + 3, cy - s + 1, cx + s + g + 3, cy + s - 1)


class ControlPanel(QWidget):
    """毛玻璃操作面板 — 黑色文字 + 模糊背景、大圆角、自动消失"""

    AUTO_HIDE_SEC = 5
    hide_requested = pyqtSignal()
    play_paused = pyqtSignal()     # 面板播放/暂停按钮被点击
    prev_clicked = pyqtSignal()    # 上一首
    next_clicked = pyqtSignal()    # 下一首
    exit_requested = pyqtSignal()  # 退出程序
    spectrum_menu_clicked = pyqtSignal(QPoint)  # 频谱样式按钮被点击（携带屏幕坐标）

    def __init__(self, config: dict):
        super().__init__()
        pc = config.get("panel", {})
        self._pw = pc.get("width", 320)
        self._ph = pc.get("height", 250)
        self._cr = pc.get("corner_radius", 20)
        blur_radius = pc.get("blur_radius", 12)
        bg_alpha = pc.get("bg_alpha", 140)

        # ── 窗口设置 ──
        self.setFixedSize(self._pw, self._ph)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        # ── 毛玻璃背景层（子控件 + QGraphicsBlurEffect）──
        self._glass = _PanelGlass(self, [255, 255, 255, bg_alpha], blur_radius, self._cr)
        self._glass.setGeometry(0, 0, self._pw, self._ph)

        # ══ 全黑色系 ══
        BLACK = "rgba(0,0,0,230)"
        BLACK_SUB = "rgba(0,0,0,150)"
        BLACK_LIGHT = "rgba(0,0,0,100)"

        # ── 自动隐藏定时器 ──
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_requested.emit)

        # ── 主布局 ──
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(2)

        # 歌名（跑马灯）
        self.title_label = MarqueeLabel(self, font_size=15, color=(0, 0, 0))
        self.title_label.setStyleSheet("background: transparent;")
        root.addWidget(self.title_label)

        # 歌手
        self.artist_label = QLabel(self)
        self.artist_label.setFont(QFont("Segoe UI", 10))
        self.artist_label.setStyleSheet(f"color: {BLACK_SUB}; background: transparent;")
        root.addWidget(self.artist_label)

        # 歌词（跑马灯流动）
        self.lyric_label = MarqueeLabel(self, font_size=13, color=(0, 0, 0))
        self.lyric_label.setStyleSheet("background: transparent;")
        root.addWidget(self.lyric_label)

        root.addSpacing(8)

        # 进度条（可拖动调整播放位置）
        self.progress = QSlider(Qt.Horizontal, self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setEnabled(True)
        self.progress.setFixedHeight(18)
        self.progress.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {BLACK_LIGHT}; height: 3px; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {BLACK}; width: 10px; height: 10px;
                margin: -4px 0; border-radius: 5px;
            }}
            QSlider::sub-page:horizontal {{
                background: {BLACK}; border-radius: 2px;
            }}
        """)
        self._progress_prev = 0
        self.progress.sliderPressed.connect(lambda: setattr(self, '_progress_prev', self.progress.value()))
        self.progress.sliderReleased.connect(self._on_seek)
        root.addWidget(self.progress)

        root.addSpacing(6)

        # 控制按钮 — 手绘简约图标，与毛玻璃背景融合
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)
        ctrl_actions = [
            (MediaButton.ICON_PREV, _send_media_prev, self.prev_clicked),
            (MediaButton.ICON_PLAY, _send_media_play_pause, self.play_paused),
            (MediaButton.ICON_NEXT, _send_media_next, self.next_clicked),
        ]
        for icon_type, action, signal in ctrl_actions:
            btn = MediaButton(icon_type, self)
            btn.clicked.connect(lambda checked, a=action, s=signal: (
                threading.Thread(target=a, daemon=True).start(),
                s.emit(),
                self._reset_hide_timer(),
            ))
            ctrl_row.addWidget(btn)
        ctrl_row.addStretch()

        # 频谱样式按钮 — ✕ 左边
        btn_style = r"☰"
        style_btn = QPushButton(btn_style, self)
        style_btn.setFixedSize(28, 28)
        style_btn.setFont(QFont("Segoe UI Symbol", 12))
        style_btn.setFocusPolicy(Qt.NoFocus)
        style_btn.setCursor(Qt.PointingHandCursor)
        style_btn.setToolTip("切换频谱样式")
        style_btn.setStyleSheet(f"""
            QPushButton {{
                color: {BLACK_LIGHT};
                background: transparent;
                border: none;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                color: {BLACK};
                background: rgba(0,0,0,15);
            }}
            QPushButton:pressed {{
                color: {BLACK};
                background: rgba(0,0,0,30);
            }}
        """)
        style_btn.clicked.connect(
            lambda: self.spectrum_menu_clicked.emit(style_btn.mapToGlobal(QPoint(0, style_btn.height())))
        )
        ctrl_row.addWidget(style_btn)

        # 退出按钮 — 右上角 ✕
        exit_btn = QPushButton("✕", self)
        exit_btn.setFixedSize(28, 28)
        exit_btn.setFont(QFont("Segoe UI Symbol", 12))
        exit_btn.setFocusPolicy(Qt.NoFocus)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(f"""
            QPushButton {{
                color: {BLACK_LIGHT};
                background: transparent;
                border: none;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                color: {BLACK};
                background: rgba(0,0,0,15);
            }}
            QPushButton:pressed {{
                color: {BLACK};
                background: rgba(0,0,0,30);
            }}
        """)
        exit_btn.clicked.connect(self.exit_requested.emit)
        ctrl_row.addWidget(exit_btn)

        root.addLayout(ctrl_row)

        # 玻璃层提到最前（在布局之后，确保在所有控件下方）
        self._glass.lower()

    # 不再需要 paintEvent — 背景由 _PanelGlass 子控件渲染

    seeked = pyqtSignal(int)  # 拖动进度条 → 通知 BubbleWidget 同步计时

    def _on_seek(self):
        """用户拖动进度条 → 发送方向键 + 通知同步计时"""
        new_val = self.progress.value()
        delta = new_val - self._progress_prev
        if delta != 0:
            threading.Thread(target=_send_seek, args=(delta,), daemon=True).start()
        self.seeked.emit(new_val)
        self._reset_hide_timer()

    def set_song_info(self, info: dict):
        title = info.get("title", "")
        artist = info.get("artist", "")
        lyric = info.get("lyric", "")
        self.title_label.setText(title if title else "未在播放")
        self.artist_label.setText(artist if artist else "")
        self.lyric_label.setText(lyric if lyric else "♫")

    def position_above(self, target: QWidget):
        tg = target.geometry()
        x = tg.x() + (tg.width() - self._pw) // 2
        y = tg.y() - self._ph - 10
        if y < 4:
            y = tg.y() + tg.height() + 10
        self.move(x, y)

    # ── 自动消失 ──

    def _reset_hide_timer(self):
        self._hide_timer.start(self.AUTO_HIDE_SEC * 1000)

    def showEvent(self, event):
        super().showEvent(event)
        self._hide_timer.start(self.AUTO_HIDE_SEC * 1000)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._hide_timer.stop()

    def mouseMoveEvent(self, event):
        self._reset_hide_timer()
        super().mouseMoveEvent(event)

    def nativeEvent(self, eventType, message):
        """面板上的滚轮 → 调节系统音量"""
        if eventType == b"windows_generic_MSG":
            msg = ctypes.cast(
                ctypes.c_void_p(int(message)),
                ctypes.POINTER(_MSG)
            ).contents
            if msg.message == 0x020A:  # WM_MOUSEWHEEL
                delta = ctypes.c_short((msg.wParam >> 16) & 0xFFFF).value
                if delta > 0:
                    _send_media_key(VK_VOLUME_UP)
                elif delta < 0:
                    _send_media_key(VK_VOLUME_DOWN)
                self._reset_hide_timer()
                return True, 0
        return super().nativeEvent(eventType, message)


# ═══════════════════════════════════════════════════════════════
# 面板毛玻璃背景子控件（同 GlassBg 原理：画形状 + 模糊）
# ═══════════════════════════════════════════════════════════════

class _PanelGlass(QWidget):
    """ControlPanel 的毛玻璃背景 — 画圆角矩形 + QGraphicsBlurEffect"""

    def __init__(self, parent, color: list, blur_radius: int, corner_radius: int):
        super().__init__(parent)
        self._color = QColor(color[0], color[1], color[2], color[3])
        self._cr = corner_radius
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._blur = QGraphicsBlurEffect(self)
        self._blur.setBlurRadius(blur_radius)
        self.setGraphicsEffect(self._blur)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), self._cr, self._cr)


# ═══════════════════════════════════════════════════════════════
# 毛玻璃背景层（仅圆形态可见，不受 QGraphicsBlurEffect 影响柱子）
# ═══════════════════════════════════════════════════════════════

class GlassBg(QWidget):
    """
    毛玻璃背景子控件：
    - 圆形态：画圆形，带 QGraphicsBlurEffect → Mica 效果
    - 展开态：隐藏（透明），让柱子浮在桌面上
    - 过渡态：画变形的圆角矩形
    """

    def __init__(self, parent, color: list, blur_radius: int):
        super().__init__(parent)
        self._color = list(color)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._blur = QGraphicsBlurEffect(self)
        self._blur.setBlurRadius(blur_radius)
        self.setGraphicsEffect(self._blur)

    def set_color(self, c: list):
        self._color = list(c)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*self._color))
        w, h = self.width(), self.height()

        if w == h:
            # 正圆形
            c = w // 2
            p.drawEllipse(QPoint(c, c), c, c)
        else:
            # 圆角矩形（展开中 / 展开后）
            r = min(h // 2, 12)
            p.drawRoundedRect(0, 0, w, h, r, r)


# ═══════════════════════════════════════════════════════════════
# 气泡主窗口
# ═══════════════════════════════════════════════════════════════

class BubbleWidget(QWidget):
    CLICK_THRESHOLD = 5
    DEBOUNCE_MS = 500

    # Qt 信号：跨线程安全地将歌曲信息从后台线程传递到主线程
    _song_info_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        cb = self.config["bubble"]
        cbr = self.config["beatbar"]

        # ── 尺寸 ──
        self.bubble_size = cb["size"]
        self.bar_wid = cbr["width"]
        self.bar_hei = cbr["height"]
        self.hover_scale = cb["hover_scale"]

        # ── 柱子参数 ──
        self._n_bars = cbr["bar_count"]
        self._bw = cbr["bar_width"]
        self._bgap = cbr["bar_gap"]
        self._brad = cbr["bar_radius"]
        self._bmin = cbr["min_height_ratio"]
        self._bmax = cbr["max_height_ratio"]
        self._bspeed = cbr["speed"]
        self._fps = cbr["fps"]
        self._expand_ms = cbr["expand_duration_ms"]
        bc = cbr["bar_color"]
        self._bar_color = QColor(bc[0], bc[1], bc[2], bc[3])

        # ── 状态 ──
        self._expanded = False
        self._animating = False
        self._expand_progress = 0.0
        self._phase = 0.0

        # 歌曲信息（后台 UIA 读取）
        self.current_song_info = {"title": "", "artist": "", "lyric": ""}

        # 拖拽 / 点击
        self._drag_pos: QPoint | None = None
        self._press_pos: QPoint | None = None
        self._last_click = 0

        # 操作面板（面板自带 5 秒自动消失计时）
        self._panel_open = False
        self._panel: ControlPanel | None = None

        # 播放进度追踪
        self._is_playing = False       # 播放/暂停状态
        self._playback_elapsed = 0.0   # 当前歌曲已播放秒数
        self._playback_start = 0.0     # 开始播放的时间戳
        self._last_song_key = ""       # 用于检测切歌
        self._last_toggle_time = 0.0  # 气泡主动切换的时间戳，用于防抖
        self._song_duration = 240.0    # 默认歌曲时长 4 分钟
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_timer.start(250)  # 每 250ms 更新一次进度条

        # ── 窗口 ──
        self.setWindowTitle("minemusic")
        self.setFixedSize(self.bubble_size, self.bubble_size)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)   # 主窗口完全透明
        self.setWindowOpacity(cb["opacity"])

        # ── 毛玻璃背景层（圆形态可见，展开后隐藏）──
        self._glass = GlassBg(self, cb["color_bg"], cb["blur_radius"])
        self._glass.setGeometry(0, 0, self.bubble_size, self.bubble_size)

        # ── 音符图标（圆形态可见）──
        ic = cb["icon"]
        self.icon_label = QLabel(ic, self)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.icon_label.setFont(QFont("Segoe UI Symbol", cb["icon_size"]))
        ci = cb["color_icon"]
        self.icon_label.setStyleSheet(f"color: rgb({ci[0]},{ci[1]},{ci[2]}); background: transparent;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setGeometry(0, 0, self.bubble_size, self.bubble_size)

        # ── 展开动画 ──
        self._anim = QPropertyAnimation(self, b"expand_progress")
        self._anim.setDuration(self._expand_ms)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_done)

        # ── 柱条动画 ──
        self._bar_timer = QTimer(self)
        self._bar_timer.timeout.connect(self._tick)

        # ── 音频捕获（真实频谱）──
        self._audio = AudioCapture()
        self._audio_enabled = False  # 展开时根据启动结果设置

        # ── 频谱渲染器 ──
        self._renderers = {}        # name → renderer 实例
        self._current_renderer: SpectrumRenderer | None = None

        # ── 定位 ──
        scr = QApplication.primaryScreen().geometry()
        self.move(scr.width() - self.bubble_size - 40,
                  scr.height() - self.bubble_size - 80)
        self.setMouseTracking(True)

        # ── 后台歌曲信息读取 ──
        # 通过 Qt 信号将回调调度到主线程（pyqtSignal 跨线程 emit 是安全的）
        self._song_info_signal.connect(self._on_song_info)
        self._song_reader = SongInfoReader(self.config)
        self._song_thread = threading.Thread(
            target=self._song_reader.run,
            args=(self._song_info_signal.emit,),
            daemon=True,
        )
        self._song_thread.start()

        # ── 全局事件过滤器（检测点击面板外部） ──
        QApplication.instance().installEventFilter(self)

    # ── 歌曲信息回调 ────────────────────────────────────

    def _tick_progress(self):
        """每 250ms 更新一次进度条位置"""
        if self._is_playing:
            elapsed = self._playback_elapsed + (time.time() - self._playback_start)
            pct = min(int(elapsed / self._song_duration * 100), 100)
            if self._panel_open and self._panel:
                self._panel.progress.setValue(pct)

    def _on_song_info(self, info: dict | None):
        """接收后台线程读取的歌曲信息（含播放状态）

        info 为 None 表示本次未读到 QQ 音乐窗口 → 跳过显示更新和状态同步
        """
        if info is None:
            return  # 没读到数据，不更新也不做同步

        # 检测切歌 → 重置进度
        song_key = f"{info.get('title','')}|{info.get('artist','')}"
        if song_key != self._last_song_key and self._last_song_key:
            self._playback_elapsed = 0.0
            self._playback_start = time.time()
        self._last_song_key = song_key
        self.current_song_info = info

        # 如果面板已打开，实时更新
        if self._panel_open and self._panel:
            self._panel.set_song_info(info)

        # ── 播放状态自动同步（双向绑定核心）──
        # 气泡主动切换后 0.8 秒内不响应外部检测，避免反馈循环
        # 仅当本次成功读取到 is_playing 时才做同步
        if "is_playing" in info and time.time() - self._last_toggle_time > 0.8:
            self._sync_playback_state(info["is_playing"])

    # ── 面板显示/隐藏 ──────────────────────────────────

    def _show_panel(self):
        """在跳动条正上方显示操作面板（面板自己管理 5 秒自动消失）"""
        try:
            if self._panel is None:
                self._panel = ControlPanel(self.config)
                self._panel.hide_requested.connect(self._on_panel_hide_requested)
                self._panel.play_paused.connect(self._on_play_pause)
                self._panel.prev_clicked.connect(self._on_prev_next)
                self._panel.next_clicked.connect(self._on_prev_next)
                self._panel.seeked.connect(self._on_seeked)
                self._panel.exit_requested.connect(self._quit_app)
                self._panel.spectrum_menu_clicked.connect(self._show_spectrum_menu)
            self._panel.set_song_info(self.current_song_info)
            self._position_panel()
            self._panel.show()  # showEvent 会启动面板自带的 5 秒计时
            self._panel_open = True
        except Exception as e:
            log(f"打开面板失败: {e}")
            self._panel_open = False

    def _hide_panel(self):
        """隐藏操作面板"""
        if self._panel:
            self._panel.hide()  # hideEvent 会停止计时
        self._panel_open = False

    def _on_panel_hide_requested(self):
        """面板自己的计时器到 5 秒 → 请求隐藏"""
        if self._panel_open:
            log("面板 5 秒无操作 → 自动收起")
            self._hide_panel()

    def _on_play_pause(self):
        """面板播放/暂停按钮被点击 → 同步播放状态 + 视觉状态"""
        self._last_toggle_time = time.time()  # 防抖
        if self._is_playing:
            # 当前播放中 → 暂停 → 收回气泡
            self._playback_elapsed += time.time() - self._playback_start
            self._is_playing = False
            self._collapse()
        else:
            # 当前暂停中 → 播放 → 展开跳动条
            self._is_playing = True
            self._playback_start = time.time()
            self._expand()

    def _on_prev_next(self):
        """面板上/下一首按钮被点击 → 重置进度 + 保证展开状态"""
        self._last_toggle_time = time.time()  # 防抖
        self._playback_elapsed = 0.0
        self._playback_start = time.time()
        if not self._is_playing:
            self._is_playing = True
        if not self._expanded:
            self._expand()

    def _on_seeked(self, pct: int):
        """用户拖动进度条 → 同步内部计时到目标位置"""
        self._playback_elapsed = pct / 100.0 * self._song_duration
        self._playback_start = time.time()

    def _position_panel(self):
        """将面板定位到跳动条正上方"""
        if self._panel:
            self._panel.position_above(self)

    # ── 全局事件过滤器（点击面板外部时关闭面板） ──────

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and self._panel_open and self._panel:
            try:
                pos = event.globalPos()
                in_panel = self._panel.geometry().contains(pos)
                in_bubble = self.geometry().contains(pos)
                if not in_panel and not in_bubble:
                    log("点击面板外部 → 收起面板")
                    self._hide_panel()
            except Exception:
                pass  # 窗口销毁过程中的边界情况
        return super().eventFilter(obj, event)

    def _quit_app(self):
        """完整退出程序：暂停音乐 → 关闭面板 → 关闭窗口 → 退出事件循环"""
        log("用户点击退出 → 关闭乐泡")
        # 如果正在播放，先暂停音乐再退出
        if self._is_playing:
            self._playback_elapsed += time.time() - self._playback_start
            self._is_playing = False
            threading.Thread(
                target=_send_media_play_pause,
                daemon=True,
            ).start()
        # 隐藏并关闭面板
        if self._panel:
            try:
                self._panel.hide()
                self._panel.close()
            except Exception:
                pass
            self._panel = None
        # 关闭气泡窗口（会触发 closeEvent）
        self.close()
        # 退出 Qt 事件循环
        QApplication.instance().quit()

    def closeEvent(self, event):
        """清理：停止定时器、关闭面板、移除事件过滤器"""
        # 停止所有定时器
        self._bar_timer.stop()
        self._progress_timer.stop()
        # 移除全局事件过滤器
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        # 关闭面板
        if self._panel:
            try:
                self._panel.close()
            except Exception:
                pass
            self._panel = None
        super().closeEvent(event)

    # ── expand_progress 属性 ──────────────────────────────

    def get_expand_progress(self) -> float:
        return self._expand_progress

    def set_expand_progress(self, v: float):
        self._expand_progress = v
        w = int(self.bubble_size + (self.bar_wid - self.bubble_size) * v)
        h = int(self.bubble_size + (self.bar_hei - self.bubble_size) * v)
        old_right = self.x() + self.width()
        self.setFixedSize(w, h)
        self.move(old_right - w, self.y())

        # 玻璃背景跟随大小
        self._glass.setGeometry(0, 0, w, h)
        # 玻璃在展开超过一半后隐藏 → 背景变透明
        self._glass.setVisible(v < 0.55)
        # 图标也同步隐藏
        self.icon_label.setVisible(v < 0.4)
        if v < 0.4:
            self.icon_label.setGeometry(0, 0, self.bubble_size, self.bubble_size)

        self.update()

    expand_progress = pyqtProperty(float, get_expand_progress, set_expand_progress)

    # ── 绘制 ─────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 展开态：只画柱子，不画背景（背景由 GlassBg 或透明处理）
        if self._expand_progress > 0.55:
            self._draw_bars(p)

    def _draw_bars(self, p: QPainter):
        """绘制频谱 — 委派给当前渲染器"""
        self._ensure_renderers()

        w, h = self.width(), self.height()

        # 获取频谱数据
        if self._audio_enabled:
            levels = self._audio.get_levels()
        else:
            levels = None

        if levels is None:
            # 假动效：5 个正弦波值
            levels = []
            for i in range(self._n_bars):
                offset = (i / (self._n_bars - 1)) * math.pi if self._n_bars > 1 else 0
                levels.append(
                    self._bmin + (math.sin(self._phase + offset) + 1.0) / 2.0 * (self._bmax - self._bmin)
                )

        if self._current_renderer:
            self._current_renderer.draw(p, levels, w, h, self.config["beatbar"])

    def _ensure_renderers(self):
        """惰性初始化渲染器注册表"""
        if self._current_renderer is not None:
            return

        self._renderers["bars"] = BarRenderer()
        self._renderers["wave"] = WaveRenderer()
        self._renderers["circle"] = CircleRenderer()
        self._renderers["particle"] = ParticleRenderer()
        self._renderers["water"] = WaterRenderer()

        style = self.config.get("spectrum", {}).get("style", "bars")
        self._current_renderer = self._renderers.get(style, self._renderers["bars"])

    def _set_spectrum_style(self, style_key: str):
        """切换频谱样式"""
        self._ensure_renderers()
        if style_key in self._renderers:
            self._current_renderer = self._renderers[style_key]
            self.config.setdefault("spectrum", {})["style"] = style_key
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            log(f"频谱样式 → {self._renderers[style_key].name}")

    # ── 柱条动画 ─────────────────────────────────────────

    def _tick(self):
        if not self._audio_enabled:
            self._phase += self._bspeed / self._fps
            if self._phase > 2 * math.pi:
                self._phase -= 2 * math.pi
        # 渲染器每帧 tick（心电波等需要内部动画）
        if self._current_renderer:
            self._current_renderer.tick(self._bspeed, self._fps)
        self.update()

    # ── 展开 / 收起 ──────────────────────────────────────

    def _expand(self):
        """展开气泡 → 跳动条"""
        if self._expanded or self._animating:
            return
        self._animating = True
        self._anim.stop()
        self._anim.setDirection(QPropertyAnimation.Forward)
        self._anim.start()

    def _collapse(self):
        """收回跳动条 → 气泡"""
        if not self._expanded or self._animating:
            return
        self._animating = True
        self._anim.stop()
        self._anim.setDirection(QPropertyAnimation.Backward)
        self._anim.start()

    def _on_anim_done(self):
        """展开/收回动画完成回调"""
        try:
            if self._expand_progress > 0.9:
                self._expanded = True
                self._animating = False
                self.icon_label.hide()
                self._glass.hide()
                self._bar_timer.start(1000 // self._fps)
                # 尝试启动真实音频频谱
                self._audio_enabled = self._audio.start()
                if not self._audio_enabled:
                    log("音频捕获未就绪 → 使用假动效")
                if self.rect().contains(self.mapFromGlobal(self.cursor().pos())):
                    self._show_panel()
            else:
                self._expanded = False
                self._animating = False
                self.icon_label.show()
                self._glass.show()
                self._bar_timer.stop()
                self._phase = 0.0
                # 停止音频捕获
                self._audio.stop()
                self._audio_enabled = False
        except Exception as e:
            log(f"动画回调异常: {e} → 强制重置")
            self._expanded = False
            self._animating = False

    # ── Windows 原生消息 → 接收其他实例的激活请求 ──────────

    def nativeEvent(self, eventType, message):
        """处理 Windows 原生消息

        - WM_BUBBLE_ACTIVATE：第二个实例发送的激活请求
        - WM_MOUSEWHEEL (0x020A)：鼠标滚轮 → 调节系统音量
        """
        if eventType == b"windows_generic_MSG":
            msg_ptr = ctypes.c_void_p(int(message))
            msg = ctypes.cast(msg_ptr, ctypes.POINTER(_MSG)).contents

            if msg.message == WM_BUBBLE_ACTIVATE:
                self._activate_from_second_instance()
                return True, 0

            elif msg.message == 0x020A:  # WM_MOUSEWHEEL
                # wParam 高 16 位 = 滚轮增量（正=上滚，负=下滚）
                delta = ctypes.c_short((msg.wParam >> 16) & 0xFFFF).value
                if delta > 0:
                    _send_media_key(VK_VOLUME_UP)
                elif delta < 0:
                    _send_media_key(VK_VOLUME_DOWN)
                return True, 0

        return super().nativeEvent(eventType, message)

    def _activate_from_second_instance(self):
        """第二个实例触发 → 切换播放/暂停状态

        - 收起态（气泡）→ 展开跳动条 + 恢复播放
        - 展开态（跳动条）→ 暂停播放 + 收起为气泡
        """
        if self._animating:
            return  # 正在动画中，忽略

        if self._expanded:
            # 展开态 → 暂停并收回
            log("收到激活请求 → 暂停并收回气泡")
            self._last_toggle_time = time.time()  # 防抖
            self._hide_panel()
            self._collapse()
            if self._is_playing:
                self._playback_elapsed += time.time() - self._playback_start
            self._is_playing = False
            threading.Thread(
                target=_do_media_control,
                args=(self.config,),
                daemon=True,
            ).start()
        else:
            # 收起态 → 展开并播放
            log("收到激活请求 → 恢复播放并展开跳动条")
            self._last_toggle_time = time.time()  # 防抖
            self._expand()
            if not self._is_playing:
                self._is_playing = True
                self._playback_start = time.time()
                threading.Thread(
                    target=_do_media_control,
                    args=(self.config,),
                    daemon=True,
                ).start()

    def _sync_playback_state(self, is_playing: bool):
        """外部播放状态变化 → 同步气泡视觉状态（双向绑定的"外→内"方向）

        - QQ 音乐开始播放 → 展开跳动条（如果还在气泡状态）
        - QQ 音乐暂停     → 收回气泡（如果还在跳动条状态）
        """
        if self._animating:
            return

        if is_playing and not self._expanded:
            # 外部开始播放，气泡还在收起状态 → 展开
            log("检测到外部播放 → 自动展开跳动条")
            self._last_toggle_time = time.time()  # 防抖：阻止后续立即回调
            self._expand()
            self._is_playing = True
            self._playback_start = time.time()
        elif not is_playing and self._expanded:
            # 外部暂停，还在跳动条状态 → 收回
            log("检测到外部暂停 → 自动收回气泡")
            self._last_toggle_time = time.time()  # 防抖：阻止后续立即回调
            self._hide_panel()
            self._collapse()
            if self._is_playing:
                self._playback_elapsed += time.time() - self._playback_start
            self._is_playing = False

    # ── 滚轮调音量 ───────────────────────────────────────

    def wheelEvent(self, ev):
        """鼠标滚轮调节系统音量：上滚增大，下滚减小"""
        delta = ev.angleDelta().y()
        if delta > 0:
            _send_media_key(VK_VOLUME_UP)
        elif delta < 0:
            _send_media_key(VK_VOLUME_DOWN)

    # ── 鼠标 ─────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPos() - self.frameGeometry().topLeft()
            self._press_pos = ev.pos()

    def mouseMoveEvent(self, ev):
        if ev.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(ev.globalPos() - self._drag_pos)
            if self._panel_open and self._panel:
                self._position_panel()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._press_pos is not None:
            d = ev.pos() - self._press_pos
            if d.manhattanLength() < self.CLICK_THRESHOLD:
                self._on_click()
        self._drag_pos = None
        self._press_pos = None

    # ── 悬停放大（仅圆形态） ─────────────────────────────

    def enterEvent(self, ev):
        if self._animating:
            return
        if self._expanded:
            # 跳动条态 → 鼠标悬停自动弹出面板
            if not self._panel_open:
                self._show_panel()
            return
        # 气泡态 → 悬停放大
        s = self.hover_scale
        ns = int(self.bubble_size * s)
        d = ns - self.bubble_size
        old_r = self.x() + self.width()
        self.setFixedSize(ns, ns)
        self.move(old_r - ns, self.y() - d // 2)
        self._glass.setGeometry(0, 0, ns, ns)
        self.icon_label.setGeometry(0, 0, ns, ns)

    def _show_spectrum_menu(self, pos: QPoint):
        """在面板按钮下方弹出频谱样式菜单"""
        self._ensure_renderers()
        self._reset_panel_hide()

        menu = QMenu(self)

        for key, renderer in self._renderers.items():
            action = QAction(renderer.name, menu, checkable=True)
            action.setChecked(renderer is self._current_renderer)
            action.triggered.connect(
                lambda checked, k=key: self._set_spectrum_style(k)
            )
            menu.addAction(action)

        menu.exec_(pos)

    def _reset_panel_hide(self):
        """重置面板自动隐藏计时"""
        if self._panel_open and self._panel:
            self._panel._reset_hide_timer()

    def leaveEvent(self, ev):
        if self._expanded or self._animating:
            return
        # 气泡态 → 恢复原大小
        s = self.hover_scale
        ns = int(self.bubble_size * s)
        d = ns - self.bubble_size
        old_r = self.x() + self.width()
        self.setFixedSize(self.bubble_size, self.bubble_size)
        self.move(old_r + d - self.bubble_size, self.y() + d // 2)
        self._glass.setGeometry(0, 0, self.bubble_size, self.bubble_size)
        self.icon_label.setGeometry(0, 0, self.bubble_size, self.bubble_size)

    # ── 点击 ─────────────────────────────────────────────

    def _on_click(self):
        t = int(time.time() * 1000)
        if t - self._last_click < self.DEBOUNCE_MS:
            return
        self._last_click = t

        if self._expanded:
            # 跳动条被点击 → 暂停 + 收回气泡
            log("跳动条被点击 → 暂停并收回")
            self._last_toggle_time = time.time()  # 防抖
            self._hide_panel()
            self._collapse()
            # 停止进度计时
            if self._is_playing:
                self._playback_elapsed += time.time() - self._playback_start
            self._is_playing = False
            threading.Thread(target=_do_media_control, args=(self.config,), daemon=True).start()
        else:
            # 气泡被点击 → 展开跳动条 + 播放
            log("点击气泡 → 展开跳动条")
            self._last_toggle_time = time.time()  # 防抖
            self._expand()
            # 开始/恢复进度计时
            if self._is_playing:
                self._playback_elapsed += time.time() - self._playback_start
            self._is_playing = not self._is_playing
            if self._is_playing:
                self._playback_start = time.time()
            threading.Thread(target=_do_media_control, args=(self.config,), daemon=True).start()


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

# Windows 命名互斥体 — 保证全局只有一个气泡实例
# Local\ 前缀：当前用户会话内唯一，无需管理员权限
_MUTEX_NAME = "Local\\MiniMusic_SingleInstance_8A7F3B2C"
_kernel32 = ctypes.windll.kernel32

_mutex_handle = None


def _acquire_lock() -> bool:
    """使用 Windows 内核互斥体确保单实例运行

    CreateMutexW 创建的命名互斥体在当前会话内唯一。
    第二个实例调用时 GetLastError() 返回 ERROR_ALREADY_EXISTS (183)。
    如果 CreateMutexW 本身失败（如权限问题），宁可允许多实例也不能阻止启动。
    """
    global _mutex_handle
    _mutex_handle = _kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not _mutex_handle:
        # 互斥体创建失败（非"已存在"错误）→ 记录并允许启动
        log(f"⚠ CreateMutex 失败 (错误码: {_kernel32.GetLastError()})，跳过单实例检查")
        return True
    error = _kernel32.GetLastError()
    return error != 183  # ERROR_ALREADY_EXISTS → 已有实例


def _release_lock():
    """释放互斥体（进程退出时 Windows 也会自动释放）"""
    global _mutex_handle
    if _mutex_handle:
        _kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None


def _notify_existing_instance():
    """通过 Windows 消息通知已有气泡实例：恢复播放 + 展开跳动条"""
    hwnd = ctypes.windll.user32.FindWindowW(None, "minemusic")
    if hwnd:
        ctypes.windll.user32.PostMessageW(hwnd, WM_BUBBLE_ACTIVATE, 0, 0)
        log(f"已通知现有实例 (hwnd={hwnd}) → 恢复播放并展开")
    else:
        log("未找到现有气泡窗口，无法发送激活通知")


def main():
    if not _acquire_lock():
        # 已有实例在运行 → 通知对方恢复播放 + 展开跳动条
        _notify_existing_instance()
        sys.exit(0)

    import io, atexit
    atexit.register(_release_lock)
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception: pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    b = BubbleWidget()
    b.show()

    # 强制在任务栏显示（Qt.Tool 窗口默认不显示在任务栏）
    hwnd = int(b.winId())
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_APPWINDOW)

    # ── 系统托盘图标 ──
    icon_path = os.path.join(_data_dir(), "icons", "app.ico")
    tray = QSystemTrayIcon()
    if os.path.exists(icon_path):
        tray.setIcon(QIcon(icon_path))
    else:
        tray.setIcon(app.style().standardIcon(app.style().SP_MediaPlay))
    tray.setToolTip("minemusic")

    # 右键菜单
    tray_menu = QMenu()
    toggle_action = QAction("显示/隐藏", tray_menu)
    toggle_action.triggered.connect(lambda: b.setVisible(not b.isVisible()))
    tray_menu.addAction(toggle_action)
    tray_menu.addSeparator()
    quit_action = QAction("退出", tray_menu)
    quit_action.triggered.connect(b._quit_app)
    tray_menu.addAction(quit_action)
    tray.setContextMenu(tray_menu)

    # 左键点击托盘 → 切换显示/隐藏
    tray.activated.connect(lambda reason: (
        b.setVisible(not b.isVisible()) if reason == QSystemTrayIcon.Trigger else None
    ))
    tray.show()

    # 退出时自动清理托盘图标
    app.aboutToQuit.connect(tray.hide)

    # 将托盘引用挂到气泡上，防止被垃圾回收
    b._tray = tray

    log("气泡已启动 — 单击展开跳动条 + QQ音乐控制")
    code = app.exec_()
    _release_lock()
    sys.exit(code)

if __name__ == "__main__":
    main()
