import os
import time
import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab
import mss  # 极速无泄漏截图库

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
        self.path_cache = {}  # 绝对路径 IO 缓存，砍掉硬盘寻道时间

        # 初始化 MSS 单例对象，复用底层 C 内存分配，杜绝 GDI 句柄泄漏
        self.sct = mss.mss()
        
        self.log("VisionEngine initialized with MSS.")

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

    def capture_region(self, region: tuple = None) -> np.ndarray:
        """【重构】使用 mss 替代 ImageGrab 捕获屏幕区域，返回 BGR 格式"""
        try:
            if region:
                x, y, w, h = map(int, region)
                # mss 的区域定义格式
                monitor = {"top": y, "left": x, "width": w, "height": h}
            else:
                # 0 代表截取全屏（包含多屏拼接区域）
                monitor = self.sct.monitors[0]
                
            # grab 返回的是专门的 mss 对象，极速转换
            sct_img = self.sct.grab(monitor)
            
            # 转换为 numpy 数组。mss 默认返回 BGRA 格式，通过切片 [:, :, :3] 直接丢弃透明通道提取 BGR
            # 这比 cvtColor 快得多，且不会产生多余的内存拷贝
            screen_bgr = np.array(sct_img)[:, :, :3]
        
            # ==========================================
            # 👁️ 【终极排错快照】：每隔 10 秒保存一张引擎真实的视野
            # ==========================================
            if getattr(self, "debug_mode", False):
                import time
                import cv2
                if not hasattr(self, "last_debug_save") or time.time() - getattr(self, "last_debug_save", 0) > 10:
                    try:
                        # 初始化图片轮播计数器
                        if not hasattr(self, "debug_img_idx"):
                            self.debug_img_idx = 1
                            
                        # 动态生成文件名，例如 debug_screen_snapshot_1.png
                        filename = f"debug_screen_snapshot_{self.debug_img_idx}.png"
                        
                        # 保存截图
                        cv2.imwrite(filename, screen_bgr)
                        self.last_debug_save = time.time()
                        self.log(f"📸 [Debug] 已保存引擎快照: {filename}")
                        
                        # 计数器递增，如果超过5，就回到1（轮播覆盖，防止把别人硬盘塞满）
                        self.debug_img_idx += 1
                        if self.debug_img_idx > 6:
                            self.debug_img_idx = 1
                            
                    except Exception as save_e:
                        pass
            # ==========================================

            return screen_bgr
        
        except Exception as e:
            self.log(f"🚨 MSS 截图引擎异常: {e}")
            return np.array([]) # 返回空数组作为安全兜底

    def _do_match(self, screen_bgr: np.ndarray, template_abs_path: str, region: tuple = None, 
                  threshold: float = 0.75, expected_base_w: int = 1024, expected_base_h: int = 768, 
                  fast_mode: bool = True, full_screen_size: tuple = None) -> tuple:
        if screen_bgr is None or screen_bgr.size == 0:
            return None
            
        orig_tpl = self.load_template(template_abs_path)
        if orig_tpl is None:
            return None

        # 【核心修复】：如果是局部 ROI 搜索，放大倍率必须依然参照全局游戏窗口的大小！
        if full_screen_size:
            current_w, current_h = full_screen_size
        else:
            current_w, current_h = screen_bgr.shape[1], screen_bgr.shape[0]
        
        scale_x = current_w / float(expected_base_w)
        scale_y = current_h / float(expected_base_h)

        scale_native = (1.0, 1.0)
        scale_stretch = (scale_x, scale_y)
        scale_pillarbox = (scale_y, scale_y)

        if fast_mode:
            scales_to_try = list(dict.fromkeys([scale_native, scale_stretch, scale_pillarbox]))
        else:
            scales_to_try = list(dict.fromkeys([
                scale_native, scale_stretch, scale_pillarbox,
                (scale_x * 0.98, scale_y * 0.98), (scale_x * 1.02, scale_y * 1.02)
            ]))

        th, tw = orig_tpl.shape[:2]

        for sx, sy in scales_to_try:
            if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
                work_screen = screen_bgr
            else:
                work_screen = cv2.resize(screen_bgr, None, fx=1.0/sx, fy=1.0/sy, interpolation=cv2.INTER_AREA)

            if th > work_screen.shape[0] or tw > work_screen.shape[1]: 
                continue

            res = cv2.matchTemplate(work_screen, orig_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                match_center_x = max_loc[0] + tw // 2
                match_center_y = max_loc[1] + th // 2
                global_x = int(match_center_x * sx) + (region[0] if region else 0)
                global_y = int(match_center_y * sy) + (region[1] if region else 0)
                return (global_x, global_y)
                
        return None

    def _do_match_all(self, screen_bgr: np.ndarray, template_abs_path: str, region: tuple = None, 
                      threshold: float = 0.75, expected_base_w: int = 1024, expected_base_h: int = 768, 
                      fast_mode: bool = True, full_screen_size: tuple = None) -> list:
        """【新增】：返回所有符合阈值的坐标列表，包含距离去重 (NMS)"""
        if screen_bgr is None or screen_bgr.size == 0:
            return []

        orig_tpl = self.load_template(template_abs_path)
        if orig_tpl is None:
            return []

        if full_screen_size:
            current_w, current_h = full_screen_size
        else:
            current_w, current_h = screen_bgr.shape[1], screen_bgr.shape[0]

        scale_x = current_w / float(expected_base_w)
        scale_y = current_h / float(expected_base_h)

        scale_native = (1.0, 1.0)
        scale_stretch = (scale_x, scale_y)
        scale_pillarbox = (scale_y, scale_y)
        scales_to_try = list(dict.fromkeys([scale_native, scale_stretch, scale_pillarbox]))

        th, tw = orig_tpl.shape[:2]
        all_matches = []

        for sx, sy in scales_to_try:
            if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
                work_screen = screen_bgr
            else:
                work_screen = cv2.resize(screen_bgr, None, fx=1.0/sx, fy=1.0/sy, interpolation=cv2.INTER_AREA)

            if th > work_screen.shape[0] or tw > work_screen.shape[1]: 
                continue

            res = cv2.matchTemplate(work_screen, orig_tpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            
            for pt in zip(*loc[::-1]): 
                match_center_x = pt[0] + tw // 2
                match_center_y = pt[1] + th // 2
                global_x = int(match_center_x * sx) + (region[0] if region else 0)
                global_y = int(match_center_y * sy) + (region[1] if region else 0)
                all_matches.append((global_x, global_y))

            if all_matches:
                break # 只要在某个比例下找到了符合条件的目标，就不再尝试其他比例以防重复

        # 欧式距离去重，防止同一个图标被返回多个密集坐标
        # 动态获取当前模板在屏幕上实际宽度的 40% 作为去重半径。
        # 既能完美消除同一位置的重叠噪点，又绝对不会吞掉相连的相同数字！
        nms_radius = max(4, int(tw * sx * 0.4)) if all_matches else 10
        
        deduped = []
        for pt in all_matches:
            if not any(np.hypot(pt[0]-d[0], pt[1]-d[1]) < nms_radius for d in deduped):
                deduped.append(pt)

        return deduped

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