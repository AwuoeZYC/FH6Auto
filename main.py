import sys
import ctypes

def setup_dpi_awareness():
    """设置进程 DPI 感知，必须在任何 GUI 库加载前调用"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Win 8.1+
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # Win Vista+
        except Exception:
            pass

if __name__ == "__main__":
    setup_dpi_awareness()
    
    # 必须在 DPI 设置之后导入 UI 相关模块
    from gui.main_window import FH_UltimateBot

    print("启动 FH6Auto 自动化核心...")
    try:
        app = FH_UltimateBot()
        app.mainloop()
    except KeyboardInterrupt:
        print("程序已手动退出。")
    except Exception as e:
        print(f"程序遭遇严重崩溃: {e}")
        sys.exit(1)