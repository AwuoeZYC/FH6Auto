import ctypes
import subprocess
import time
import win32gui

class GameMonitor:
    """
    游戏窗口监控与进程管理类。
    负责游戏进程的生命周期探测、窗口坐标获取以及系统级输入法的控制。
    """
    TARGET_EXE = "forzahorizon6.exe"

    @staticmethod
    def set_english_input(logger=None):
        """
        在硬件级模拟按键前，强制当前活动窗口进入纯英文输入状态，
        防止触发输入法候选框导致游戏失去焦点。
        """
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd: 
                return
            
            # 策略 1：尝试向目标窗口发送消息，切换至美式键盘布局 (0x0409)
            hkl = ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 1)
            ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, hkl) 
            
            # 策略 2：调用底层 IME API 强制关闭当前输入法的中文开启状态
            WM_IME_CONTROL = 0x0283
            IMC_SETOPENSTATUS = 0x0006
            ctypes.windll.user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)
            
            if logger: 
                logger("已自动切换英文键盘/关闭中文输入法状态。")
        except Exception as e:
            if logger: 
                logger(f"自动防中文输入设置失败: {e}")

    @classmethod
    def check_and_focus_game(cls, logger=None) -> tuple:
        """
        查找游戏进程，将其强制置于前台，并返回游戏窗口的客户端坐标信息。
        返回: (是否成功: bool, 窗口区域元组: (x, y, w, h) 或 None)
        """
        if logger: 
            logger(f"检查游戏进程 ({cls.TARGET_EXE})...")
            
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = f'tasklist /FI "IMAGENAME eq {cls.TARGET_EXE}" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)

            if cls.TARGET_EXE.lower() not in output.lower():
                if logger: 
                    logger(f"未发现 {cls.TARGET_EXE} 进程！(请确保游戏已运行)")
                return False, None

            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and cls.TARGET_EXE.lower() in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break

            if not target_pid:
                if logger: 
                    logger("找到进程但无法解析PID！")
                return False, None

            hwnds = []
            def foreach_window(hwnd, lParam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        window_pid = ctypes.c_ulong()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == target_pid:
                            hwnds.append(hwnd)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(foreach_window), 0)

            if hwnds:
                hwnd = hwnds[0]
                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                else:
                    ctypes.windll.user32.ShowWindow(hwnd, 5)
                    
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                
                cls.set_english_input(logger)
                
                # 获取不包含窗口边框的实际客户端渲染区域
                client_rect = win32gui.GetClientRect(hwnd)
                pt = win32gui.ClientToScreen(hwnd, (0, 0))
                x, y = pt[0], pt[1]
                w, h = client_rect[2], client_rect[3]
                
                time.sleep(1.0)
                return True, (x, y, w, h)

        except Exception as e:
            if logger: 
                logger(f"检查进程异常: {e}")
            return False, None

        return False, None