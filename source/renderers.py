"""
频谱渲染器 — 柱状 / 心电波 / 圆环 / 粒子 / 水波
===================================================
所有渲染器继承 SpectrumRenderer，
覆写 draw() 和 name 属性即可接入跳动条。
"""

import math
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QPen, QBrush, QPainterPath


class SpectrumRenderer:
    """频谱渲染器基类"""

    name: str = "基类"

    def draw(self, p: QPainter, levels: list[float],
             w: int, h: int, cfg: dict):
        """
        绘制一帧频谱。

        Args:
            p:      QPainter
            levels: 5 个 float (0~1)
            w, h:   跳动条区域的宽和高
            cfg:    config["beatbar"]
        """
        raise NotImplementedError

    def tick(self, speed: float, fps: int) -> float:
        """每帧调用，返回当前相位。默认不做任何事"""
        return 0.0


# ─────────────────────────────────────────────────
#  柱状图（当前默认，从 main.py 迁移）
# ─────────────────────────────────────────────────

class BarRenderer(SpectrumRenderer):
    """经典柱状频谱 — 5 根竖向柱，顶部渐变到根部"""

    name = "柱状图"

    def draw(self, p: QPainter, levels: list[float],
             w: int, h: int, cfg: dict):
        n_bars = cfg.get("bar_count", 5)
        bw = cfg.get("bar_width", 10)
        gap = cfg.get("bar_gap", 8)
        radius = cfg.get("bar_radius", 5)
        bar_color = cfg.get("bar_color", [0, 0, 0, 200])
        min_ratio = cfg.get("min_height_ratio", 0.12)
        max_ratio = cfg.get("max_height_ratio", 0.95)

        c = QColor(bar_color[0], bar_color[1], bar_color[2], bar_color[3])

        total_w = n_bars * bw + (n_bars - 1) * gap
        start_x = (w - total_w) // 2
        base_y = h - 2

        for i in range(n_bars):
            if i < len(levels):
                ratio = min_ratio + levels[i] * (max_ratio - min_ratio)
            else:
                ratio = min_ratio

            bh = max(2, int((h - 4) * ratio))
            x = start_x + i * (bw + gap)
            y = base_y - bh

            grad = QLinearGradient(x, y, x, base_y)
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 230))
            grad.setColorAt(0.6, QColor(c.red(), c.green(), c.blue(), 180))
            grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 60))

            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(x, y, bw, bh, radius, radius)


# ─────────────────────────────────────────────────
#  波形曲线 — 平滑贝塞尔连接 5 个频段
# ─────────────────────────────────────────────────

