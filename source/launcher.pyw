# minemusic — 桌面悬浮音乐控制气泡
# .pyw 扩展名告诉 Windows 使用 pythonw.exe（无控制台窗口）

import subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from main import main
    main()
