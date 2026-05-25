import sys
import os
import json
import time
import shutil
import ctypes
import threading
import subprocess
import webbrowser

import customtkinter as ctk
ctk.deactivate_automatic_dpi_awareness()
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)
import cv2
import numpy as np
import pyautogui
import pydirectinput
import requests
from pynput import keyboard
from PIL import Image, ImageGrab
import win32gui
import pickle
import threading

from config import (
    APP_DIR, INTERNAL_DIR, CONFIG_FILE, LOG_FILE, CACHE_DIR,
    TEMPLATE_CACHE_FILE, TEMPLATE_META_FILE, CURRENT_VERSION,
    auto_extract_images, get_img_path, get_asset_path, parse_version
)
import core.input_driver as input_driver

from core.vision import VisionEngine

import logic.race
import logic.buy
import logic.wheelspin
import logic.sell

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
pyautogui.FAILSAFE = False


class FH_UltimateBot(ctk.CTk):
    def __init__(self):
        super().__init__()
        #窗口相关
        self.title(f"FH6Auto by YSTO v{CURRENT_VERSION}")
        self.geometry("1800x800")
        #self.minsize(980, 560)
        self.attributes("-topmost", False)
        self.attributes("-alpha", 0.98)
        self.resizable(False, False)

        try:
            icon_path = get_asset_path("icon.ico")
            if icon_path:
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.is_running = False
        self.current_thread = None

        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.sc_count = 0
        self.global_loop_current = 0

        self.support_win = None
        # 注入日志方法、状态检查方法，以及动态获取 regions 的回调函数
        self.vision = VisionEngine(
            logger_callback=self.log, 
            running_check_callback=lambda: self.is_running,
            get_regions_callback=lambda: getattr(self, 'regions', {})
        )
        self.init_regions()
        
                # 【优化加载速度】：将IO提取与图像缓存的加载/生成放到后台线程，避免阻塞主界面启动
        def background_init():
            auto_extract_images()
            self.vision.prepare_template_cache()
        threading.Thread(target=background_init, daemon=True).start()

        #初始配置
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
        }
        self.load_config()

        self.setup_ui()
        self.start_hotkey_listener()
        self.update_skill_grid()
        self.center_window()
        self.log("免责声明：本脚本仅供 Python 自动化技术交流与学习使用。请勿用于商业盈利或破坏游戏平衡，因使用本脚本造成的账号封禁等损失，由使用者自行承担。")
        self.log("默认刷图车辆：【斯巴鲁Impreza 22B-STi Version】【调校S2  900】【保持默认涂装】【收藏车辆】")
        self.log("启动前先将键盘设置为【英文键盘】")
        self.log("游戏设置为【自动转向】【自动挡】，游戏语言设置为【简体中文】")
        self.log("大部分以图像识别作为引导，减少机器盲目操作的风险，但仍无法完全避免，使用前请做好准备")

    # ==========================================
    # --- UI 安全调度 ---
    # ==========================================
    def ui_call(self, func, *args, **kwargs):
        try:
            self.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        gx, gy, gw, gh = self.regions["全界面"]
        x = gx + (gw - w) // 2
        y = gy + (gh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
    def sync_buy_to_sell(self, event=None):
        try:
            val = "".join(c for c in self.entry_car.get() if c.isdigit())
            if val == "":
                val = "0"
            self.entry_sc.delete(0, "end")
            self.entry_sc.insert(0, val)
        except Exception:
            pass

    def normalize_step_entry(self, entry_widget, default_value):
        try:
            v = "".join(c for c in entry_widget.get() if c.isdigit())
            if v == "":
                v = str(default_value)
            iv = int(v)
            if iv < 1:
                iv = 1
            if iv > 4:
                iv = 4
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(iv))
        except Exception:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(default_value))
    # ==========================================
    # --- 初始化全局 Region ---
    # ==========================================
    def init_regions(self):
        sw, sh = pyautogui.size()
        self.update_regions_by_window(0, 0, sw, sh)

    def update_regions_by_window(self, x, y, w, h):
        self.regions = {
            "全界面": (x, y, w, h),
            "左上": (x, y, w // 2, h // 2),
            "右上": (x + w // 2, y, w // 2, h // 2),
            "左下": (x, y + h // 2, w // 2, h // 2),
            "右下": (x + w // 2, y + h // 2, w // 2, h // 2),
            "上": (x, y, w, h // 2),
            "下": (x, y + h // 2, w, h // 2),
            "左": (x, y, w // 2, h),
            "右": (x + w // 2, y, w // 2, h),
            "中间": (x + w // 4, y + h // 4, w // 2, h // 2),
        }

    # ==========================================
    # --- 配置管理 ---
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
            #self.config["base_width"] = int(self.entry_base_w.get())
            self.config["next_1"] = int(self.entry_next1.get())
            self.config["next_2"] = int(self.entry_next2.get())
            self.config["next_3"] = int(self.entry_next3.get())
            self.config["next_4"] = int(self.entry_next4.get())
        except Exception:
            pass

        self.config["chk_1"] = self.var_chk1.get()
        self.config["chk_2"] = self.var_chk2.get()
        self.config["chk_3"] = self.var_chk3.get()
        self.config["chk_4"] = self.var_chk4.get()
        self.config["auto_restart"] = self.var_auto_restart.get()
        self.config["restart_cmd"] = self.le_restart_cmd.get().strip()
        try:
            if hasattr(self, "entry_calc_a"):
                self.config["calc_a"] = self.entry_calc_a.get().strip()
                self.config["calc_b"] = self.entry_calc_b.get().strip()
                self.config["calc_c"] = self.entry_calc_c.get().strip()
        except Exception:
            pass
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def auto_calculate_pipeline(self):
        val_a = self.entry_calc_a.get().strip()
        if not val_a:
            self.log("未输入CR，无需计算。")
            return
            
        try:
            target_cr = int(val_a)
            val_b = self.entry_calc_b.get().strip()
            cost_per_car = int(val_b) if val_b else 81700
            
            val_c = self.entry_calc_c.get().strip()
            sp_per_car = int(val_c) if val_c else 30
        except Exception:
            self.log("输入格式有误，请确保只输入数字！")
            return

        if cost_per_car <= 0 or sp_per_car <= 0:
            self.log("单车成本或技能点不能为 0！")
            return

        # 1. 基础转换（总车数 & 总跑图数）
        total_cars = target_cr // cost_per_car
        total_races = (total_cars * sp_per_car) // 10

        if total_races <= 0:
            self.log(f"目标金额不足(只够买{total_cars}辆车)，无法产生有效跑图！")
            return

        # 2. 核心分配逻辑
        if total_races <= 99:
            final_loops = 1
            final_races_per_loop = total_races
        else:
            import math
            loops = math.ceil(total_races / 99)
            avg_races = total_races // loops

            # 如果平均下来大于等于70次，就采用均分策略
            if avg_races >= 70:
                final_loops = loops
                final_races_per_loop = avg_races
            # 小于70次，直接拉满每个99，舍弃最后不够塞满一轮的余数
            else:
                final_races_per_loop = 99
                final_loops = total_races // 99 

        # 3. 反推每一轮买车、抽奖、卖车的具体数量
        cars_per_loop = (final_races_per_loop * 10) // sp_per_car

        if final_loops <= 0:
            self.log("计算后可用大循环次数为0。")
            return

        # 4. 自动填写到界面
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

        self.log(f"✅计算完成: 总计需{total_cars}车, 共跑图{total_races}次。分配为: {final_loops} 个大循环, 每轮跑图 {final_races_per_loop} 次, 动作 {cars_per_loop} 辆。")
        self.save_config()

    # ==========================================
    # --- UI 布局设计 ---
    # ==========================================
    def setup_ui(self):
        self.top_container = ctk.CTkFrame(self, fg_color="transparent")
        self.top_container.pack(fill="x", padx=18, pady=(18, 10))

        self.config_frame = ctk.CTkFrame(self.top_container, fg_color="transparent")
        self.config_frame.pack(fill="x")

        def create_box(parent, title, btn_text, btn_cmd, btn_color, def_val):
            frame = ctk.CTkFrame(
                parent,
                width=210,
                height=300,
                corner_radius=12,
                border_width=1,
                border_color="#2B2B2B",
            )
            frame.pack_propagate(False)
            frame.pack(side="left", padx=8)

            ctk.CTkLabel(
                frame,
                text=title,
                font=ctk.CTkFont(weight="bold", size=20),
            ).pack(pady=(14, 10))

            btn = ctk.CTkButton(
                frame,
                text=btn_text,
                fg_color=btn_color,
                hover_color=btn_color,
                command=btn_cmd,
                width=140,
                height=38,
                corner_radius=10,
            )
            btn.pack(pady=8, padx=10)

            entry = ctk.CTkEntry(frame, width=95, height=34, justify="center", corner_radius=8)
            entry.insert(0, str(def_val))
            entry.pack(pady=8)

            lbl = ctk.CTkLabel(
                frame,
                text=f"执行: 0 / {def_val}",
                text_color="#A0A0A0",
                font=ctk.CTkFont(size=16),
            )
            lbl.pack(pady=8)
            return frame, btn, entry, lbl

        def create_next_step(parent, var_checked, def_step, box_h=300):
            frame = ctk.CTkFrame(parent, width=120, height=box_h, corner_radius=12, border_width=1, border_color="#2B2B2B")
            frame.pack(side="left", padx=4)
            frame.pack_propagate(False)

            ctk.CTkLabel(
                frame,
                text="下一步骤",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color="#5DADE2",
            ).pack(pady=(55, 10))

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

        box_race, self.btn_race, self.entry_race, self.lbl_race = create_box(
            self.config_frame,
            "1. 循环跑图",
            "开始",
            lambda: self.start_pipeline("race"),
            "#1F6AA5",
            self.config["race_count"],
        )
        self.entry_share = ctk.CTkEntry(box_race, width=130, justify="center", placeholder_text="蓝图数字代码")
        self.entry_share.insert(0, self.config["share_code"])
        self.entry_share.pack(pady=4)

        self.next_frame1, self.entry_next1, self.chk1 = create_next_step(
            self.config_frame, self.var_chk1, self.config.get("next_1", 2)
        )

        box_car, self.btn_car, self.entry_car, self.lbl_car = create_box(
            self.config_frame,
            "2. 批量买车",
            "开始",
            lambda: self.start_pipeline("buy"),
            "#2EA043",
            self.config["buy_count"],
        )
        self.entry_car.bind("<KeyRelease>", self.sync_buy_to_sell)

        self.next_frame2, self.entry_next2, self.chk2 = create_next_step(
            self.config_frame, self.var_chk2, self.config.get("next_2", 3)
        )

        self.box_cj = ctk.CTkFrame(
            self.config_frame,
            width=360,
            height=300,
            corner_radius=12,
            border_width=1,
            border_color="#2B2B2B",
        )
        self.box_cj.pack_propagate(False)
        self.box_cj.pack(side="left", padx=8)

        top_cj = ctk.CTkFrame(self.box_cj, fg_color="transparent")
        top_cj.pack(fill="x", pady=10)

        left_cj = ctk.CTkFrame(top_cj, fg_color="transparent")
        left_cj.pack(side="left", padx=10)

        ctk.CTkLabel(left_cj, text="3. 超级抽奖", font=ctk.CTkFont(weight="bold", size=20)).pack(pady=(0, 8))

        self.btn_cj = ctk.CTkButton(
            left_cj,
            text="开始",
            width=120,
            height=38,
            corner_radius=10,
            fg_color="#8E44AD",
            hover_color="#8E44AD",
            command=lambda: self.start_pipeline("cj"),
        )
        self.btn_cj.pack(pady=5)

        self.entry_cj = ctk.CTkEntry(left_cj, width=95, height=34, justify="center", corner_radius=8)
        self.entry_cj.insert(0, str(self.config["cj_count"]))
        self.entry_cj.pack(pady=5)

        self.lbl_cj = ctk.CTkLabel(
            left_cj,
            text=f"执行: 0 / {self.config['cj_count']}",
            text_color="#A0A0A0",
            font=ctk.CTkFont(size=14),
        )
        self.lbl_cj.pack(pady=(2, 8))

        dir_frame = ctk.CTkFrame(left_cj, fg_color="transparent")
        dir_frame.pack(pady=4)

        for text, val in [("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right")]:
            ctk.CTkButton(
                dir_frame,
                text=text,
                width=30,
                height=28,
                corner_radius=8,
                command=lambda x=val: self.add_skill_dir(x),
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            left_cj,
            text="清除矩阵",
            width=90,
            height=28,
            corner_radius=8,
            fg_color="#C0392B",
            hover_color="#A93226",
            command=self.clear_skill_dir,
        ).pack(pady=8)

        self.grid_frame = ctk.CTkFrame(top_cj, fg_color="transparent")
        self.grid_frame.pack(side="right", padx=12)

        self.grid_labels = [[None] * 4 for _ in range(4)]
        for r in range(4):
            for c in range(4):
                lbl = ctk.CTkLabel(
                    self.grid_frame,
                    text="",
                    width=28,
                    height=28,
                    corner_radius=5,
                    fg_color="#444444",
                )
                lbl.grid(row=r, column=c, padx=4, pady=4)
                self.grid_labels[r][c] = lbl
        ctk.CTkLabel(
            self.grid_frame,
            text="技能树",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#A0A0A0",
        ).grid(row=4, column=0, columnspan=4, pady=(8, 0))

        self.next_frame3, self.entry_next3, self.chk3 = create_next_step(
            self.config_frame, self.var_chk3, self.config.get("next_3", 4)
        )

        box_sc, self.btn_sc, self.entry_sc, self.lbl_sc = create_box(
            self.config_frame,
            "4. 移除车辆",
            "！！开始！！",
            lambda: self.start_pipeline("sell"),
            "#D97706",
            self.config.get("sc_count", 30),
        )

        self.next_frame4, self.entry_next4, self.chk4 = create_next_step(
            self.config_frame, self.var_chk4, self.config.get("next_4", 1)
        )
                # ====== 抽离到底部的全局设置栏 (放在上方) ======
        # 【修改1】把 self.top_container 改成了 self
        self.global_settings_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        # 【修改2】加上了 padx=18，让它和上下边缘对齐
        self.global_settings_frame.pack(fill="x", padx=18, pady=(15, 0))
        self.global_settings_frame.pack_propagate(False)
        ctk.CTkLabel(
            self.global_settings_frame, 
            text="⚙️ 循环与守护设置", 
            font=ctk.CTkFont(weight="bold", size=15), 
            text_color="#F1C40F"
        ).pack(side="left", padx=(15, 20))
        ctk.CTkLabel(self.global_settings_frame, text="大循环次数:").pack(side="left", padx=(10, 5))
        self.entry_global_loop = ctk.CTkEntry(self.global_settings_frame, width=70, height=28, justify="center")
        self.entry_global_loop.insert(0, str(self.config.get("global_loops", 10)))
        self.entry_global_loop.pack(side="left", padx=(0, 20))
        self.var_auto_restart = ctk.BooleanVar(value=self.config.get("auto_restart", True))
        self.cb_auto_restart = ctk.CTkCheckBox(self.global_settings_frame, text="游戏闪退自动重启（测试）", variable=self.var_auto_restart)
        self.cb_auto_restart.pack(side="left", padx=(10, 20))
        ctk.CTkLabel(self.global_settings_frame, text="启动命令(CMD):").pack(side="left", padx=(10, 5))
        self.le_restart_cmd = ctk.CTkEntry(self.global_settings_frame, width=250, height=28)
        self.le_restart_cmd.insert(0, self.config.get("restart_cmd", "start steam://run/2483190"))
        self.le_restart_cmd.pack(side="left", padx=(0, 20))


        # ====== 新增：智能计算分配工具栏 (放在下方) ======
        # 【修改1】把 self.top_container 改成了 self
        self.calc_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        # 【修改2】加上了 padx=18，让它和上下边缘对齐
        self.calc_frame.pack(fill="x", padx=18, pady=(10, 0))
        self.calc_frame.pack_propagate(False)
        ctk.CTkLabel(
            self.calc_frame, 
            text="次数计算器", 
            font=ctk.CTkFont(weight="bold", size=15), 
            text_color="#2EA043"
        ).pack(side="left", padx=(15, 20))
        ctk.CTkLabel(self.calc_frame, text="CR:").pack(side="left", padx=(0, 5))
        self.entry_calc_a = ctk.CTkEntry(self.calc_frame, width=110, height=28, placeholder_text="留空不计算")
        self.entry_calc_a.insert(0, self.config.get("calc_a", ""))
        self.entry_calc_a.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(self.calc_frame, text="单车成本(CR):").pack(side="left", padx=(0, 5))
        self.entry_calc_b = ctk.CTkEntry(self.calc_frame, width=70, height=28)
        self.entry_calc_b.insert(0, self.config.get("calc_b", "81700"))
        self.entry_calc_b.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(self.calc_frame, text="单车技能点:").pack(side="left", padx=(0, 5))
        self.entry_calc_c = ctk.CTkEntry(self.calc_frame, width=50, height=28)
        self.entry_calc_c.insert(0, self.config.get("calc_c", "30"))
        self.entry_calc_c.pack(side="left", padx=(0, 15))
        ctk.CTkButton(
            self.calc_frame,
            text="计算并应用",
            width=90,
            height=28,
            fg_color="#D35400",
            hover_color="#A04000",
            command=self.auto_calculate_pipeline
        ).pack(side="left", padx=(0, 15))
        
        # 动态限制输入框长度（只允许数字并截断）
        def limit_len(evt, widget, max_l):
            val = "".join(c for c in widget.get() if c.isdigit())
            if len(val) > max_l:
                val = val[:max_l]
            if widget.get() != val:
                widget.delete(0, "end")
                widget.insert(0, val)
        self.entry_calc_a.bind("<KeyRelease>", lambda e: limit_len(e, self.entry_calc_a, 10))
        self.entry_calc_b.bind("<KeyRelease>", lambda e: limit_len(e, self.entry_calc_b, 7))
        self.entry_calc_c.bind("<KeyRelease>", lambda e: limit_len(e, self.entry_calc_c, 2))
        # ==========================================
        #ctk.CTkLabel(self.global_settings_frame, text="图片原宽（不要修改）:").pack(side="left", padx=(10, 5))
        #self.entry_base_w = ctk.CTkEntry(self.global_settings_frame, width=70, height=28, justify="center")
        #self.entry_base_w.insert(0, str(self.config.get("base_width", 2560)))
        #self.entry_base_w.pack(side="left", padx=(0, 20))

        self.entry_next1.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next1, 2))
        self.entry_next2.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next2, 3))
        self.entry_next3.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next3, 4))
        self.entry_next4.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next4, 1))

        if not self.entry_sc.get().strip():
            self.entry_sc.insert(0, "30")

        # === 全新的横向迷你UI设计 ===
        self.mini_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=10)

        # 1. 日志区 (最左侧，占据主要伸缩空间)
        self.mini_log_box = ctk.CTkTextbox(self.mini_frame, state="disabled", wrap="word", font=ctk.CTkFont(size=13), fg_color="#2B2B2B")
        self.mini_log_box.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

        # 2. 信息区 (垂直排列任务状态和耗时)
        self.mini_info_frame = ctk.CTkFrame(self.mini_frame, fg_color="transparent")
        self.mini_info_frame.pack(side="left", fill="y", padx=5, pady=10)

        self.lbl_mini_task = ctk.CTkLabel(self.mini_info_frame, text="当前任务: 等待中", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498DB")
        self.lbl_mini_task.pack(pady=(5, 2), anchor="w")

        self.lbl_mini_prog = ctk.CTkLabel(self.mini_info_frame, text="任务进度: 0 / 0", font=ctk.CTkFont(size=13))
        self.lbl_mini_prog.pack(pady=2, anchor="w")

        self.lbl_mini_loop = ctk.CTkLabel(self.mini_info_frame, text="大循环: 0 / 0", font=ctk.CTkFont(size=13))
        self.lbl_mini_loop.pack(pady=2, anchor="w")

        # 3. 按钮区 (靠右排列)
        self.btn_mini_stop = ctk.CTkButton(self.mini_frame, text="⏸ 停止 (F8)", fg_color="#DA3633", hover_color="#B02A37", width=90, font=ctk.CTkFont(weight="bold"), command=self.stop_all)
        self.btn_mini_stop.pack(side="left", fill="y", padx=5, pady=10)

        self.btn_mini_support = ctk.CTkButton(self.mini_frame, text="❤ 支持", fg_color="#F97316", hover_color="#EA580C", width=60, font=ctk.CTkFont(weight="bold"), command=self.open_support_window)
        self.btn_mini_support.pack(side="left", fill="y", padx=(5, 10), pady=10)


        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent", height=200)
        self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))

        self.btn_stop = ctk.CTkButton(
            self.bottom_frame,
            text="⏸ 等待指令 (F8)",
            fg_color="#3A3A3A",
            hover_color="#4A4A4A",
            width=180,
            height=60,
            corner_radius=12,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.stop_all,
        )
        self.btn_stop.pack(side="left", padx=6)

        self.log_box = ctk.CTkTextbox(
            self.bottom_frame,
            state="disabled",
            wrap="word",
            corner_radius=12,
            height=120,
            font=ctk.CTkFont(size=18),
        )
        self.log_box.pack(side="left", fill="both", expand=True, padx=8)

        self.btn_support = ctk.CTkButton(
            self,
            text="❤ 支持作者 / 检查更新",
            fg_color="#F97316",
            hover_color="#EA580C",
            height=42,
            corner_radius=12,
            font=ctk.CTkFont(weight="bold", size=15),
            command=self.open_support_window,
        )
        self.btn_support.pack(fill="x", padx=18, pady=(6, 12))
        self.sync_buy_to_sell()
    def open_support_window(self):
        if self.support_win is not None and self.support_win.winfo_exists():
            self.support_win.focus()
            return

        self.support_win = ctk.CTkToplevel(self)
        self.support_win.title("感谢支持 & 更新")
        self.support_win.geometry("340x520")
        self.support_win.attributes("-topmost", True)
        self.support_win.resizable(False, False)

        try:
            icon_path = get_asset_path("icon.ico")
            if icon_path:
                self.support_win.iconbitmap(icon_path)
        except Exception:
            pass

        self.support_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 520) // 2
        self.support_win.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            self.support_win,
            text="感谢您的支持与鼓励",
            font=ctk.CTkFont(weight="bold", size=18),
            text_color="#F97316",
        ).pack(pady=(20, 6))

        ctk.CTkLabel(
            self.support_win,
            text="您的支持是我持续优化的动力！",
            font=ctk.CTkFont(size=12),
        ).pack(pady=4)

        qr_path = get_asset_path("qrcode.png")
        try:
            if qr_path and os.path.exists(qr_path):
                img = Image.open(qr_path)
                qr_img = ctk.CTkImage(light_image=img, size=(210, 210))
                qr_label = ctk.CTkLabel(self.support_win, text="", image=qr_img)
                qr_label.image = qr_img
                qr_label.pack(pady=10)
            else:
                ctk.CTkLabel(self.support_win, text="（未找到内置 qrcode.png）", text_color="gray").pack(pady=40)
        except Exception:
            ctk.CTkLabel(self.support_win, text="（二维码加载失败）", text_color="gray").pack(pady=40)

        ctk.CTkButton(
            self.support_win,
            text="前往 爱发电 赞助主页",
            fg_color="#8E44AD",
            hover_color="#7D3C98",
            command=lambda: webbrowser.open("https://ifdian.net/a/yousto"),
        ).pack(pady=5)

        ctk.CTkFrame(self.support_win, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=10)

        self.lbl_version = ctk.CTkLabel(
            self.support_win,
            text=f"当前版本: v{CURRENT_VERSION}",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_version.pack()

        def check_update_logic():
            self.ui_call(self.lbl_version.configure, text="正在连接 Github...", text_color="#3498DB")
            try:
                url = "https://raw.githubusercontent.com/YOUSTHEONE/FH6Auto/refs/heads/main/version.json"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    remote_ver = data.get("version", "0.0.0")
                    remote_url = data.get("url", "")

                    if parse_version(remote_ver) > parse_version(CURRENT_VERSION):
                        if remote_url.startswith("https://github.com/YOUSTHEONE/") or remote_url.startswith("https://ifdian.net/"):
                            self.ui_call(
                                self.lbl_version.configure,
                                text=f"发现新版本 v{remote_ver}，已打开浏览器！",
                                text_color="#2EA043",
                            )
                            webbrowser.open(remote_url)
                        else:
                            self.ui_call(
                                self.lbl_version.configure,
                                text="发现更新，但链接不可信，已拦截",
                                text_color="#DA3633",
                            )
                    else:
                        self.ui_call(
                            self.lbl_version.configure,
                            text=f"当前已是最新版本 (v{CURRENT_VERSION})",
                            text_color="gray",
                        )
                else:
                    self.ui_call(
                        self.lbl_version.configure,
                        text="检查更新失败 (服务器异常)",
                        text_color="#DA3633",
                    )
            except Exception:
                self.ui_call(
                    self.lbl_version.configure,
                    text="检查更新失败 (网络超时或无法访问)",
                    text_color="#DA3633",
                )

        btn_frame = ctk.CTkFrame(self.support_win, fg_color="transparent")
        btn_frame.pack(pady=6)

        ctk.CTkButton(
            btn_frame,
            text="检查更新",
            width=100,
            height=30,
            fg_color="#444444",
            hover_color="#555555",
            command=lambda: threading.Thread(target=check_update_logic, daemon=True).start(),
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="GitHub",
            width=100,
            height=30,
            fg_color="#2EA043",
            hover_color="#238636",
            command=lambda: webbrowser.open("https://github.com/YOUSTHEONE/FH6Auto"),
        ).pack(side="left", padx=5)
    def update_timer(self):
        if not self.is_running:
            return
        elapsed = int(time.time() - self.start_time)
        hrs = elapsed // 3600
        mins = (elapsed % 3600) // 60
        secs = elapsed % 60
        time_str = f"总耗时: {hrs:02d}:{mins:02d}:{secs:02d}"
        try:
            self.lbl_mini_time.configure(text=time_str)
        except Exception: pass
        
        if self.is_running:
            self.after(1000, self.update_timer)

    def update_running_ui(self, task_name="", current_val=0, max_val=0):
        try:
            if task_name:
                self.ui_call(self.lbl_mini_task.configure, text=f"当前任务: {task_name}")
            if max_val > 0:
                self.ui_call(self.lbl_mini_prog.configure, text=f"执行进度: {current_val} / {max_val}")
        except Exception:
            pass

    # ==========================================
    # --- 核心操作与流程控制 ---
    # ==========================================
    
    def game_click(self, pos, double=False):
        if not self.is_running or not pos:
            return
        x, y = int(pos[0]), int(pos[1])
        
        # 使用多屏兼容的硬件级移动
        input_driver.hw_mouse_move(x, y)
        time.sleep(0.2)
        for _ in range(2 if double else 1):
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.1)
        time.sleep(0.1)
        # 移开鼠标 10 像素，防止游戏里的悬浮提示框遮挡下一次截图
        try:
            gx, gy, gw, gh = self.regions["全界面"]
            # 移动到游戏左上角向内偏移 5 个像素，确保在游戏内但绝对不会挡住任何中间UI
            input_driver.hw_mouse_move(gx + 5, gy + 5)
        except Exception:
            # 兜底：如果获取不到窗口坐标，移到绝对屏幕左上角
            input_driver.hw_mouse_move(5, 5)
        time.sleep(0.2)

    def move_to_game_coord(self, x, y):
        """
        将鼠标移动到以【游戏窗口左上角】为起点的 (x, y) 坐标。
        例如传入 (5, 5)，就会移动到游戏内左上角 5 像素的安全位置。
        """
        try:
            gx, gy, gw, gh = self.regions["全界面"]
            abs_x = gx + x
            abs_y = gy + y
            input_driver.hw_mouse_move(abs_x, abs_y)
        except Exception:
            # 兜底：如果获取不到窗口坐标，就直接当绝对坐标移动
            input_driver.hw_mouse_move(x, y)
    
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
            if d == "up":
                curr_r -= 1
            elif d == "down":
                curr_r += 1
            elif d == "left":
                curr_c -= 1
            elif d == "right":
                curr_c += 1

            if 0 <= curr_r < 4 and 0 <= curr_c < 4:
                self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
                valid_dirs.append(d)
            else:
                break

        self.config["skill_dirs"] = valid_dirs

    def log(self, message):
        curr_time = time.strftime("%H:%M:%S")
        full_msg = f"[{curr_time}] {message}"

        def write_ui():
            try:
                # 写入下方大界面的日志
                self.log_box.configure(state="normal")
                self.log_box.insert("end", full_msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
                # 同时写入迷你界面的横向日志
                if hasattr(self, "mini_log_box"):
                    self.mini_log_box.configure(state="normal")
                    self.mini_log_box.insert("end", full_msg + "\n")
                    self.mini_log_box.see("end")
                    self.mini_log_box.configure(state="disabled")
            except Exception:
                pass
        self.ui_call(write_ui)
    def start_pipeline(self, start_step):
        if self.is_running:
            return

        self.is_running = True
        self.save_config()

        # 隐藏大窗的所有元素
        self.config_frame.pack_forget()
        self.global_settings_frame.pack_forget()
        self.calc_frame.pack_forget()
        self.top_container.pack_forget()
        if hasattr(self, "bottom_frame"):
            self.bottom_frame.pack_forget()
        self.btn_support.pack_forget()

        # 显示新的迷你横向 UI
        self.mini_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ====== 计算 15% 高度 40% 宽度 ======
        last_x, last_y, last_w, last_h = self.regions["全界面"]
        if last_w <= 0: last_w = self.winfo_screenwidth()
        if last_h <= 0: last_h = self.winfo_screenheight()

        calc_w = int(last_w * 0.40)
        calc_h = int(last_h * 0.15)
        # 设置一个兜底最小值，防止分辨率过低时文字挤压导致崩溃
        calc_w = max(calc_w, 650)
        calc_h = max(calc_h, 150)

        pos_x = last_x + last_w - calc_w - 20
        pos_y = last_y + 20

        self.attributes("-topmost", True)
        self.geometry(f"{calc_w}x{calc_h}+{pos_x}+{pos_y}")
        
        # 启动计时器
        self.start_time = time.time()
        self.update_timer()

        
        self.update_running_ui("初始化中...")
        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.sc_count = 0
        self.global_loop_current = 0

        def runner():
            if not self.check_and_focus_game():
                self.stop_all()
                return

            steps = ["race", "buy", "cj", "sell"]
            curr_idx = steps.index(start_step)

            try:
                total_loops = int(self.entry_global_loop.get())
            except Exception:
                total_loops = self.config.get("global_loops", 10)
            self.global_loop_current = 1
            if hasattr(self, "lbl_mini_loop"):
                self.ui_call(self.lbl_mini_loop.configure, text=f"大循环: {self.global_loop_current} / {total_loops}")
            while self.is_running:
                step_name = steps[curr_idx]
                success = False

                try:
                    if step_name == "race":
                        success = logic.race.run_race(self, int(self.entry_race.get()), self.entry_share.get())
                    elif step_name == "buy":
                        success = logic.buy.run_buy(self, int(self.entry_car.get()))
                    elif step_name == "cj":
                        success = logic.wheelspin.run_wheelspin(self, int(self.entry_cj.get()))
                    elif step_name == "sell":
                        success = logic.sell.run_sell(self, int(self.entry_sc.get()))
                except Exception as e:
                    self.log(f"执行模块 {step_name} 时异常: {e}")
                    success = False

                if not self.is_running:
                    break

                if not success:
                    if self.attempt_recovery():
                        continue
                    else:
                        self.log("致命错误：断点恢复失败，彻底停止。")
                        break
                #v1.0.1
                # ====== 核心流转与无限循环逻辑 ======
                next_idx = curr_idx + 1 # 默认前往下一步
                if curr_idx == 0:
                    if self.var_chk1.get():
                        try: next_idx = max(0, min(3, int(self.entry_next1.get()) - 1))
                        except Exception: next_idx = 1
                    else: break
                elif curr_idx == 1:
                    if self.var_chk2.get():
                        try: next_idx = max(0, min(3, int(self.entry_next2.get()) - 1))
                        except Exception: next_idx = 2
                    else: break
                elif curr_idx == 2:
                    if self.var_chk3.get():
                        try: next_idx = max(0, min(3, int(self.entry_next3.get()) - 1))
                        except Exception: next_idx = 3
                    else: break
                elif curr_idx == 3:
                    if self.var_chk4.get():
                        try: next_idx = max(0, min(3, int(self.entry_next4.get()) - 1))
                        except Exception: next_idx = 0
                    else: break

                if next_idx <= curr_idx:
                    self.global_loop_current += 1
                    
                    if self.global_loop_current > total_loops:
                        self.log("达到设定的总循环次数，任务圆满结束。")
                        break
                        
                    self.log(f"开启新一轮大循环 ({self.global_loop_current}/{total_loops})")
                    
                    if hasattr(self, "lbl_mini_loop"):
                        self.ui_call(self.lbl_mini_loop.configure, text=f"大循环: {self.global_loop_current} / {total_loops}")

                    self.race_counter = 0
                    self.car_counter = 0
                    self.cj_counter = 0
                    self.sc_count = 0
                
                curr_idx = next_idx

            self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()

    def stop_all(self):
        if not self.is_running:
            return

        self.is_running = False

        for key in input_driver.DIK_CODES.keys():
            input_driver.hw_key_up(key)

        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            input_driver.hw_key_up(key)

        try:
            pydirectinput.mouseUp()
        except Exception:
            pass

        def restore_ui():
            if hasattr(self, "mini_frame"):
                self.mini_frame.pack_forget()
                
            # 【核心修复】：先让大容器里的东西全部解绑，洗牌重来
            self.config_frame.pack_forget()
            self.global_settings_frame.pack_forget()
            self.calc_frame.pack_forget()
            
            # 1. 铺设最外层大容器
            self.top_container.pack(fill="x", padx=18, pady=(18, 10))
            
            # 2. 依次按顺序塞入三个模块，完美保证从上到下的顺序！
            self.config_frame.pack(fill="x")
            self.global_settings_frame.pack(fill="x", pady=(15, 0))
            self.calc_frame.pack(fill="x", pady=(10, 0))
            
            # 3. 铺设底部的日志和按钮
            if hasattr(self, "bottom_frame"):
                self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))
            self.btn_support.pack(fill="x", padx=18, pady=(6, 12))
            
            # 恢复窗口原本的状态
            self.btn_stop.configure(text="等待指令 (F8)", fg_color="#3A3A3A", hover_color="#4A4A4A")
            self.attributes("-topmost", False)
            self.geometry("1800x800")
            self.center_window()

        self.ui_call(restore_ui)
        self.log("!!! 任务已停止，所有物理按键状态已强制重置")

    def start_hotkey_listener(self):
        def hotkey_thread():
            def on_press(k):
                if k == keyboard.Key.f8:
                    self.stop_all()

            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()

        threading.Thread(target=hotkey_thread, daemon=True).start()

   
    # ==========================================
    # --- 逻辑保障 ---
    # ==========================================
    # 【新增】：强制切换英文键盘与关闭中文状态
    def set_english_input(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return
            # 策略1：尝试切美式键盘
            hkl = ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 1)
            ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, hkl) 
            # 策略2：底层强制关闭当前中文输入法的中文状态(绝杀)
            WM_IME_CONTROL = 0x0283
            IMC_SETOPENSTATUS = 0x0006
            ctypes.windll.user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)
            
            self.log("已自动切换英文键盘/关闭中文输入法状态。")
        except Exception as e:
            self.log(f"自动防中文输入设置失败: {e}")
    def check_and_focus_game(self):
        self.log("检查游戏进程 (forzahorizon6.exe)...")
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = 'tasklist /FI "IMAGENAME eq forzahorizon6.exe" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)

            if "forzahorizon6.exe" not in output.lower():
                self.log("未发现 forzahorizon6.exe 进程！(请确保游戏已运行)")
                return False

            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and "forzahorizon6.exe" in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break

            if not target_pid:
                self.log("找到进程但无法解析PID！")
                return False

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
                # ====== 【新增】：强制关闭中文输入法 ======
                self.set_english_input()
                # ==========================================
                try:
                    client_rect = win32gui.GetClientRect(hwnd)
                    pt = win32gui.ClientToScreen(hwnd, (0, 0))
                    x, y = pt[0], pt[1]
                    w, h = client_rect[2], client_rect[3]
                    self.update_regions_by_window(x, y, w, h)
                    # ====== 【新增】：小窗口精准吸附游戏所在屏幕的右上角 ======
                    def snap_to_game():
                        if self.is_running:
                            calc_w = int(w * 0.40)
                            calc_h = int(h * 0.15)
                            calc_w = max(calc_w, 650)
                            calc_h = max(calc_h, 150)
                            pos_x = x + w - calc_w - 20
                            pos_y = y + 20
                            self.geometry(f"{calc_w}x{calc_h}+{pos_x}+{pos_y}")
                    self.ui_call(snap_to_game)
                    # ==========================================
                except Exception as e:
                    self.log(f"获取窗口坐标失败: {e}")

                time.sleep(1.0)
                return True

        except Exception as e:
            self.log(f"检查进程异常: {e}")
            return False

        return False

    def restart_game_and_boot(self):
        auto_restart = getattr(self, "var_auto_restart", None)
        if auto_restart is None or not auto_restart.get():
            self.log("未开启自动重启，任务结束。")
            return False

        self.log("触发自动重启机制！正在拉起游戏...")
        try:
            cmd_widget = getattr(self, "le_restart_cmd", None)
            cmd_str = cmd_widget.get() if cmd_widget else self.config.get("restart_cmd", "start steam://run/2483190")
            os.system(cmd_str)
        except Exception as e:
            self.log(f"执行重启命令失败: {e}")
            return False

        self.log("等待游戏启动加载 (10秒)...")
        for _ in range(10):
            if not self.is_running:
                return False
            time.sleep(1)

        self.log("开始持续检测开机界面元素 (限制5分钟)...")
        for _ in range(300):
            if not self.is_running:
                return False

            if self.vision.find_image("horizon6.png", threshold=0.6):
                self.log("识别到欢迎界面，按下回车。")
                input_driver.hw_press("enter")
                time.sleep(4)
                continue

            pos_con = self.vision.find_any_image(["continue-w.png", "continue-b.png"], threshold=0.6)
            if pos_con:
                self.log("识别到继续游戏，点击进入！")
                self.game_click(pos_con)
                time.sleep(10)
                self.log("尝试按 ESC 唤出菜单...")
                input_driver.hw_press("esc")
                time.sleep(2)
                if self.enter_menu():
                    self.log("成功重连并进入菜单，准备恢复执行！")
                    return True
                return False

            time.sleep(2.0)

        self.log("自动重启超时(2分钟未进入漫游)，放弃抢救。")
        return False

    def recover_to_freeroam(self):
        self.log("尝试退回漫游重置状态...")
        for _ in range(30):
            if not self.is_running:
                return False

            if self.vision.find_image("anna.png", region=self.regions["全界面"], threshold=0.5):
                self.log("成功退回漫游界面！")
                return True

            input_driver.hw_press("esc")
            time.sleep(2.0)

        return self.wait_for_freeroam()

    def recover_to_menu(self):
        self.log("尝试退回主菜单重置状态...")
        for _ in range(120):
            if not self.is_running:
                return False

            if self.vision.find_image("collectionjournal.png", region=self.regions["全界面"], threshold=0.55):
                self.log("成功退回主菜单界面！")
                return True

            pos_exit = self.vision.find_any_image(["exit.png", "exit-b.png"], region=self.regions["左下"], threshold=0.85)
            if pos_exit:
                self.log("识别到退出按钮，点击...")
                self.game_click(pos_exit)
                time.sleep(1.5)
                continue

            input_driver.hw_press("esc")
            time.sleep(0.5)

        self.log("多次尝试仍未退回主菜单。")
        return False

    def attempt_recovery(self):
        self.log("任务执行异常中断，准备执行断点恢复流程...")
        if not self.check_and_focus_game():
            if not self.restart_game_and_boot():
                return False
        else:
            if not self.recover_to_menu():
                return False

        self.log("环境重置成功！即将从中断处继续剩余任务。")
        return True

    def wait_for_freeroam(self):
        self.log("验证漫游状态...")
        for i in range(100):
            if not self.is_running:
                return False

            if self.vision.find_image("anna.png", region=self.regions["全界面"], threshold=0.5):
                self.log("验证成功：已确认处于游戏漫游界面。")
                return True

            self.log(f"重试返回漫游界面({i + 1}/100)")
            input_driver.hw_press("esc")

            for _ in range(20):
                if not self.is_running:
                    return False
                time.sleep(0.1)

        self.log("多次尝试验证漫游界面失败，尝试进入菜单。")
        return True

    def is_in_menu(self):
        return self.vision.find_any_image(
            ["collectionjournal.png", "nextstep.png"],
            region=self.regions["全界面"],
            threshold=0.55,
            fast_mode=True
        )

    def enter_menu(self):
        self.log("正在搜索菜单锚点...")
        menu_anchors = ["collectionjournal.png", "nextstep.png"]

        for i in range(100):
            if not self.is_running:
                return False

            pos = self.vision.wait_for_any_image(
                menu_anchors,
                region=self.regions["全界面"],
                threshold=0.55,
                timeout=0.8,
                interval=0.15,
                fast_mode=True
            )
            if pos:
                self.log(f"成功进入菜单页面！({i + 1}/100)")
                time.sleep(0.4)
                return True

            self.log(f"未识别到菜单锚点，正在重试 ({i + 1}/100)")
            input_driver.hw_press("esc")
            time.sleep(0.6)

        self.log("100 次尝试进入菜单均失败。")
        return False