class WaveRenderer(SpectrumRenderer):
    """心电波 — 尖锐折线，随机跳动，像心电图，带光晕"""

    name = "心电波"

    def __init__(self):
        import random as _r
        self._r = _r
        self._phases = [_r.random() * 3.14 for _ in range(5)]
        self._targets = [0.3] * 5
        self._values = [0.15] * 5

    def tick(self, speed: float, fps: int) -> float:
        """快速随机游走 + 偶尔尖峰，模拟不规则跳动"""
        for i in range(5):
            # 每约 0.8 秒换个随机目标
            self._phases[i] += speed / fps * 2.5
            if self._phases[i] > 3.14:
                self._phases[i] -= 3.14
                # 偶尔来一个尖峰
                if self._r.random() < 0.35:
                    self._targets[i] = self._r.random() * 0.55 + 0.30  # 高尖峰
                else:
                    self._targets[i] = self._r.random() * 0.50 + 0.05  # 普通幅度
            # 快速趋近目标（不稳定感）
            self._values[i] += (self._targets[i] - self._values[i]) * 0.25
        return 0.0

    def draw(self, p: QPainter, levels: list[float],
             w: int, h: int, cfg: dict):
        bar_color = cfg.get("bar_color", [0, 0, 0, 200])
        c = QColor(bar_color[0], bar_color[1], bar_color[2], bar_color[3])
        n = 5

        p.setRenderHint(QPainter.Antialiasing)

        margin = 10
        area_w = w - 2 * margin
        base_y = h - 5
        area_h = h - 10

        # 用内部随机值
        xs = []
        ys = []
        for i in range(n):
            ratio = self._values[i]
            xs.append(margin + int(area_w * i / (n - 1)))
            ys.append(base_y - int(area_h * ratio))

        # ── 心电折线 ──
        path = QPainterPath()
        path.moveTo(xs[0], base_y)
        path.lineTo(xs[0], ys[0])
        for i in range(1, n):
            path.lineTo(xs[i], ys[i])
        path.lineTo(xs[-1], base_y)

        # ── 光晕 ──
        glow_pen = QPen(QColor(c.red(), c.green(), c.blue(), 50), 5.0,
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(glow_pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # ── 主线条 ──
        main_pen = QPen(QColor(c.red(), c.green(), c.blue(), 200), 1.8,
                        Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(main_pen)
        p.drawPath(path)

        # ── 峰值亮点 ──
        p.setPen(Qt.NoPen)
        glow_dot = QColor(c.red(), c.green(), c.blue(), 200)
        for i in range(n):
            p.setBrush(glow_dot)
            p.drawEllipse(QPoint(xs[i], ys[i]), 2, 2)


# ─────────────────────────────────────────────────
#  辐射圆环 — 5 根柱从中心向外辐射
# ─────────────────────────────────────────────────

class CircleRenderer(SpectrumRenderer):
    """辐射圆环 — 5 根柱从圆心向外伸展，像圆形均衡器"""

    name = "辐射圆环"

    def __init__(self):
        import random as _r
        self._r = _r
        self._phases = [_r.random() * 3.14 for _ in range(5)]
        self._targets = [0.3] * 5
        self._values = [0.15] * 5

    def tick(self, speed: float, fps: int) -> float:
        for i in range(5):
            self._phases[i] += speed / fps * 2.5
            if self._phases[i] > 3.14:
                self._phases[i] -= 3.14
                if self._r.random() < 0.35:
                    self._targets[i] = self._r.random() * 0.55 + 0.30
                else:
                    self._targets[i] = self._r.random() * 0.50 + 0.05
            self._values[i] += (self._targets[i] - self._values[i]) * 0.25
        return 0.0

    def draw(self, p: QPainter, levels: list[float],
             w: int, h: int, cfg: dict):
        bar_color = cfg.get("bar_color", [0, 0, 0, 200])
        c = QColor(bar_color[0], bar_color[1], bar_color[2], bar_color[3])
        n = 5

        p.setRenderHint(QPainter.Antialiasing)

        cx, cy = w // 2, h // 2
        max_r = min(w, h) // 2 - 6

        # 5 根柱均匀分布 180°（上半圆），角度从 -90° 到 +90°
        angles = [-90, -45, 0, 45, 90]

        for i in range(n):
            ratio = self._values[i]
            bar_len = int(max_r * ratio)
            angle_rad = math.radians(angles[i])

            inner_r = 4  # 中心留空
            outer_r = inner_r + max(2, bar_len)

            x1 = cx + int(inner_r * math.cos(angle_rad))
            y1 = cy - int(inner_r * math.sin(angle_rad))
            x2 = cx + int(outer_r * math.cos(angle_rad))
            y2 = cy - int(outer_r * math.sin(angle_rad))

            # 辐射柱：根细顶粗
            grad = QLinearGradient(x1, y1, x2, y2)
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 80))
            grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 220))

            pen = QPen(QBrush(grad), 4.0, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(x1, y1, x2, y2)

            # 顶端亮点
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 220))
            p.drawEllipse(QPoint(x2, y2), 3, 3)

        # 中心点
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 180))
        p.drawEllipse(QPoint(cx, cy), 3, 3)


# ─────────────────────────────────────────────────
#  粒子喷射 — 光点从底部飞升，带拖尾
# ─────────────────────────────────────────────────

