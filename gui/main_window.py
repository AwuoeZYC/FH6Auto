import os
import json
import time
import threading
import webbrowser
import requests
import customtkinter as ctk
from PIL import Image
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
        self.geometry("1800x800")
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

        # 初始化应用静态默认配置
        self.config = {
            "race_count": 99,
            "buy_count": 30,
            "cj_count": 30,
            "sc_count": 30,
            "chk_1": True,
            "chk_2": True,
            "chk_3": True,
            "chk_4": True,
            "next_1": 2,
            "next_2": 3,
            "next_3": 1,
            "next_4": 1,
            "global_loops": 10,
            "skill_dirs": ["right", "up", "up", "up", "left"],
            "share_code": "890169683",
            "auto_restart": False,
            "restart_cmd": "start steam://run/2483190",
            "base_width": 1024,  
            "base_height": 768, 
        }
        self.load_config()

        # UI 组件装配与核心回调双向绑定
        self.setup_ui()
        self.controller.register_ui_callbacks(
            log_cb=self.log,
            progress_cb=self.update_running_ui,
            loop_cb=self.update_loop_ui,
            stop_cb=self.on_controller_stopped
        )
        
        self.update_skill_grid()
        self.center_window()
        self.sync_buy_to_sell()

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

    def sync_buy_to_sell(self, event=None):
        """同步买车数量与移除车辆数量的输入框数据"""
        try:
            val = "".join(c for c in self.entry_car.get() if c.isdigit())
            if not val:
                val = "0"
            self.entry_sc.delete(0, "end")
            self.entry_sc.insert(0, val)
        except Exception:
            pass

    def normalize_step_entry(self, entry_widget, default_value):
        """强制规范流水线单步转向序号输入范围为 1 至 4"""
        try:
            v = "".join(c for c in entry_widget.get() if c.isdigit())
            if not v:
                v = str(default_value)
            iv = int(v)
            if iv < 1: iv = 1
            if iv > 4: iv = 4
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(iv))
        except Exception:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(default_value))

    def on_entry_change(self, event, entry_widget, label_widget, config_key, max_len=4):
        """通用输入框实时响应函数：过滤非数字、限制长度、实时更新标签、实时保存配置"""
        val = "".join(c for c in entry_widget.get() if c.isdigit())
        if len(val) > max_len: 
            val = val[:max_len]
            
        if entry_widget.get() != val:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, val)
            
        # 实时同步到标签显示
        display_val = val if val else "0"
        label_widget.configure(text=f"执行: 0 / {display_val}")
        
        # 实时写入内存并保存到本地
        try:
            self.config[config_key] = int(display_val)
            self.save_config()
        except ValueError:
            pass

    # ==========================================
    # --- 配置管理数据流 ---
    # ==========================================
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception:
                pass

    def save_config(self):
        try:
            self.config["race_count"] = int(self.entry_race.get())
            self.config["buy_count"] = int(self.entry_car.get())
            self.config["cj_count"] = int(self.entry_cj.get())
            self.config["sc_count"] = int(self.entry_sc.get())
            self.config["global_loops"] = int(self.entry_global_loop.get())
            self.config["share_code"] = "".join(c for c in self.entry_share.get() if c.isdigit())
            self.config["next_1"] = int(self.entry_next1.get())
            self.config["next_2"] = int(self.entry_next2.get())
            self.config["next_3"] = int(self.entry_next3.get())
            self.config["next_4"] = int(self.entry_next4.get())
            self.config["base_width"] = int(self.entry_base_w.get())
            self.config["base_height"] = int(self.entry_base_h.get())
        except Exception:
            pass

        self.config["chk_1"] = self.var_chk1.get()
        self.config["chk_2"] = self.var_chk2.get()
        self.config["chk_3"] = self.var_chk3.get()
        self.config["chk_4"] = self.var_chk4.get()
        self.config["auto_restart"] = self.var_auto_restart.get()
        self.config["restart_cmd"] = self.le_restart_cmd.get().strip()

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def auto_calculate_pipeline(self):
        """根据目标 CR 金额与单车消耗，自动推演并优化大循环队列配比"""
        val_a = self.entry_calc_a.get().strip()
        if not val_a:
            self.log("未输入CR目标，放弃计算。")
            return
            
        try:
            target_cr = int(val_a)
            cost_per_car = int(self.entry_calc_b.get().strip()) if self.entry_calc_b.get().strip() else 81700
            sp_per_car = int(self.entry_calc_c.get().strip()) if self.entry_calc_c.get().strip() else 30
        except Exception:
            self.log("输入解析格式错误，请确保填入纯数字。")
            return

        if cost_per_car <= 0 or sp_per_car <= 0:
            return

        total_cars = target_cr // cost_per_car
        total_races = (total_cars * sp_per_car) // 10

        if total_races <= 0:
            self.log(f"目标金额过低，仅需购买 {total_cars} 辆车，无需启动跑图。")
            return

        if total_races <= 99:
            final_loops = 1
            final_races_per_loop = total_races
        else:
            import math
            loops = math.ceil(total_races / 99)
            avg_races = total_races // loops
            if avg_races >= 70:
                final_loops = loops
                final_races_per_loop = avg_races
            else:
                final_races_per_loop = 99
                final_loops = total_races // 99 

        cars_per_loop = (final_races_per_loop * 10) // sp_per_car
        if final_loops <= 0:
            return

        # 将最优推导数据同步至 UI 输入组件
        self.entry_race.delete(0, "end")
        self.entry_race.insert(0, str(final_races_per_loop))
        self.entry_car.delete(0, "end")
        self.entry_car.insert(0, str(cars_per_loop))
        self.entry_cj.delete(0, "end")
        self.entry_cj.insert(0, str(cars_per_loop))
        self.entry_sc.delete(0, "end")
        self.entry_sc.insert(0, str(cars_per_loop))
        self.entry_global_loop.delete(0, "end")
        self.entry_global_loop.insert(0, str(final_loops))

        self.log(f"✅ 分配器计算完成。总计需 {total_cars} 辆，共跑图 {total_races} 次。")
        self.save_config()

    # ==========================================
    # --- GUI 视窗布局装配 ---
    # ==========================================
    def setup_ui(self):
        self.top_container = ctk.CTkFrame(self, fg_color="transparent")
        self.top_container.pack(fill="x", padx=18, pady=(18, 10))

        self.config_frame = ctk.CTkFrame(self.top_container, fg_color="transparent")
        self.config_frame.pack(fill="x")

        def create_box(parent, title, btn_text, btn_cmd, btn_color, def_val, config_key):
            frame = ctk.CTkFrame(parent, width=210, height=300, corner_radius=12, border_width=1, border_color="#2B2B2B")
            frame.pack_propagate(False)
            frame.pack(side="left", padx=8)

            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight="bold", size=20)).pack(pady=(14, 10))
            
            btn = ctk.CTkButton(frame, text=btn_text, fg_color=btn_color, hover_color=btn_color, command=btn_cmd, width=140, height=38, corner_radius=10)
            btn.pack(pady=8, padx=10)

            entry = ctk.CTkEntry(frame, width=95, height=34, justify="center", corner_radius=8)
            entry.insert(0, str(def_val))
            entry.pack(pady=8)

            lbl = ctk.CTkLabel(frame, text=f"执行: 0 / {def_val}", text_color="#A0A0A0", font=ctk.CTkFont(size=16))
            lbl.pack(pady=8)
            
            # 【核心】：绑定键盘松开事件，实现类似 Vue/React 的双向绑定效果
            entry.bind("<KeyRelease>", lambda e: self.on_entry_change(e, entry, lbl, config_key))
            
            return frame, btn, entry, lbl

        def create_next_step(parent, var_checked, def_step):
            frame = ctk.CTkFrame(parent, width=120, height=300, corner_radius=12, border_width=1, border_color="#2B2B2B")
            frame.pack(side="left", padx=4)
            frame.pack_propagate(False)

            ctk.CTkLabel(frame, text="下一步骤", font=ctk.CTkFont(size=18, weight="bold"), text_color="#5DADE2").pack(pady=(55, 10))
            
            entry = ctk.CTkEntry(frame, width=60, height=34, justify="center", corner_radius=8)
            entry.insert(0, str(def_step))
            entry.pack(pady=6)

            chk = ctk.CTkCheckBox(frame, text="继续", variable=var_checked, width=60)
            chk.pack(pady=8)
            return frame, entry, chk

        self.var_chk1 = ctk.BooleanVar(value=self.config["chk_1"])
        self.var_chk2 = ctk.BooleanVar(value=self.config["chk_2"])
        self.var_chk3 = ctk.BooleanVar(value=self.config["chk_3"])
        self.var_chk4 = ctk.BooleanVar(value=self.config.get("chk_4", True))

        # 模块 1：跑图
        box_race, self.btn_race, self.entry_race, self.lbl_race = create_box(
            self.config_frame, "1. 循环跑图", "开始", lambda: self.ui_trigger_start("race"), "#1F6AA5", self.config["race_count"], "race_count"
        )
        self.entry_share = ctk.CTkEntry(box_race, width=130, justify="center", placeholder_text="蓝图数字代码")
        self.entry_share.insert(0, self.config["share_code"])
        self.entry_share.pack(pady=4)

        self.next_frame1, self.entry_next1, self.chk1 = create_next_step(self.config_frame, self.var_chk1, self.config.get("next_1", 2))

        # 模块 2：买车
        box_car, self.btn_car, self.entry_car, self.lbl_car = create_box(
            self.config_frame, "2. 批量买车", "开始", lambda: self.ui_trigger_start("buy"), "#2EA043", self.config["buy_count"], "buy_count"
        )
        self.entry_car.bind("<KeyRelease>", self.sync_buy_to_sell)

        self.next_frame2, self.entry_next2, self.chk2 = create_next_step(self.config_frame, self.var_chk2, self.config.get("next_2", 3))

        # 模块 3：抽奖
        self.box_cj = ctk.CTkFrame(self.config_frame, width=360, height=300, corner_radius=12, border_width=1, border_color="#2B2B2B")
        self.box_cj.pack_propagate(False)
        self.box_cj.pack(side="left", padx=8)

        top_cj = ctk.CTkFrame(self.box_cj, fg_color="transparent")
        top_cj.pack(fill="x", pady=10)

        left_cj = ctk.CTkFrame(top_cj, fg_color="transparent")
        left_cj.pack(side="left", padx=10)

        ctk.CTkLabel(left_cj, text="3. 超级抽奖", font=ctk.CTkFont(weight="bold", size=20)).pack(pady=(0, 8))

        self.btn_cj = ctk.CTkButton(left_cj, text="开始", width=120, height=38, corner_radius=10, fg_color="#8E44AD", hover_color="#8E44AD", command=lambda: self.ui_trigger_start("cj"))
        self.btn_cj.pack(pady=5)

        self.entry_cj = ctk.CTkEntry(left_cj, width=95, height=34, justify="center", corner_radius=8)
        self.entry_cj.insert(0, str(self.config["cj_count"]))
        self.entry_cj.pack(pady=5)

        self.lbl_cj = ctk.CTkLabel(left_cj, text=f"执行: 0 / {self.config['cj_count']}", text_color="#A0A0A0", font=ctk.CTkFont(size=14))
        self.lbl_cj.pack(pady=(2, 8))

        dir_frame = ctk.CTkFrame(left_cj, fg_color="transparent")
        dir_frame.pack(pady=4)

        for text, val in [("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right")]:
            ctk.CTkButton(dir_frame, text=text, width=30, height=28, corner_radius=8, command=lambda x=val: self.add_skill_dir(x)).pack(side="left", padx=2)

        ctk.CTkButton(left_cj, text="清除矩阵", width=90, height=28, corner_radius=8, fg_color="#C0392B", hover_color="#A93226", command=self.clear_skill_dir).pack(pady=8)

        self.grid_frame = ctk.CTkFrame(top_cj, fg_color="transparent")
        self.grid_frame.pack(side="right", padx=12)

        self.grid_labels = [[None] * 4 for _ in range(4)]
        for r in range(4):
            for c in range(4):
                lbl = ctk.CTkLabel(self.grid_frame, text="", width=28, height=28, corner_radius=5, fg_color="#444444")
                lbl.grid(row=r, column=c, padx=4, pady=4)
                self.grid_labels[r][c] = lbl
        ctk.CTkLabel(self.grid_frame, text="技能树", font=ctk.CTkFont(size=14, weight="bold"), text_color="#A0A0A0").grid(row=4, column=0, columnspan=4, pady=(8, 0))

        self.next_frame3, self.entry_next3, self.chk3 = create_next_step(self.config_frame, self.var_chk3, self.config.get("next_3", 4))

        # 模块 4：移除车辆
        box_sc, self.btn_sc, self.entry_sc, self.lbl_sc = create_box(
            self.config_frame, "4. 移除车辆", "！！开始！！", lambda: self.ui_trigger_start("sell"), "#D97706", self.config.get("sc_count", 30), "sc_count"
        )

        self.next_frame4, self.entry_next4, self.chk4 = create_next_step(self.config_frame, self.var_chk4, self.config.get("next_4", 1))

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
        self.cb_auto_restart = ctk.CTkCheckBox(self.global_settings_frame, text="游戏闪退自动重启", variable=self.var_auto_restart)
        self.cb_auto_restart.pack(side="left", padx=(10, 20))
        
        ctk.CTkLabel(self.global_settings_frame, text="启动命令(CMD):").pack(side="left", padx=(10, 5))
        self.le_restart_cmd = ctk.CTkEntry(self.global_settings_frame, width=250, height=28)
        self.le_restart_cmd.insert(0, self.config.get("restart_cmd", "start steam://run/2483190"))
        self.le_restart_cmd.pack(side="left", padx=(0, 20))

        # 计算器栏
        self.calc_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        self.calc_frame.pack(fill="x", padx=18, pady=(10, 0))
        self.calc_frame.pack_propagate(False)
        
        ctk.CTkLabel(self.calc_frame, text="次数计算器", font=ctk.CTkFont(weight="bold", size=15), text_color="#2EA043").pack(side="left", padx=(15, 20))
        ctk.CTkLabel(self.calc_frame, text="CR:").pack(side="left", padx=(0, 5))
        
        self.entry_calc_a = ctk.CTkEntry(self.calc_frame, width=110, height=28, placeholder_text="留空不计算")
        self.entry_calc_a.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(self.calc_frame, text="单车成本(CR):").pack(side="left", padx=(0, 5))
        self.entry_calc_b = ctk.CTkEntry(self.calc_frame, width=70, height=28)
        self.entry_calc_b.insert(0, "81700")
        self.entry_calc_b.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(self.calc_frame, text="单车技能点:").pack(side="left", padx=(0, 5))
        self.entry_calc_c = ctk.CTkEntry(self.calc_frame, width=50, height=28)
        self.entry_calc_c.insert(0, "30")
        self.entry_calc_c.pack(side="left", padx=(0, 15))
        
        ctk.CTkButton(self.calc_frame, text="计算并应用", width=90, height=28, fg_color="#D35400", hover_color="#A04000", command=self.auto_calculate_pipeline).pack(side="left", padx=(0, 15))

        # 动态绑定限制器
        def limit_len(widget, max_l):
            val = "".join(c for c in widget.get() if c.isdigit())
            if len(val) > max_l: val = val[:max_l]
            if widget.get() != val:
                widget.delete(0, "end")
                widget.insert(0, val)
        self.entry_calc_a.bind("<KeyRelease>", lambda e: limit_len(self.entry_calc_a, 10))
        self.entry_calc_b.bind("<KeyRelease>", lambda e: limit_len(self.entry_calc_b, 7))
        self.entry_calc_c.bind("<KeyRelease>", lambda e: limit_len(self.entry_calc_c, 2))

        self.entry_next1.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next1, 2))
        self.entry_next2.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next2, 3))
        self.entry_next3.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next3, 4))
        self.entry_next4.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next4, 1))

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

        self.btn_update = ctk.CTkButton(self, text="🔄 检查更新 / GitHub", fg_color="#2EA043", hover_color="#238636", height=42, corner_radius=12, font=ctk.CTkFont(weight="bold", size=15), command=self.open_update_window)
        self.btn_update.pack(fill="x", padx=18, pady=(6, 12))

    # ==========================================
    # --- 技能树参数矩阵映射 ---
    # ==========================================
    def add_skill_dir(self, direction):
        self.config["skill_dirs"].append(direction)
        self.update_skill_grid()
        self.save_config()

    def clear_skill_dir(self):
        self.config["skill_dirs"].clear()
        self.update_skill_grid()
        self.save_config()

    def update_skill_grid(self):
        for r in range(4):
            for c in range(4):
                self.grid_labels[r][c].configure(fg_color="#333333")

        curr_r, curr_c = 3, 0
        self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
        valid_dirs = []

        for d in self.config["skill_dirs"]:
            if d == "up": curr_r -= 1
            elif d == "down": curr_r += 1
            elif d == "left": curr_c -= 1
            elif d == "right": curr_c += 1

            if 0 <= curr_r < 4 and 0 <= curr_c < 4:
                self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
                valid_dirs.append(d)
            else:
                break
        self.config["skill_dirs"] = valid_dirs

    # ==========================================
    # --- 控制层回调槽函数实现 ---
    # ==========================================
    def log(self, message: str):
        """线程安全的双日志框行同步写入器"""
        curr_time = time.strftime("%H:%M:%S")
        full_msg = f"[{curr_time}] {message}"

        def do_write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", full_msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
            
            self.mini_log_box.configure(state="normal")
            self.mini_log_box.insert("end", full_msg + "\n")
            self.mini_log_box.see("end")
            self.mini_log_box.configure(state="disabled")
            
        self.ui_call(do_write)

    def update_running_ui(self, task_name: str, current_val: int, max_val: int):
        self.ui_call(self.lbl_mini_task.configure, text=f"当前任务: {task_name}")
        self.ui_call(self.lbl_mini_prog.configure, text=f"执行进度: {current_val} / {max_val}")
        
        # 反向同步更新主视图上的对应大计数器
        if "跑图" in task_name:
            self.ui_call(self.lbl_race.configure, text=f"执行: {current_val} / {max_val}")
        elif "买车" in task_name:
            self.ui_call(self.lbl_car.configure, text=f"执行: {current_val} / {max_val}")
        elif "抽奖" in task_name:
            self.ui_call(self.lbl_cj.configure, text=f"执行: {current_val} / {max_val}")
        elif "移除" in task_name:
            self.ui_call(self.lbl_sc.configure, text=f"执行: {current_val} / {max_val}")

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

    def ui_trigger_start(self, start_step: str):
        """捕获 UI 参数并下发异步流水线开启指令"""
        if self.controller.is_running():
            return

        self.save_config()
        
        # 同步基准配置给控制端特征匹配器
        self.controller.base_res = (self.config["base_width"], self.config["base_height"])

        # 隐藏庞大的主配置操作网格
        self.config_frame.pack_forget()
        self.global_settings_frame.pack_forget()
        self.calc_frame.pack_forget()
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

    def on_controller_stopped(self):
        """当后台控制核心停止或遭遇熔断时，安全恢复大视窗界面结构"""
        def do_restore():
            self.mini_frame.pack_forget()
            
            # 按顺序线性重构标准大控制面板
            self.top_container.pack(fill="x", padx=18, pady=(18, 10))
            self.config_frame.pack(fill="x")
            self.global_settings_frame.pack(fill="x", pady=(15, 0))
            self.calc_frame.pack(fill="x", pady=(10, 0))
            self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))
            self.btn_update.pack(fill="x", padx=18, pady=(6, 12))
            
            self.attributes("-topmost", False)
            self.geometry("1800x800")
            self.center_window()
            
        self.ui_call(do_restore)

    # ==========================================
    # --- 纯净版热更新模块 ---
    # ==========================================
    def open_update_window(self):
        """打开纯净的检查更新窗口"""
        if hasattr(self, "update_win") and self.update_win is not None and self.update_win.winfo_exists():
            self.update_win.focus()
            return

        self.update_win = ctk.CTkToplevel(self)
        self.update_win.title("检查更新")
        self.update_win.geometry("340x220")
        self.update_win.resizable(False, False)
        self.update_win.transient(self)

        self.update_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 220) // 2
        self.update_win.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(self.update_win, text="FH6Auto 自动化更新", font=ctk.CTkFont(weight="bold", size=18), text_color="#3498DB").pack(pady=(25, 10))
        
        self.lbl_version = ctk.CTkLabel(self.update_win, text=f"当前版本: v{CURRENT_VERSION}", text_color="gray", font=ctk.CTkFont(size=13))
        self.lbl_version.pack(pady=5)

        def check_update_logic():
            self.ui_call(self.lbl_version.configure, text="正在连接 GitHub...", text_color="#3498DB")
            try:
                # 换成你自己的 Github 仓库 API
                api_url = "https://api.github.com/repos/AwuoeZYC/FH6Auto/releases/latest"
                resp = requests.get(api_url, timeout=5, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    remote_ver = data.get("tag_name", "v0.0.0").replace("v", "")
                    
                    if parse_version(remote_ver) > parse_version(CURRENT_VERSION):
                        self.ui_call(self.lbl_version.configure, text=f"发现新版本 v{remote_ver}！", text_color="#2EA043")
                        
                        # 提取 Github Release 中的 exe 下载地址
                        download_url = ""
                        for asset in data.get("assets", []):
                            if asset.get("name", "").endswith(".exe"):
                                download_url = asset.get("browser_download_url")
                                break
                                
                        if download_url:
                            def ask_user():
                                # 使用国内镜像加速下载
                                proxy_url = f"https://mirror.ghproxy.com/{download_url}"
                                from tkinter import messagebox
                                if messagebox.askyesno("发现新版本", f"检测到新版本 v{remote_ver}\n\n是否立即下载并热更新？\n(支持断点随时取消)"):
                                    self.start_safe_download(proxy_url, remote_ver)
                            self.ui_call(ask_user)
                        else:
                            self.ui_call(self.lbl_version.configure, text="新版本未包含 exe 附件，请手动下载", text_color="#F39C12")
                    else:
                        self.ui_call(self.lbl_version.configure, text=f"当前已是最新版本 (v{CURRENT_VERSION})", text_color="gray")
                else:
                    self.ui_call(self.lbl_version.configure, text="检查更新失败：网络请求被拒", text_color="#DA3633")
            except Exception as e:
                error_msg = f"异常: {type(e).__name__} - {str(e)}"
                print(f"【DEBUG 更新报错】 {error_msg}")
                self.ui_call(self.lbl_version.configure, text=error_msg[:30], text_color="#DA3633")

        btn_frame = ctk.CTkFrame(self.update_win, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="检查更新", width=100, height=32, fg_color="#444444", hover_color="#555555", command=lambda: threading.Thread(target=check_update_logic, daemon=True).start()).pack(side="left", padx=5)
        # 换成你自己的 Github 仓库主页
        ctk.CTkButton(btn_frame, text="前往 GitHub", width=100, height=32, fg_color="#2EA043", hover_color="#238636", command=lambda: webbrowser.open("https://github.com/AwuoeZYC/FH6Auto")).pack(side="left", padx=5)

    def start_safe_download(self, url: str, version: str):
        """带有进度条的安全热更新下载方法，支持随时取消"""
        dl_win = ctk.CTkToplevel(self)
        dl_win.title(f"正在下载 v{version}")
        dl_win.geometry("400x160")
        dl_win.resizable(False, False)
        dl_win.transient(self)
        
        dl_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 160) // 2
        dl_win.geometry(f"+{x}+{y}")
        
        lbl_status = ctk.CTkLabel(dl_win, text="正在连接节点...", font=ctk.CTkFont(weight="bold"))
        lbl_status.pack(pady=(20, 5))

        progress_bar = ctk.CTkProgressBar(dl_win, width=300)
        progress_bar.set(0)
        progress_bar.pack(pady=5)

        cancel_flag = {"is_cancelled": False}

        def cancel_download():
            cancel_flag["is_cancelled"] = True
            dl_win.destroy()

        btn_cancel = ctk.CTkButton(dl_win, text="取消下载", fg_color="#DA3633", hover_color="#B02A37", width=100, command=cancel_download)
        btn_cancel.pack(pady=10)

        def download_thread():
            try:
                current_exe_path = sys.executable 
                if not current_exe_path.lower().endswith("fh6auto.exe"):
                    self.ui_call(lbl_status.configure, text="[开发环境提示] 源码运行不支持热替换", text_color="#F39C12")
                    return

                tmp_file_path = current_exe_path + ".tmp"
                resp = requests.get(url, stream=True, timeout=10, verify=False)
                resp.raise_for_status()
                total_size = int(resp.headers.get('content-length', 0))
                
                downloaded_size = 0
                with open(tmp_file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if cancel_flag["is_cancelled"]:
                            break
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            if total_size > 0:
                                pct = downloaded_size / total_size
                                self.ui_call(progress_bar.set, pct)
                                self.ui_call(lbl_status.configure, text=f"下载进度: {int(pct*100)}%")

                if cancel_flag["is_cancelled"]:
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)
                    return

                self.ui_call(lbl_status.configure, text="下载完成！正在部署并重启...", text_color="#2EA043")
                time.sleep(1.0)
                self.ui_call(dl_win.destroy)

                import shutil
                from tkinter import messagebox
                bundled_updater = get_asset_path("Updater.exe")
                external_updater = os.path.join(os.environ.get("TEMP", "C:\\"), "FH6_Updater.exe")
                
                if bundled_updater and os.path.exists(bundled_updater):
                    shutil.copy2(bundled_updater, external_updater)
                    subprocess.Popen([external_updater, str(os.getpid()), current_exe_path, tmp_file_path], creationflags=subprocess.CREATE_NO_WINDOW)
                    os._exit(0)
                else:
                    self.ui_call(messagebox.showerror, "错误", "缺少更新组件(Updater.exe)，无法热替换！")

            except Exception:
                if not cancel_flag["is_cancelled"]:
                    self.ui_call(lbl_status.configure, text="下载中断：网络异常", text_color="#DA3633")

        threading.Thread(target=download_thread, daemon=True).start()