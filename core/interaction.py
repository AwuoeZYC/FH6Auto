import time
import core.input_driver as hw_driver

# 全局停止异常类
class BotStoppedException(Exception):
    pass

class InteractionEngine:
    """
    底层硬件交互引擎 (The Muscle)。
    所有键鼠操作必须经过此类，自带全局绝对熔断机制。
    """
    def __init__(self, ctx):
        self.ctx = ctx  # 注入全局 Controller 上下文

    def check_stopped(self):
        """检查点，一旦停止直接抛出异常，击穿调用栈"""
        if not self.ctx.is_running():
            raise BotStoppedException("🚨 系统已收到 F8 停止指令！")

    def press_key(self, key: str, delay: float = 0.08):
        """单次按键 (带熔断拦截)"""
        self.check_stopped()
        hw_driver.hw_key_down(key)
        time.sleep(delay)
        hw_driver.hw_key_up(key)

    def key_down(self, key: str):
        """按下不放 (带熔断拦截)"""
        self.check_stopped()
        hw_driver.hw_key_down(key)

    def key_up(self, key: str):
        """抬起按键 (抬起动作不熔断，确保任何时候都能释放按键防止卡死)"""
        hw_driver.hw_key_up(key)

    def game_click(self, pos: tuple, double: bool = False):
        """
        游戏内鼠标点击 (带熔断拦截与防抖偏移)
        """
        self.check_stopped()
        if not pos: return
            
        import pydirectinput
        
        x, y = int(pos[0]), int(pos[1])
        hw_driver.hw_mouse_move(x, y)
        time.sleep(0.2)
        
        for _ in range(2 if double else 1):
            self.check_stopped()
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.1)
            
        # 点击完成后将鼠标移开，防止悬停(Hover)特效遮挡后续的视觉识别
        gx, gy, _, _ = self.ctx.game_region
        hw_driver.hw_mouse_move(gx + 5, gy + 5)
        time.sleep(0.2)
    
    def smooth_mouse_move(self, start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 12, duration: float = 0.15):
        """
        利用线性插值(Lerp)模拟人类鼠标的平滑滑动轨迹。
        :param steps: 轨迹拆分的步数（帧数）
        :param duration: 整个滑动过程的总耗时（秒）
        """
        self.check_stopped()
        delay_per_step = duration / steps
        for i in range(1, steps + 1):
            self.check_stopped() # 保持绝对熔断安全
            
            # 计算当前步的进度百分比 (0.0 到 1.0)
            t = i / steps
            
            # 线性插值计算当前的 X 和 Y 坐标
            current_x = int(start_x + (end_x - start_x) * t)
            current_y = int(start_y + (end_y - start_y) * t)
            
            hw_driver.hw_mouse_move(current_x, current_y)
            time.sleep(delay_per_step)

    def anti_afk_wake(self):
        """
        标准防挂机唤醒：在游戏窗口左上角进行一次“去而复返”的平滑滑动。
        总耗时约 0.3 秒，既能保证被游戏引擎识别，又不会导致状态机严重阻塞。
        """
        self.check_stopped()
        
        gx, gy, _, _ = self.ctx.game_region
        
        # 设定滑动起点与终点（避开正中间的UI，在左上角安全区域滑动）
        start_x, start_y = gx + 20, gy + 20
        end_x, end_y = gx + 150, gy + 150
        
        # 滑过去
        self.smooth_mouse_move(start_x, start_y, end_x, end_y, steps=10, duration=0.1)
        # 稍微停顿一下
        time.sleep(0.05)
        # 再滑回来
        self.smooth_mouse_move(end_x, end_y, start_x, start_y, steps=10, duration=0.1)

    def release_all(self):
        """紧急释放所有常用按键，用于 F8 停止或脱困时使用"""
        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            self.key_up(key)
        import pydirectinput
        try:
            pydirectinput.mouseUp()
        except Exception:
            pass