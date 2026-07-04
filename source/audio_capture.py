"""
WASAPI 环回捕获 → FFT 频谱分析
=================================
使用 soundcard 库（封装 Windows WASAPI loopback），
捕获系统音频输出，FFT 后输出 5 频段频谱数据。
"""

import threading
import time
import numpy as np


class AudioCapture:
    """后台 WASAPI 环回捕获 → FFT → 频谱数据"""

    # 频段分布（Hz）
    BANDS = [
        (20, 60), (60, 250), (250, 2000), (2000, 6000), (6000, 20000),
    ]

    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = False
        self._running = False
        self._thread = None
        self._levels = [0.12] * 5
        self._smooth = [0.12] * 5
        self._peaks = [0.12] * 5
        self._peak_decay = 0.92
        self._smooth_factor = 0.35
        self._sample_rate = 44100
        self._chunk = 1024

    def start(self) -> bool:
        """启动音频捕获，成功返回 True"""
        try:
            import soundcard as sc

            # 获取默认输出设备的环回麦克风
            default_speaker = sc.default_speaker()
            self._mic = sc.get_microphone(
                default_speaker.id, include_loopback=True
            )

            if self._mic is None or not self._mic.isloopback:
                return False

            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            time.sleep(0.2)
            return self._enabled
        except Exception:
            return False

    def _run(self):
        """后台线程：环回录音 → FFT"""
        try:
            recorder = self._mic.recorder(
                samplerate=self._sample_rate,
                channels=2,
                blocksize=self._chunk,
            )

            with recorder:
                self._enabled = True

                while self._running:
                    try:
                        # 读取一帧音频数据 → shape (chunk, 2)
                        data = recorder.record(numframes=self._chunk)
                        if data is not None and len(data) >= 64:
                            self._process(data)
                    except Exception:
                        time.sleep(0.01)
        except Exception:
            pass
        finally:
            self._enabled = False

    def _process(self, stereo_data):
        """处理音频帧：双声道混合 → FFT → 分频段 → 平滑"""
        try:
            # 双声道 → 单声道
            mono = np.mean(stereo_data, axis=1)

            # FFT
            fft = np.abs(np.fft.rfft(mono))
            freqs = np.fft.rfftfreq(len(mono), 1 / self._sample_rate)

            # 分 5 频段
            raw = []
            for low, high in self.BANDS:
                mask = (freqs >= low) & (freqs <= high)
                if np.any(mask):
                    raw.append(float(np.mean(fft[mask])))
                else:
                    raw.append(0.0)

            # 归一化
            max_val = max(raw) + 0.001
            raw_norm = [min(1.0, v / max_val * 2.5) for v in raw]

            # 指数平滑 + 峰值衰减
            with self._lock:
                sf = self._smooth_factor
                for i in range(5):
                    self._smooth[i] = sf * raw_norm[i] + (1 - sf) * self._smooth[i]
                    if self._smooth[i] > self._peaks[i]:
                        self._peaks[i] = self._smooth[i]
                    else:
                        self._peaks[i] *= self._peak_decay
                    self._levels[i] = self._smooth[i]
        except Exception:
            pass

    def get_levels(self):
        """获取当前频谱数据 (5 floats, 0~1)，未启用时返回 None"""
        with self._lock:
            return list(self._levels) if self._enabled else None

    def stop(self):
        """停止音频捕获"""
        self._running = False
        self._enabled = False
