@echo off
chcp 65001 >nul
echo ============================================
echo   气泡应用 — 一键测试
echo ============================================
echo.
echo [1/3] 检查依赖...
python -c "import PyQt5; print('  PyQt5', PyQt5.QtCore.PYQT_VERSION_STR)" 2>nul
if errorlevel 1 (
    echo   PyQt5 未安装，请先运行: pip install -r requirements.txt
    pause
    exit /b 1
)
echo [2/3] 核心功能测试...
python test_core.py
echo.
echo [3/3] 启动气泡 GUI...
echo   桌面右下角会出现半透明气泡（音符图标）
echo   单击气泡 → 播放/暂停 QQ 音乐
echo   拖拽气泡 → 移动位置
echo   按 Ctrl+C 或关闭本窗口 → 退出
echo.
python main.py
pause
