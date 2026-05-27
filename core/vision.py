import os
import time
import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

class VisionEngine:
    """
    自适应视觉识别引擎。
    纯图像处理模块，不依赖任何上层业务逻辑与 UI 配置。
    """
    def __init__(self, logger_callback=None, check_running_callback=None):
        self.logger = logger_callback
        self.is_running = check_running_callback if check_running_callback else lambda: True
        
        self.template_cache = {}
        self.scaled_template_cache = {}
        self.path_cache = {}  # 新增：绝对路径 IO 缓存，砍掉硬盘寻道时间
        
        self.log("VisionEngine initialized.")

    def log(self, msg: str): 
        if self.logger:
            self.logger(msg)

    def _get_aspect_ratio_folder(self, base_w: int, base_h: int) -> str:
        """根据基准宽高计算对应的比例文件夹名"""
        if base_h <= 0:
            return "16_9"
            
        ratio = base_w / float(base_h)
        if 1.20 <= ratio < 1.45: return "4_3"     
        elif 1.45 <= ratio < 1.65: return "16_10" 
        elif 1.65 <= ratio < 2.00: return "16_9"  
        elif 2.00 <= ratio <= 2.50: return "21_9" 
        return "16_9"

    def _resolve_template_path(self, search_dirs: list, folder: str, filename: str) -> str:
        """在提供的目录列表中按优先级寻找模板文件，使用内存字典避免高频 IO"""
        cache_key = (folder, filename)
        if cache_key in self.path_cache:
            return self.path_cache[cache_key]

        for base_dir in search_dirs:
            if not base_dir or not os.path.isdir(base_dir):
                continue
                
            ratio_path = os.path.join(base_dir, folder, filename)
            if os.path.exists(ratio_path):
                self.path_cache[cache_key] = ratio_path
                return ratio_path
                
            fallback_path = os.path.join(base_dir, filename)
            if os.path.exists(fallback_path):
                self.path_cache[cache_key] = fallback_path
                return fallback_path
                
        self.path_cache[cache_key] = filename
        return filename

    def load_template(self, actual_path: str) -> np.ndarray:
        """加载并缓存原始模板图像"""
        if actual_path in self.template_cache:
            return self.template_cache[actual_path]

        if not os.path.exists(actual_path):
            self.log(f"Template not found: {actual_path}")
            return None

        tpl = cv2.imread(actual_path, cv2.IMREAD_COLOR)
        if tpl is not None:
            self.template_cache[actual_path] = tpl
        return tpl

    # def get_scaled_template(self, template_path: str, scale_x: float, scale_y: float) -> np.ndarray:
    #     """支持 X 轴与 Y 轴独立非等比缩放的模板生成"""
    #     if scale_x <= 0 or scale_y <= 0:
    #         return None
            
    #     # 原生 1:1 拦截，避免 OpenCV 重新插值导致图像变糊
    #     if abs(scale_x - 1.0) < 0.01 and abs(scale_y - 1.0) < 0.01:
    #         return self.load_template(template_path)

    #     mem_key = (template_path, round(scale_x, 3), round(scale_y, 3))
    #     if mem_key in self.scaled_template_cache:
    #         return self.scaled_template_cache[mem_key]

    #     template_orig = self.load_template(template_path)
    #     if template_orig is None: 
    #         return None

    #     tpl = cv2.resize(template_orig, None, fx=scale_x, fy=scale_y, interpolation=cv2.INTER_AREA)
    #     self.scaled_template_cache[mem_key] = tpl
    #     return tpl

    def capture_region(self, region: tuple = None) -> np.ndarray:
        """捕获屏幕区域，返回 BGR 格式的 numpy 数组"""
        try:
            if region:
                x, y, w, h = map(int, region)
                bbox = (x, y, x + w, y + h)
                screen = ImageGrab.grab(bbox=bbox, all_screens=True)
            else:
                screen = ImageGrab.grab(all_screens=True)
        except Exception as e:
            self.log(f"ImageGrab failed, fallback to pyautogui: {e}")
            screen = pyautogui.screenshot(region=region)
            
        return cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)

    def _do_match(self, screen_bgr: np.ndarray, template_abs_path: str, region: tuple = None, 
                  threshold: float = 0.75, expected_base_w: int = 1024, expected_base_h: int = 768, fast_mode: bool = True) -> tuple:
        """
        核心匹配逻辑 (逆向降维版)。
        通过将截屏逆向缩放回基准空间进行比对，运算时间从十几秒压缩至毫秒级。
        同时兼容: 原生窗口、非等比强行拉伸(满屏)、等比拉伸(留黑边)。
        """
        if screen_bgr is None or screen_bgr.size == 0:
            return None
            
        orig_tpl = self.load_template(template_abs_path)
        if orig_tpl is None:
            return None

        current_w = screen_bgr.shape[1]
        current_h = screen_bgr.shape[0]
        
        # 计算当前物理屏幕相对基准素材的放大倍率
        scale_x = current_w / float(expected_base_w)
        scale_y = current_h / float(expected_base_h)

        # 智能推演三种可能存在的显卡呈现状态
        scale_native = (1.0, 1.0)                     # UI 输入分辨率与实际吻合
        scale_stretch = (scale_x, scale_y)            # 显卡强行拉伸铺满全屏
        scale_pillarbox = (scale_y, scale_y)          # 显卡保持原比例拉伸，以高度为准左右留黑边

        if fast_mode:
            scales_to_try = list(dict.fromkeys([scale_native, scale_stretch, scale_pillarbox]))
        else:
            scales_to_try = list(dict.fromkeys([
                scale_native, scale_stretch, scale_pillarbox,
                (scale_x * 0.98, scale_y * 0.98),
                (scale_x * 1.02, scale_y * 1.02)
            ]))

        th, tw = orig_tpl.shape[:2]

        for sx, sy in scales_to_try:
            # 【性能核心】：逆向缩放屏幕！
            # 将 2K/4K 的截图缩小回 1024x768 的基准空间进行高速比对
            if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
                work_screen = screen_bgr
            else:
                work_screen = cv2.resize(screen_bgr, None, fx=1.0/sx, fy=1.0/sy, interpolation=cv2.INTER_AREA)

            # 越界保护：如果缩小后的屏幕依然比模板小，说明该物理拉伸比例不符合当前现实，直接跳过
            if th > work_screen.shape[0] or tw > work_screen.shape[1]: 
                continue

            res = cv2.matchTemplate(work_screen, orig_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                # 在 1024x768 空间下找到了坐标，现在将其乘以放大倍率，还原到物理显示器上的真实点击位置
                match_center_x = max_loc[0] + tw // 2
                match_center_y = max_loc[1] + th // 2
                
                global_x = int(match_center_x * sx) + (region[0] if region else 0)
                global_y = int(match_center_y * sy) + (region[1] if region else 0)
                return (global_x, global_y)
                
        return None

    # ==========================================
    # --- 对外暴露 API ---
    # ==========================================
    def find_image(self, template_name: str, search_dirs: list, base_res: tuple, 
                   region: tuple = None, threshold: float = 0.90) -> tuple:
        """
        单次寻找图像
        base_res: (width, height) 制作模板时的基准分辨率
        search_dirs: 优先搜索的目录列表 (如 [APP_DIR/images, INTERNAL_DIR/images])
        """
        if not self.is_running(): 
            return None
            
        base_w, base_h = base_res
        folder = self._get_aspect_ratio_folder(base_w, base_h)
        actual_path = self._resolve_template_path(search_dirs, folder, template_name)
        
        screen_bgr = self.capture_region(region)
        return self._do_match(screen_bgr, actual_path, region, threshold, expected_base_w=base_w, fast_mode=True)

    def wait_for_any_image(self, image_names: list, search_dirs: list, base_res: tuple, 
                           region: tuple = None, threshold: float = 0.90, 
                           timeout: float = 30.0, interval: float = 0.2) -> tuple:
        """轮询等待多个图像之一出现"""
        start_time = time.monotonic()
        
        base_w, base_h = base_res
        folder = self._get_aspect_ratio_folder(base_w, base_h)
        actual_paths = [self._resolve_template_path(search_dirs, folder, name) for name in image_names]

        while self.is_running() and (time.monotonic() - start_time) < timeout:
            screen_bgr = self.capture_region(region)
            for path in actual_paths:
                pos = self._do_match(screen_bgr, path, region, threshold, expected_base_w=base_w, fast_mode=True)
                if pos: 
                    return pos
            time.sleep(interval)
            
        return None