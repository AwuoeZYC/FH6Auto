import sys
import ctypes
from gui.main_window import FH_UltimateBot

# 【极其关键】：必须在任何 UI 库导入之前设置 DPI 感知，保证高分辨率屏幕不模糊
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Win 8.1+
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Win Vista+
    except Exception:
        pass

if __name__ == "__main__":
    print("正在启动 FH6Auto 自动化核心...")
    try:
        app = FH_UltimateBot()
        app.mainloop()
    except KeyboardInterrupt:
        print("程序已手动退出。")
    except Exception as e:
        print(f"程序遭遇严重崩溃: {e}")
        input("按回车键退出...")