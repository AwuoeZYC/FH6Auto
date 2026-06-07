import customtkinter as ctk

class TaskConfigPanel(ctk.CTkFrame):
    """
    四大核心任务配置面板。
    接管跑图、买车、熟练度矩阵、卖车模块的所有 UI 渲染与双向绑定。
    """
    def __init__(self, master, config_mgr, on_start_callback):
        super().__init__(master, fg_color="transparent")
        self.config_mgr = config_mgr
        self.config = config_mgr.config
        self.on_start_callback = on_start_callback

        self.grid_labels = [[None] * 4 for _ in range(4)]
        self.setup_ui()
        self.update_skill_grid()

    def on_entry_change(self, event, entry_widget, label_widget, config_key, max_len=4):
        """输入框防抖与双向绑定"""
        val = "".join(c for c in entry_widget.get() if c.isdigit())
        if len(val) > max_len: 
            val = val[:max_len]
            
        if entry_widget.get() != val:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, val)
            
        display_val = val if val else "0"
        
        # 处理无限模式的特殊显示
        if config_key == "remove_count" and display_val == "9999":
            label_widget.configure(text="执行: 0 / 无限")
        else:
            label_widget.configure(text=f"执行: 0 / {display_val}")
        
        try:
            self.config[config_key] = int(display_val)
            self.config_mgr.save()
        except ValueError:
            pass

    def normalize_step_entry(self, entry_widget, default_value):
        try:
            v = "".join(c for c in entry_widget.get() if c.isdigit())
            if not v: v = str(default_value)
            iv = max(1, min(int(v), 4))
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(iv))
        except Exception:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(default_value))

    def setup_ui(self):
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

        self.var_chk1 = ctk.BooleanVar(value=self.config.get("chk_1", True))
        self.var_chk2 = ctk.BooleanVar(value=self.config.get("chk_2", True))
        self.var_chk3 = ctk.BooleanVar(value=self.config.get("chk_3", True))
        self.var_chk4 = ctk.BooleanVar(value=self.config.get("chk_4", True))

        # 1: 跑图
        box_race, _, self.entry_race, self.lbl_race = create_box(
            self, "1. 循环跑图", "开始", lambda: self.on_start_callback("race"), "#1F6AA5", self.config.get("race_count", 99), "race_count"
        )
        self.entry_share = ctk.CTkEntry(box_race, width=130, justify="center", placeholder_text="蓝图数字代码")
        self.entry_share.insert(0, self.config.get("share_code", "890169683"))
        self.entry_share.pack(pady=4)
        self.next_frame1, self.entry_next1, _ = create_next_step(self, self.var_chk1, self.config.get("next_1", 2))

        # 2: 买车
        _, _, self.entry_car, self.lbl_car = create_box(
            self, "2. 批量买车", "开始", lambda: self.on_start_callback("buy"), "#2EA043", self.config.get("buy_count", 33), "buy_count"
        )
        self.next_frame2, self.entry_next2, _ = create_next_step(self, self.var_chk2, self.config.get("next_2", 3))

        # 3: 熟练度加点
        self._build_mastery_box()
        self.next_frame3, self.entry_next3, _ = create_next_step(self, self.var_chk3, self.config.get("next_3", 4))

        # 4: 移除车辆
        box_sc, _, self.entry_sc, self.lbl_sc = create_box(
            self, "4. 移除车辆", "！！开始！！", lambda: self.on_start_callback("remove"), "#D97706", self.config.get("remove_count", 33), "remove_count"
        )
        
        # 【新增】：无限移除选项
        self.var_infinite_remove = ctk.BooleanVar(value=(self.config.get("remove_count", 33) == 9999))
        self.chk_infinite = ctk.CTkCheckBox(box_sc, text="无限模式", variable=self.var_infinite_remove, command=self._toggle_infinite_remove)
        self.chk_infinite.pack(pady=4)
        
        # 初始化界面状态
        if self.var_infinite_remove.get():
            self._toggle_infinite_remove()

        self.next_frame4, self.entry_next4, _ = create_next_step(self, self.var_chk4, self.config.get("next_4", 1))
        
        self.entry_next1.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next1, 2))
        self.entry_next2.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next2, 3))
        self.entry_next3.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next3, 4))
        self.entry_next4.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next4, 1))

    def _toggle_infinite_remove(self):
        """无限卖车模式切换逻辑 (底层认定 9999 即为无限)"""
        if self.var_infinite_remove.get():
            self.entry_sc.delete(0, "end")
            self.entry_sc.insert(0, "9999")
            self.entry_sc.configure(state="disabled")
        else:
            self.entry_sc.configure(state="normal")
            self.entry_sc.delete(0, "end")
            self.entry_sc.insert(0, "33")
            
        # 手动触发一次变更，同步到底层配置和 Label
        self.on_entry_change(None, self.entry_sc, self.lbl_sc, "remove_count")

    def _build_mastery_box(self):
        self.box_mastery = ctk.CTkFrame(self, width=360, height=300, corner_radius=12, border_width=1, border_color="#2B2B2B")
        self.box_mastery.pack_propagate(False)
        self.box_mastery.pack(side="left", padx=8)

        top_mastery = ctk.CTkFrame(self.box_mastery, fg_color="transparent")
        top_mastery.pack(fill="x", pady=10)

        left_mastery = ctk.CTkFrame(top_mastery, fg_color="transparent")
        left_mastery.pack(side="left", padx=10)

        ctk.CTkLabel(left_mastery, text="3. 熟练度加点", font=ctk.CTkFont(weight="bold", size=20)).pack(pady=(0, 8))
        ctk.CTkButton(left_mastery, text="开始", width=120, height=38, corner_radius=10, fg_color="#8E44AD", hover_color="#8E44AD", command=lambda: self.on_start_callback("mastery")).pack(pady=5)

        self.entry_mastery = ctk.CTkEntry(left_mastery, width=95, height=34, justify="center", corner_radius=8)
        self.entry_mastery.insert(0, str(self.config.get("mastery_count", 33)))
        self.entry_mastery.pack(pady=5)

        self.lbl_mastery = ctk.CTkLabel(left_mastery, text=f"执行: 0 / {self.config.get('mastery_count', 33)}", text_color="#A0A0A0", font=ctk.CTkFont(size=14))
        self.lbl_mastery.pack(pady=(2, 8))
        self.entry_mastery.bind("<KeyRelease>", lambda e: self.on_entry_change(e, self.entry_mastery, self.lbl_mastery, "mastery_count"))

        dir_frame = ctk.CTkFrame(left_mastery, fg_color="transparent")
        dir_frame.pack(pady=4)
        for text, val in [("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right")]:
            ctk.CTkButton(dir_frame, text=text, width=30, height=28, corner_radius=8, command=lambda x=val: self.add_skill_dir(x)).pack(side="left", padx=2)
        ctk.CTkButton(left_mastery, text="清除矩阵", width=90, height=28, corner_radius=8, fg_color="#C0392B", hover_color="#A93226", command=self.clear_skill_dir).pack(pady=8)

        self.grid_frame = ctk.CTkFrame(top_mastery, fg_color="transparent")
        self.grid_frame.pack(side="right", padx=12)
        for r in range(4):
            for c in range(4):
                lbl = ctk.CTkLabel(self.grid_frame, text="", width=28, height=28, corner_radius=5, fg_color="#444444")
                lbl.grid(row=r, column=c, padx=4, pady=4)
                self.grid_labels[r][c] = lbl
        ctk.CTkLabel(self.grid_frame, text="技能树", font=ctk.CTkFont(size=14, weight="bold"), text_color="#A0A0A0").grid(row=4, column=0, columnspan=4, pady=(8, 0))

    def add_skill_dir(self, direction):
        self.config["skill_dirs"].append(direction)
        self.update_skill_grid()
        self.config_mgr.save()

    def clear_skill_dir(self):
        self.config["skill_dirs"].clear()
        self.update_skill_grid()
        self.config_mgr.save()

    def update_skill_grid(self):
        for r in range(4):
            for c in range(4):
                self.grid_labels[r][c].configure(fg_color="#333333")

        curr_r, curr_c = 3, 0
        self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
        valid_dirs = []

        for d in self.config.get("skill_dirs", []):
            if d == "up": curr_r -= 1
            elif d == "down": curr_r += 1
            elif d == "left": curr_c -= 1
            elif d == "right": curr_c += 1

            if 0 <= curr_r < 4 and 0 <= curr_c < 4:
                self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
                valid_dirs.append(d)
            else: break
        self.config["skill_dirs"] = valid_dirs

    def sync_values(self, races, buys, masteries, removes):
        """提供给外部智能计算器调用的同步接口"""
        self.entry_race.delete(0, "end"); self.entry_race.insert(0, str(races))
        self.on_entry_change(None, self.entry_race, self.lbl_race, "race_count")
        
        self.entry_car.delete(0, "end"); self.entry_car.insert(0, str(buys))
        self.on_entry_change(None, self.entry_car, self.lbl_car, "buy_count")
        
        self.entry_mastery.delete(0, "end"); self.entry_mastery.insert(0, str(masteries))
        self.on_entry_change(None, self.entry_mastery, self.lbl_mastery, "mastery_count")
        
        # 如果当前是无限模式，要先解开锁定才能覆写数字
        self.var_infinite_remove.set(False)
        self.entry_sc.configure(state="normal")
        self.entry_sc.delete(0, "end"); self.entry_sc.insert(0, str(removes))
        self.on_entry_change(None, self.entry_sc, self.lbl_sc, "remove_count")
        
    def save_current_values(self):
        """将内部流转组件的最终状态刷入 config字典"""
        self.config["chk_1"] = self.var_chk1.get()
        self.config["chk_2"] = self.var_chk2.get()
        self.config["chk_3"] = self.var_chk3.get()
        self.config["chk_4"] = self.var_chk4.get()
        self.config["share_code"] = "".join(c for c in self.entry_share.get() if c.isdigit())
        self.config["next_1"] = int(self.entry_next1.get())
        self.config["next_2"] = int(self.entry_next2.get())
        self.config["next_3"] = int(self.entry_next3.get())
        self.config["next_4"] = int(self.entry_next4.get())
        self.config_mgr.save()