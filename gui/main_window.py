import os
import sys
import json
import time
import threading
import webbrowser
import requests
import customtkinter as ctk
from PIL import Image
from core.profile_manager import ProfileManager
from gui.windows.updater_window import UpdaterWindow
from gui.panels.smart_planner import SmartPlannerPanel
from gui.panels.task_config_panel import TaskConfigPanel
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 必须显式关闭组件自带的 DPI 缩放，由主入口接管绝对坐标控制
ctk.deactivate_automatic_dpi_awareness()
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)

from config import (
    APP_DIR, INTERNAL_DIR, CONFIG_FILE, CURRENT_VERSION,
    auto_extract_images, get_asset_path, parse_version
)
from core.bot_controller import BotController

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class FH_UltimateBot(ctk.CTk):
    """
    自动化脚本的主 GUI 视图窗口。
    负责用户配置交互、矩阵技能树渲染、任务状态显示，不处理任何游戏内控制逻辑。
    """
    def __init__(self):
        super().__init__()
        
        # 窗口基础属性配置
        self.title(f"FH6Auto by AwuoeZYC v{CURRENT_VERSION}")
        self.geometry("1800x880")
        self.attributes("-topmost", False)
        self.attributes("-alpha", 0.98)
        self.resizable(False, False)

        try:
            icon_path = get_asset_path("icon.ico")
            if icon_path:
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # 核心业务控制器初始化与注入
        # 搜寻路径列表：外部图片目录优先，内部资源目录降级
        search_dirs = [os.path.join(APP_DIR, "images"), os.path.join(INTERNAL_DIR, "images")]
        
        # 初始默认的蓝图素材基准分辨率为 1024x768
        self.controller = BotController(search_dirs=search_dirs, base_res=(1024, 768))
        
        self.support_win = None
        self.start_time = 0.0

        ProfileManager().load_profiles()

        # 初始化配置管理器并挂载引用
        from core.config_manager import ConfigManager
        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.config  # 保持兼容性，让旧的 UI 组件还能通过 self.config 访问


        # UI 组件装配与核心回调双向绑定
        self.setup_ui()
        self.controller.register_ui_callbacks(
            log_cb=self.log,
            progress_cb=self.update_running_ui,
            loop_cb=self.update_loop_ui,
            stop_cb=self.on_controller_stopped
        )
        
        self.center_window()

        # 异步预热视觉特征引擎，避免阻塞主线程渲染
        def background_init():
            auto_extract_images()
            self.controller.prepare_vision_cache()
        threading.Thread(target=background_init, daemon=True).start()


        # 输出引导日志
        self.log("免责声明：本脚本仅供 Python 自动化技术交流与学习使用。请勿用于商业盈利或破坏游戏平衡。")
        self.log("默认刷图车辆：【斯巴鲁Impreza 22B-STi Version】【调校S2 900】【保持默认配置】【收藏车辆】")
        self.log("启动前请确保：系统键盘设置为【英文键盘】，游戏设置为【自动转向】【自动挡】，语言为【简体中文】")

        from pynput import keyboard
        def hotkey_thread():
            def on_press(k):
                if k == keyboard.Key.f8:
                    self.log("⚠️ 检测到 F8 物理按键，下发强制停止指令！")
                    self.controller.stop_all()
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
                
        threading.Thread(target=hotkey_thread, daemon=True).start()

    def ui_call(self, func, *args, **kwargs):
        """线程安全的 GUI 操作分发包装器"""
        try:
            self.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def center_window(self):
        """将主窗口居中于当前主显示器屏幕"""
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    
    # ==========================================
    # --- 配置管理数据流 ---
    # ==========================================
    
    def save_config(self):
        try:
            self.config["global_loops"] = int(self.entry_global_loop.get())
            self.config["base_width"] = int(self.entry_base_w.get())
            self.config["base_height"] = int(self.entry_base_h.get())
        except Exception:
            pass
        self.config["auto_restart"] = self.var_auto_restart.get()
        self.config["debug_vision"] = self.var_debug_vision.get()
        self.config["restart_cmd"] = self.le_restart_cmd.get().strip()

        # 让任务面板自己保存它的参数
        if hasattr(self, 'task_panel'):
            self.task_panel.save_current_values()

        self.config_mgr.save()

    
    # ==========================================
    # --- GUI 视窗布局装配 ---
    # ==========================================
    def setup_ui(self):
        self.top_container = ctk.CTkFrame(self, fg_color="transparent")
        self.top_container.pack(fill="x", padx=18, pady=(18, 10))

        # --- 接入任务配置面板 ---
        self.task_panel = TaskConfigPanel(
            self.top_container, 
            config_mgr=self.config_mgr, 
            on_start_callback=self.ui_trigger_start
        )
        self.task_panel.pack(fill="x")

        self.profile_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        self.profile_frame.pack(fill="x", padx=18, pady=(15, 0))
        self.profile_frame.pack_propagate(False)

        ctk.CTkLabel(self.profile_frame, text="🚗 目标刷取车辆:", font=ctk.CTkFont(weight="bold", size=15), text_color="#3498DB").pack(side="left", padx=(15, 10))

        # 1. 动态提取所有可选车辆的内部 ID 和展示名
        available_vehicles = ProfileManager().get_available_vehicles()
        available_ids = [v[0] for v in available_vehicles]
        display_names = [v[1] for v in available_vehicles]
        
        # 2. 动态默认值判定
        saved_id = self.config.get("target_vehicle")
        if saved_id not in available_ids:
            saved_id = available_ids[0] if available_ids else None
            self.config["target_vehicle"] = saved_id  # 纠正并回写

        # 3. 映射为 UI 需要的中文展示名
        profile_data = ProfileManager().get_profile(saved_id)
        default_display = profile_data.get("display_name", "未知车辆") if profile_data else "无可用车辆"
        
        self.var_vehicle = ctk.StringVar(value=default_display)
        self.opt_vehicle = ctk.CTkOptionMenu(
            self.profile_frame, 
            variable=self.var_vehicle, 
            values=display_names,
            width=250,
            command=self.on_vehicle_change
        )
        self.opt_vehicle.pack(side="left", padx=(0, 20))
        
        # 守护底栏设置
        self.global_settings_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        self.global_settings_frame.pack(fill="x", padx=18, pady=(15, 0))
        self.global_settings_frame.pack_propagate(False)
        
        ctk.CTkLabel(self.global_settings_frame, text="⚙️ 循环与守护设置", font=ctk.CTkFont(weight="bold", size=15), text_color="#F1C40F").pack(side="left", padx=(15, 20))
        ctk.CTkLabel(self.global_settings_frame, text="大循环次数:").pack(side="left", padx=(10, 5))
        
        self.entry_global_loop = ctk.CTkEntry(self.global_settings_frame, width=70, height=28, justify="center")
        self.entry_global_loop.insert(0, str(self.config.get("global_loops", 10)))
        self.entry_global_loop.pack(side="left", padx=(0, 20))
        
        ctk.CTkLabel(self.global_settings_frame, text="素材分辨率:").pack(side="left", padx=(10, 2))
        self.entry_base_w = ctk.CTkEntry(self.global_settings_frame, width=55, height=28, justify="center")
        self.entry_base_w.insert(0, str(self.config.get("base_width", 1024)))
        self.entry_base_w.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(self.global_settings_frame, text="x").pack(side="left", padx=(2, 2))        
        self.entry_base_h = ctk.CTkEntry(self.global_settings_frame, width=55, height=28, justify="center")
        self.entry_base_h.insert(0, str(self.config.get("base_height", 768)))
        self.entry_base_h.pack(side="left", padx=(0, 20))
        
        self.var_auto_restart = ctk.BooleanVar(value=self.config.get("auto_restart", True))
        self.cb_auto_restart = ctk.CTkCheckBox(self.global_settings_frame, text="游戏闪退自动重启", variable=self.var_auto_restart, command=self.save_config)
        self.cb_auto_restart.pack(side="left", padx=(10, 20))

        # =================视觉调试模式开关=================
        self.var_debug_vision = ctk.BooleanVar(value=self.config.get("debug_vision", False))
        self.cb_debug_vision = ctk.CTkCheckBox(self.global_settings_frame, text="视觉调试(保存快照)", variable=self.var_debug_vision, command=self.save_config)
        self.cb_debug_vision.pack(side="left", padx=(0, 20))
        # ==========================================================
        
        ctk.CTkLabel(self.global_settings_frame, text="启动命令(CMD):").pack(side="left", padx=(10, 5))
        self.le_restart_cmd = ctk.CTkEntry(self.global_settings_frame, width=250, height=28)
        self.le_restart_cmd.insert(0, self.config.get("restart_cmd", "start steam://run/2483190"))
        self.le_restart_cmd.pack(side="left", padx=(0, 20))

        # --- 接入智能规划面板 ---
        self.planner_panel = SmartPlannerPanel(
            self, 
            config_mgr=self.config_mgr, 
            on_sync_callback=self.sync_planner_to_ui
        )
        self.planner_panel.pack(fill="x", padx=18, pady=(10, 0))


        # 紧凑型挂机控制台（大循环开启时呈现）
        self.mini_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=10)
        self.mini_log_box = ctk.CTkTextbox(self.mini_frame, state="disabled", wrap="word", font=ctk.CTkFont(size=13), fg_color="#2B2B2B")
        self.mini_log_box.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

        self.mini_info_frame = ctk.CTkFrame(self.mini_frame, fg_color="transparent")
        self.mini_info_frame.pack(side="left", fill="y", padx=5, pady=10)

        self.lbl_mini_task = ctk.CTkLabel(self.mini_info_frame, text="当前任务: 等待中", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498DB")
        self.lbl_mini_task.pack(pady=(5, 2), anchor="w")

        self.lbl_mini_prog = ctk.CTkLabel(self.mini_info_frame, text="任务进度: 0 / 0", font=ctk.CTkFont(size=13))
        self.lbl_mini_prog.pack(pady=2, anchor="w")

        self.lbl_mini_loop = ctk.CTkLabel(self.mini_info_frame, text="大循环: 0 / 0", font=ctk.CTkFont(size=13))
        self.lbl_mini_loop.pack(pady=2, anchor="w")

        self.lbl_mini_time = ctk.CTkLabel(self.mini_info_frame, text="总耗时: 00:00:00", font=ctk.CTkFont(size=13))
        self.lbl_mini_time.pack(pady=2, anchor="w")

        self.btn_mini_stop = ctk.CTkButton(self.mini_frame, text="⏸ 停止 (F8)", fg_color="#DA3633", hover_color="#B02A37", width=90, font=ctk.CTkFont(weight="bold"), command=self.controller.stop_all)
        self.btn_mini_stop.pack(side="left", fill="y", padx=5, pady=10)

        # 底部标准大日志栏
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent", height=200)
        self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))

        self.btn_stop = ctk.CTkButton(self.bottom_frame, text="⏸ 等待指令 (F8)", fg_color="#3A3A3A", hover_color="#4A4A4A", width=180, height=60, corner_radius=12, font=ctk.CTkFont(size=16, weight="bold"))
        self.btn_stop.pack(side="left", padx=6)

        self.log_box = ctk.CTkTextbox(self.bottom_frame, state="disabled", wrap="word", corner_radius=12, height=120, font=ctk.CTkFont(size=18))
        self.log_box.pack(side="left", fill="both", expand=True, padx=8)

        self.btn_update = ctk.CTkButton(self, text="🔄 检查更新 / GitHub", fg_color="#2EA043", hover_color="#238636", height=42, corner_radius=12, font=ctk.CTkFont(weight="bold", size=15), command=lambda: UpdaterWindow(self))
        self.btn_update.pack(fill="x", padx=18, pady=(6, 12))

    # ==========================================
    # --- 控制层回调槽函数实现 ---
    # ==========================================
    def log(self, message: str):
        """线程安全的双日志框行同步写入器 (带防泄漏截断)"""
        curr_time = time.strftime("%H:%M:%S")
        full_msg = f"[{curr_time}] {message}"

        def do_write():
            # 定义最大允许行数，防止 Tkinter 渲染卡死内存溢出
            MAX_LINES = 500

            # 写入主日志框
            self.log_box.configure(state="normal")
            self.log_box.insert("end", full_msg + "\n")
            
            # 获取当前行数，超过则从头部删掉最旧的 100 行
            if int(self.log_box.index('end-1c').split('.')[0]) > MAX_LINES:
                self.log_box.delete("1.0", "100.0")
                
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
            
            # 写入迷你挂机日志框
            self.mini_log_box.configure(state="normal")
            self.mini_log_box.insert("end", full_msg + "\n")
            
            if int(self.mini_log_box.index('end-1c').split('.')[0]) > MAX_LINES:
                self.mini_log_box.delete("1.0", "100.0")
                
            self.mini_log_box.see("end")
            self.mini_log_box.configure(state="disabled")
            
        self.ui_call(do_write)

    def update_running_ui(self, task_name: str, current_val: int, max_val: int):
        self.ui_call(self.lbl_mini_task.configure, text=f"当前任务: {task_name}")

        display_max = "无限" if max_val == 9999 else str(max_val)
        self.ui_call(self.lbl_mini_prog.configure, text=f"执行进度: {current_val} / {display_max}")

        if "跑图" in task_name:
            self.ui_call(self.task_panel.lbl_race.configure, text=f"执行: {current_val} / {display_max}")
        elif "买车" in task_name:
            self.ui_call(self.task_panel.lbl_car.configure, text=f"执行: {current_val} / {display_max}")
        elif "加点" in task_name:
            self.ui_call(self.task_panel.lbl_mastery.configure, text=f"执行: {current_val} / {display_max}")
        elif "移除" in task_name:
            self.ui_call(self.task_panel.lbl_sc.configure, text=f"执行: {current_val} / {display_max}")

    def update_loop_ui(self, current_loop: int, total_loops: int):
        self.ui_call(self.lbl_mini_loop.configure, text=f"大循环: {current_loop} / {total_loops}")

    def update_timer_loop(self):
        """挂机计时器自循环刷新线"""
        if not self.controller.is_running():
            return
        elapsed = int(time.monotonic() - self.start_time)
        hrs = elapsed // 3600
        mins = (elapsed % 3600) // 60
        secs = elapsed % 60
        self.lbl_mini_time.configure(text=f"总耗时: {hrs:02d}:{mins:02d}:{secs:02d}")
        self.after(1000, self.update_timer_loop)

    def on_vehicle_change(self, selected_display_name):
        """响应下拉框变化，记录 ID 并保存"""
        
        for vid, display_name in ProfileManager().get_available_vehicles():
            if display_name == selected_display_name:
                self.config["target_vehicle"] = vid
                self.save_config()
                self.log(f"已切换目标刷取车辆为: {selected_display_name}")
                # 通知规划面板更新默认值
                if hasattr(self, 'planner_panel'):
                    self.planner_panel.load_initial_values()
                break
    
    def ui_trigger_start(self, start_step: str):
        """捕获 UI 参数并下发异步流水线开启指令"""
        if self.controller.is_running():
            return

        self.save_config()
        
        # 同步基准配置给控制端特征匹配器
        self.controller.base_res = (self.config["base_width"], self.config["base_height"])

        # 隐藏庞大的主配置操作网格
        self.profile_frame.pack_forget()
        self.global_settings_frame.pack_forget()
        self.planner_panel.pack_forget()
        self.top_container.pack_forget()
        self.bottom_frame.pack_forget()
        self.btn_update.pack_forget()

        # 挂载精简版迷你侧边通知栏
        self.mini_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 强制小窗口安全吸附至当前屏幕右上方
        sw = self.winfo_screenwidth()
        calc_w = max(int(sw * 0.40), 650)
        calc_h = 160
        pos_x = sw - calc_w - 20
        self.attributes("-topmost", True)
        self.geometry(f"{calc_w}x{calc_h}+{pos_x}+20")
        
        self.start_time = time.monotonic()
        self.update_timer_loop()
        
        # 移交运行控制权给后台进程流
        self.controller.start_pipeline(start_step, self.config)
        
        self.start_time = time.monotonic()
        self.update_timer_loop()

    def on_controller_stopped(self):
        """当后台控制核心停止或遭遇熔断时，安全恢复大视窗界面结构"""
        def do_restore():
            self.mini_frame.pack_forget()
            
            # 按顺序线性重构标准大控制面板
            self.top_container.pack(fill="x", padx=18, pady=(18, 10))
            self.profile_frame.pack(fill="x", padx=18, pady=(15, 0))
            self.global_settings_frame.pack(fill="x", padx=18, pady=(15, 0))
            self.planner_panel.pack(fill="x", padx=18, pady=(10, 0))
            self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))
            self.btn_update.pack(fill="x", padx=18, pady=(6, 12))
            
            self.attributes("-topmost", False)
            self.geometry("1800x880")
            self.center_window()
            
        self.ui_call(do_restore)

    def sync_planner_to_ui(self, races, buys, masteries, removes):
        self.task_panel.sync_values(races, buys, masteries, removes)
        self.log(f"🧠 已应用智能规划配比: {races}:{buys}:{masteries}:{removes}")