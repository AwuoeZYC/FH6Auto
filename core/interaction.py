import time
import core.input_driver as hw_driver

class InteractionEngine:
    """
    底层硬件交互引擎 (The Muscle)。
    所有键鼠操作必须经过此类，自带全局绝对熔断机制。
    """
    def __init__(self, ctx):
        self.ctx = ctx  # 注入全局 Controller 上下文

    def press_key(self, key: str, delay: float = 0.08):
        """单次按键 (带熔断拦截)"""
        if not self.ctx.is_running(): 
            return
        hw_driver.hw_key_down(key)
        time.sleep(delay)
        hw_driver.hw_key_up(key)

    def key_down(self, key: str):
        """按下不放 (带熔断拦截)"""
        if not self.ctx.is_running(): 
            return
        hw_driver.hw_key_down(key)

    def key_up(self, key: str):
        """抬起按键 (抬起动作不熔断，确保任何时候都能释放按键防止卡死)"""
        hw_driver.hw_key_up(key)

    def game_click(self, pos: tuple, double: bool = False):
        """
        游戏内鼠标点击 (带熔断拦截与防抖偏移)
        """
        if not self.ctx.is_running() or not pos:
            return
            
        import pydirectinput
        
        x, y = int(pos[0]), int(pos[1])
        hw_driver.hw_mouse_move(x, y)
        time.sleep(0.2)
        
        for _ in range(2 if double else 1):
            if not self.ctx.is_running(): 
                break # 点击中途发现熔断，立即中断
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.1)
            
        # 点击完成后将鼠标移开，防止悬停(Hover)特效遮挡后续的视觉识别
        gx, gy, _, _ = self.ctx.game_region
        hw_driver.hw_mouse_move(gx + 5, gy + 5)
        time.sleep(0.2)

    def release_all(self):
        """紧急释放所有常用按键，用于 F8 停止或脱困时使用"""
        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            self.key_up(key)
        import pydirectinput
        try:
            pydirectinput.mouseUp()
        except Exception:
            pass