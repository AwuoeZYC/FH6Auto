import threading
import time
from typing import Optional, Callable
from core.vision import VisionEngine
from core.navigator import SceneNavigator
from core.router import UIRouter    # <--- 新增：引入路由引擎
from utils.game_monitor import GameMonitor
import os
import core.pipeline_manager
from core.interaction import InteractionEngine

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
        self.interaction = InteractionEngine(self) # 硬件交互肌肉
        self.navigator = SceneNavigator(self)      # GPS 定位雷达
        self.router = UIRouter(self)               # 自动驾驶司机
        
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
    def press_key(self, key: str):
        """统一硬件按键下发，包含全局熔断拦截"""
        if not self._is_running:
            return
        import core.input_driver as input_driver
        input_driver.hw_press(key)

    def find_image(self, template_name: str, region: tuple = None, threshold: float = 0.90, fast_mode: bool = True) -> tuple:
        """视觉搜索的 Context 包装器。自动注入全局分辨率和路径。"""
        base_w, base_h = self.base_res
        folder = self.vision._get_aspect_ratio_folder(base_w, base_h)
        actual_path = self.vision._resolve_template_path(self.search_dirs, folder, template_name)
        
        search_region = region if region else self.game_region
        screen_bgr = self.vision.capture_region(search_region)
        
        # 【核心修复】：注入实际的全局游戏窗口尺寸
        gw, gh = self.game_region[2], self.game_region[3]
        
        return self.vision._do_match(
            screen_bgr, actual_path, search_region, threshold, 
            base_w, base_h, fast_mode, full_screen_size=(gw, gh)
        )


    def find_any_image(self, template_names: list, region: tuple = None, threshold: float = 0.90, fast_mode: bool = True) -> tuple:
        """
        多图轮询寻找。将 region 参数向下透传给单图寻找逻辑。
        """
        for name in template_names:
            # 【核心修复】：把接收到的 region 传递给 find_image
            pos = self.find_image(name, region=region, threshold=threshold, fast_mode=fast_mode)
            if pos: 
                return pos
        return None

    def find_all_images(self, template_name: str, region: tuple = None, threshold: float = 0.90, fast_mode: bool = True) -> list:
        """【新增】：多目标检索接口，返回所有匹配项的坐标列表"""
        base_w, base_h = self.base_res
        folder = self.vision._get_aspect_ratio_folder(base_w, base_h)
        actual_path = self.vision._resolve_template_path(self.search_dirs, folder, template_name)
        
        search_region = region if region else self.game_region
        screen_bgr = self.vision.capture_region(search_region)
        gw, gh = self.game_region[2], self.game_region[3]
        
        return self.vision._do_match_all(
            screen_bgr, actual_path, search_region, threshold, 
            base_w, base_h, fast_mode, full_screen_size=(gw, gh)
        )

    def check_image_in_buffer(self, screen_bgr, template_name: str, threshold: float = 0.8) -> bool:
        base_w, base_h = self.base_res
        folder = self.vision._get_aspect_ratio_folder(base_w, base_h)
        actual_path = self.vision._resolve_template_path(self.search_dirs, folder, template_name)
        gw, gh = self.game_region[2], self.game_region[3]
        
        pos = self.vision._do_match(
            screen_bgr, actual_path, self.game_region, threshold, 
            base_w, base_h, fast_mode=True, full_screen_size=(gw, gh)
        )
        return pos is not None

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
        from core.pipeline_manager import PipelineManager
        from logic.race_task import RaceTask
        from logic.buy_task import BuyCarTask
        from logic.car_mastery_task import CarMasteryTask
        from logic.remove_task import RemoveTask
        
        pipeline = PipelineManager(self)
        
        # 将所有的控制参数完整地绑定到对应的任务槽位上
        pipeline.register_task("race", RaceTask, "race_count", "chk_1", "next_1")
        pipeline.register_task("buy", BuyCarTask, "buy_count", "chk_2", "next_2")
        pipeline.register_task("mastery", CarMasteryTask, "mastery_count", "chk_3", "next_3")
        pipeline.register_task("remove", RemoveTask, "remove_count", "chk_4", "next_4")

        pipeline.run_pipeline(start_step)
        
        self.stop_all()

    def stop_all(self):
        if not self._is_running: return
        self.set_running_status(False)

        # 呼叫肌肉引擎释放所有按键
        if hasattr(self, 'interaction'):
            self.interaction.release_all()

        self.log("🛑 核心控制器已下发强制停止指令，物理键位全部复位。")