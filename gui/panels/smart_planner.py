import customtkinter as ctk

class SmartPlannerPanel(ctk.CTkFrame):
    """
    智能资产规划与托管面板。
    负责处理 SP/CR 的感知展示、自定义参数以及自动计算流水线配比。
    """
    def __init__(self, master, config_mgr, on_sync_callback):
        super().__init__(master, fg_color="#2B2B2B", corner_radius=10)
        self.config_mgr = config_mgr
        self.on_sync_callback = on_sync_callback # 当计算出新配比时，回调给主窗口更新 UI
        
        self.pack_propagate(False)
        self.setup_ui()
        self.load_initial_values()

    def setup_ui(self):
        # --- 顶部：标题与资产感知 ---
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(top_frame, text="🧠 智能资产规划", font=ctk.CTkFont(weight="bold", size=16), text_color="#F39C12").pack(side="left")
        
        self.lbl_asset_status = ctk.CTkLabel(top_frame, text="资产感知: SP [尚未检测]", font=ctk.CTkFont(size=13), text_color="#A0A0A0")
        self.lbl_asset_status.pack(side="right")

        # --- 中部：策略配置 ---
        config_frame = ctk.CTkFrame(self, fg_color="transparent")
        config_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        # 目标技能点设定
        ctk.CTkLabel(config_frame, text="目标技能点:").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_target_sp = ctk.CTkEntry(config_frame, width=70, height=28)
        self.entry_target_sp.grid(row=0, column=1, padx=10, pady=5)
        
        # 成本设定 (支持用户修改)
        ctk.CTkLabel(config_frame, text="单车成本(CR):").grid(row=0, column=2, sticky="w", pady=5, padx=(10, 0))
        self.entry_cost_cr = ctk.CTkEntry(config_frame, width=80, height=28)
        self.entry_cost_cr.grid(row=0, column=3, padx=10, pady=5)
        
        ctk.CTkLabel(config_frame, text="单车消耗(SP):").grid(row=0, column=4, sticky="w", pady=5, padx=(10, 0))
        self.entry_cost_sp = ctk.CTkEntry(config_frame, width=60, height=28)
        self.entry_cost_sp.grid(row=0, column=5, padx=10, pady=5)

        # 按钮区
        btn_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=6, padx=10, pady=5)
        
        ctk.CTkButton(btn_frame, text="计算配比", width=80, height=28, fg_color="#D35400", hover_color="#A04000", command=self.calculate_plan).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="恢复默认", width=80, height=28, fg_color="#7F8C8D", hover_color="#95A5A6", command=self.reset_defaults).pack(side="left", padx=5)

        # --- 底部：输出与托管 ---
        bottom_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=8)
        bottom_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        self.lbl_plan_result = ctk.CTkLabel(bottom_frame, text="等待计算...", font=ctk.CTkFont(size=14))
        self.lbl_plan_result.pack(side="left", padx=15, pady=10)
        
        self.var_auto_sync = ctk.BooleanVar(value=True)
        self.chk_auto_sync = ctk.CTkCheckBox(bottom_frame, text="同步至执行配置", variable=self.var_auto_sync)
        self.chk_auto_sync.pack(side="right", padx=15, pady=10)
        
        # 绑定实时限制
        self.entry_target_sp.bind("<KeyRelease>", lambda e: self.limit_number(self.entry_target_sp, 999))
        self.entry_cost_cr.bind("<KeyRelease>", lambda e: self.limit_number(self.entry_cost_cr, 9999999))
        self.entry_cost_sp.bind("<KeyRelease>", lambda e: self.limit_number(self.entry_cost_sp, 999))

    def limit_number(self, widget, max_val):
        val = "".join(c for c in widget.get() if c.isdigit())
        if val:
            if int(val) > max_val:
                val = str(max_val)
        if widget.get() != val:
            widget.delete(0, "end")
            widget.insert(0, val)

    def load_initial_values(self):
        """从 ProfileManager 加载默认值 (基于当前选择的车辆)"""
        from core.profile_manager import ProfileManager
        target_vid = self.config_mgr.config.get("target_vehicle")
        
        cost_cr = ProfileManager().get_cost_cr(target_vid)
        cost_sp = ProfileManager().get_skill_sp(target_vid)
        
        self.entry_cost_cr.delete(0, "end")
        self.entry_cost_cr.insert(0, str(cost_cr))
        
        self.entry_cost_sp.delete(0, "end")
        self.entry_cost_sp.insert(0, str(cost_sp))
        
        self.entry_target_sp.delete(0, "end")
        self.entry_target_sp.insert(0, "990") # 默认目标

    def reset_defaults(self):
        """用户点击重置按钮时触发"""
        self.load_initial_values()
        self.lbl_plan_result.configure(text="已恢复默认参数。")

    def update_asset_status(self, current_sp):
        """提供给外部系统调用的接口，用于更新面板上的资产感知状态"""
        if current_sp >= 0:
            self.lbl_asset_status.configure(text=f"资产感知: SP [{current_sp}]", text_color="#2EA043")
        else:
            self.lbl_asset_status.configure(text="资产感知: SP [读取失败]", text_color="#E74C3C")

    def calculate_plan(self):
        """核心计算逻辑"""
        try:
            target_sp = int(self.entry_target_sp.get())
            cost_sp = int(self.entry_cost_sp.get())
        except ValueError:
            self.lbl_plan_result.configure(text="请输入有效的数字！")
            return
            
        if cost_sp <= 0:
            self.lbl_plan_result.configure(text="单车消耗 SP 必须大于 0！")
            return

        # 计算理论需要加点的车辆数
        cars_needed = target_sp // cost_sp
        
        # 因为每跑一局固定获得 10 SP，所以跑图次数 = 目标SP / 10
        races_needed = (cars_needed * cost_sp) // 10
        
        # 买车和删车数量与加点车数量保持一致
        buy_needed = cars_needed
        remove_needed = cars_needed
        
        result_text = f"推荐配比: 跑图 {races_needed} 次 | 买车 {buy_needed} 台 | 加点 {cars_needed} 台 | 移除 {remove_needed} 台"
        self.lbl_plan_result.configure(text=result_text)
        
        # 如果勾选了同步，触发回调更新主界面的输入框和配置
        if self.var_auto_sync.get() and self.on_sync_callback:
            self.on_sync_callback(races_needed, buy_needed, cars_needed, remove_needed)