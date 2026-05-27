import threading
import time
from typing import Optional, Callable
from core.vision import VisionEngine
from core.navigator import SceneNavigator
from core.router import UIRouter    # <--- 新增：引入路由引擎
from utils.game_monitor import GameMonitor
import os

class BotController:
    def __init__(self, search_dirs: list, base_res: tuple):
        self._is_running = False
        self.current_thread: Optional[threading.Thread] = None
        self.global_loop_current = 0
        self.global_loop_total = 10
        
        self.ui_log_callback: Optional[Callable[[str], None]] = None
        self.ui_progress_callback: Optional[Callable[[str, int, int], None]] = None
        self.ui_loop_callback: Optional[Callable[[int, int], None]] = None
        self.ui_stop_callback: Optional[Callable[[], None]] = None

        self.search_dirs = search_dirs
        self.base_res = base_res  
        self.game_region = (0, 0, 1920, 1080) 
        self.config = {}

        self.vision = VisionEngine(
            logger_callback=self.log,
            check_running_callback=self.is_running
        )
        
        # --- 核心组件装配 ---
        self.navigator = SceneNavigator(self)  # GPS 定位雷达
        self.router = UIRouter(self)           # 自动驾驶司机

    def prepare_vision_cache(self):
        """预热模板缓存，并自动补全目录结构，严格去重内部与外部重复资源"""
        self.log("开始动态预热视觉引擎...")
        
        # 1. 自动补全外部文件夹结构 (解决打包时不拷贝空文件夹的问题)
        external_img_dir = os.path.join(self.search_dirs[0]) # APP_DIR/images
        for ratio_folder in ["4_3", "16_9", "16_10", "21_9"]:
            folder_path = os.path.join(external_img_dir, ratio_folder)
            try:
                os.makedirs(folder_path, exist_ok=True)
            except Exception:
                pass

        # 2. 遍历加载并严格去重
        # 使用 (相对文件夹, 文件名) 作为唯一键，只要外部文件夹加载了这张图，内部的同名图就直接抛弃
        loaded_keys = set() 
        count = 0

        for base_dir in self.search_dirs:
            if not base_dir or not os.path.exists(base_dir):
                continue
                
            for root, _, files in os.walk(base_dir):
                for file in files:
                    if file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                        abs_path = os.path.join(root, file)
                        
                        # 提取相对于 base_dir 的子路径 (如 '4_3/btn.png') 作为去重标识
                        rel_path = os.path.relpath(abs_path, base_dir).lower()
                        
                        if rel_path not in loaded_keys:
                            self.vision.load_template(abs_path)
                            loaded_keys.add(rel_path)
                            count += 1
                            
        self.log(f"✅ 视觉预热完毕，已成功加载 {count} 张独立特征快照！")

    # ==========================================
    # --- 任务层门面接口 (Facade API) 同步更新 ---
    # ==========================================
    def find_image(self, template_name: str, threshold: float = 0.90, fast_mode: bool = True) -> tuple:
        base_w, base_h = self.base_res
        folder = self.vision._get_aspect_ratio_folder(base_w, base_h)
        actual_path = self.vision._resolve_template_path(self.search_dirs, folder, template_name)
        screen_bgr = self.vision.capture_region(self.game_region)
        # 加入 base_h 的传递
        return self.vision._do_match(screen_bgr, actual_path, self.game_region, threshold, base_w, base_h, fast_mode)

    def find_any_image(self, template_names: list, threshold: float = 0.90, fast_mode: bool = True) -> tuple:
        for name in template_names:
            pos = self.find_image(name, threshold, fast_mode)
            if pos: return pos
        return None

    def check_image_in_buffer(self, screen_bgr, template_name: str, threshold: float = 0.68) -> bool:
        base_w, base_h = self.base_res
        folder = self.vision._get_aspect_ratio_folder(base_w, base_h)
        actual_path = self.vision._resolve_template_path(self.search_dirs, folder, template_name)
        # 加入 base_h 的传递
        pos = self.vision._do_match(screen_bgr, actual_path, self.game_region, threshold, base_w, base_h, fast_mode=True)
        return pos is not None

    def game_click(self, pos: tuple, double: bool = False):
        if not self._is_running or not pos:
            return
        import pydirectinput
        import core.input_driver as input_driver
        
        x, y = int(pos[0]), int(pos[1])
        input_driver.hw_mouse_move(x, y)
        time.sleep(0.2)
        
        for _ in range(2 if double else 1):
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.1)
            
        gx, gy, _, _ = self.game_region
        input_driver.hw_mouse_move(gx + 5, gy + 5)
        time.sleep(0.2)

    # ==========================================
    # --- 生命周期与 UI 同步控制 ---
    # ==========================================
    def is_running(self) -> bool:
        return self._is_running

    def register_ui_callbacks(self, log_cb, progress_cb, loop_cb, stop_cb):
        self.ui_log_callback = log_cb
        self.ui_progress_callback = progress_cb
        self.ui_loop_callback = loop_cb
        self.ui_stop_callback = stop_cb

    def log(self, message: str):
        if self.ui_log_callback:
            self.ui_log_callback(message)

    def update_running_ui(self, task_name: str, current: int, total: int):
        if self.ui_progress_callback:
            self.ui_progress_callback(task_name, current, total)

    def set_running_status(self, status: bool):
        self._is_running = status
        if not status and self.ui_stop_callback:
            self.ui_stop_callback()

    def start_pipeline(self, start_step: str, global_config: dict):
        if self._is_running: return
            
        self.config = global_config
        self.global_loop_total = int(global_config.get("global_loops", 10))
        self.global_loop_current = 1
        
        success, region = GameMonitor.check_and_focus_game(self.log)
        if not success or not region:
            self.log("❌ 无法定位游戏窗口，拒绝启动。")
            return
            
        self.game_region = region
        self.set_running_status(True)
        
        self.current_thread = threading.Thread(target=self._run_pipeline_loop, args=(start_step,), daemon=True)
        self.current_thread.start()

    def _run_pipeline_loop(self, start_step: str):
        from logic.race_task import RaceTask
        import logic.wheelspin
        import logic.sell
        from logic.buy_task import BuyCarTask

        steps = ["race", "buy", "cj", "sell"]
        try:
            curr_idx = steps.index(start_step)
        except ValueError:
            curr_idx = 0

        if self.ui_loop_callback:
            self.ui_loop_callback(self.global_loop_current, self.global_loop_total)

        while self._is_running:
            step_name = steps[curr_idx]
            step_success = False

            try:
                if step_name == "race": step_success = RaceTask(self, int(self.config.get("race_count", 99))).run()
                elif step_name == "buy": step_success = BuyCarTask(self, int(self.config.get("buy_count", 30))).run()
                elif step_name == "cj": step_success = logic.wheelspin.run_wheelspin(self, int(self.config.get("cj_count", 30)))
                elif step_name == "sell": step_success = logic.sell.run_sell(self, int(self.config.get("sc_count", 30)))
            except Exception as e:
                self.log(f"🔥 执行模块 {step_name} 时遭遇严重崩溃: {e}")

            if not self._is_running: break

            if not step_success:
                self.log("⚠️ 模块返回失败，尝试执行雷达脱困重置...")
                if self.navigator.recover_to_safe_state():
                    self.log("✅ 成功脱困，尝试重新执行当前步骤。")
                    continue
                else:
                    self.log("🚨 无法通过常规手段脱困，流水线终止。")
                    break

            next_idx = curr_idx + 1
            if curr_idx == 0: next_idx = int(self.config.get("next_1", 2)) - 1 if self.config.get("chk_1") else -1
            elif curr_idx == 1: next_idx = int(self.config.get("next_2", 3)) - 1 if self.config.get("chk_2") else -1
            elif curr_idx == 2: next_idx = int(self.config.get("next_3", 4)) - 1 if self.config.get("chk_3") else -1
            elif curr_idx == 3: next_idx = int(self.config.get("next_4", 1)) - 1 if self.config.get("chk_4") else -1

            if next_idx < 0:
                self.log("设置了后续不继续执行，任务正常结束。")
                break

            if next_idx <= curr_idx:
                self.global_loop_current += 1
                if self.global_loop_current > self.global_loop_total:
                    self.log("🎉 已达到设定的总大循环次数，全自动化流程圆满结束。")
                    break
                if self.ui_loop_callback:
                    self.ui_loop_callback(self.global_loop_current, self.global_loop_total)
                self.log(f"🔄 开启新一轮大循环 ({self.global_loop_current}/{self.global_loop_total})")

            curr_idx = next_idx

        self.stop_all()

    def stop_all(self):
        if not self._is_running: return
        self.set_running_status(False)
        
        import core.input_driver as input_driver
        import pydirectinput
        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            input_driver.hw_key_up(key)
        try:
            pydirectinput.mouseUp()
        except Exception:
            pass
        self.log("🛑 核心控制器已下发强制停止指令，物理键位全部复位。")