class ParticleRenderer(SpectrumRenderer):
    """粒子喷射 — 5 列粒子从底部向上升起，高度随频谱跳动，带拖尾"""

    name = "粒子喷射"

    def __init__(self):
        import random as _r
        self._r = _r
        self._phases = [_r.random() * 3.14 for _ in range(5)]
        self._targets = [0.3] * 5
        self._values = [0.15] * 5
        # 每列的历史粒子位置 [(y, opacity), ...]
        self._trails = [[] for _ in range(5)]

    def tick(self, speed: float, fps: int) -> float:
        for i in range(5):
            self._phases[i] += speed / fps * 2.5
            if self._phases[i] > 3.14:
                self._phases[i] -= 3.14
                if self._r.random() < 0.35:
                    self._targets[i] = self._r.random() * 0.55 + 0.30
                else:
                    self._targets[i] = self._r.random() * 0.50 + 0.05
            self._values[i] += (self._targets[i] - self._values[i]) * 0.25

            # 向拖尾追加新粒子
            self._trails[i].append([self._values[i], 1.0])
            # 衰减旧粒子
            for t in self._trails[i]:
                t[1] -= 0.12  # 透明度衰减
            # 去掉已消失的
            self._trails[i] = [t for t in self._trails[i] if t[1] > 0]
            # 最多保留 8 个
            if len(self._trails[i]) > 8:
                self._trails[i] = self._trails[i][-8:]
        return 0.0

    def draw(self, p: QPainter, levels: list[float],
             w: int, h: int, cfg: dict):
        bar_color = cfg.get("bar_color", [0, 0, 0, 200])
        c = QColor(bar_color[0], bar_color[1], bar_color[2], bar_color[3])
        n = 5

        p.setRenderHint(QPainter.Antialiasing)

        margin = 10
        area_w = w - 2 * margin
        base_y = h - 4
        area_h = h - 8

        for i in range(n):
            x = margin + int(area_w * i / (n - 1))
            ratio = self._values[i]
            top_y = base_y - int(area_h * ratio)

            # 主粒子（当前高度）
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 220))
            p.drawEllipse(QPoint(x, top_y), 3, 3)

            # 拖尾粒子（历史位置，渐淡）
            for val, alpha in self._trails[i][:-1]:  # 跳过最新（已画）
                trail_y = base_y - int(area_h * val)
                a = int(alpha * 120)
                if a > 0:
                    p.setBrush(QColor(c.red(), c.green(), c.blue(), a))
                    p.drawEllipse(QPoint(x, trail_y), 2, 2)

            # 底部微光
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 40))
            p.drawEllipse(QPoint(x, base_y), 2, 2)


# ─────────────────────────────────────────────────
#  水波纹 — 多层正弦波浪叠加，像水面涟漪
# ─────────────────────────────────────────────────

class WaterRenderer(SpectrumRenderer):
    """水波纹 — 3 层正弦波浪叠加，振幅随机跳动，流体感"""

    name = "水波纹"

    def __init__(self):
        import random as _r
        self._r = _r
        self._phases = [_r.random() * 3.14 for _ in range(3)]
        self._targets = [0.3, 0.35, 0.25]
        self._values = [0.2, 0.25, 0.15]
        self._shift = 0.0  # 水平流动相位

    def tick(self, speed: float, fps: int) -> float:
        self._shift += speed / fps * 0.6
        for i in range(3):
            self._phases[i] += speed / fps * 2.0
            if self._phases[i] > 3.14:
                self._phases[i] -= 3.14
                if self._r.random() < 0.3:
                    self._targets[i] = self._r.random() * 0.4 + 0.25
                else:
                    self._targets[i] = self._r.random() * 0.35 + 0.08
            self._values[i] += (self._targets[i] - self._values[i]) * 0.2
        return 0.0

    def draw(self, p: QPainter, levels: list[float],
             w: int, h: int, cfg: dict):
        bar_color = cfg.get("bar_color", [0, 0, 0, 200])
        c = QColor(bar_color[0], bar_color[1], bar_color[2], bar_color[3])

        p.setRenderHint(QPainter.Antialiasing)
        cy = h // 2

        # 3 层波浪，从浅到深
        layers = [
            {"amp_idx": 0, "freq": 14, "offset": 0,   "alpha": 60},   # 背面层
            {"amp_idx": 1, "freq": 20, "offset": 1.2, "alpha": 120},  # 中间层
            {"amp_idx": 2, "freq": 26, "offset": 2.5, "alpha": 180},  # 前景层
        ]

        for layer in layers:
            amp = self._values[layer["amp_idx"]]
            freq = layer["freq"]
            alpha = layer["alpha"]

            path = QPainterPath()
            first = True
            for x in range(0, w + 2, 2):
                # 正弦波：y = cy + amplitude * sin(freq * x/w * 2pi + shift + offset)
                phase = (freq * x / w * 6.28
                         + self._shift
                         + layer["offset"])
                y = cy + int(amp * (h // 3) * math.sin(phase))

                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)

            pen = QPen(QColor(c.red(), c.green(), c.blue(), alpha), 1.5,
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
