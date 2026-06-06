import time
from core.image_utils import find_with_roi_features

class VehicleSelectorMixin:
    """
    车辆选择通用逻辑混入类 (Mixin)
    提供标准的找品牌、翻页、找车逻辑。
    """
    def state_start_brand_search(self):
        if not getattr(self, "action_executed", False):
            self.ctx.interaction.press_key("backspace")
            self.action_executed = True
        if self.wait_in_state(1.0):
            self.change_state("find_brand")

    def state_find_brand(self):
        brand_img = self.get_asset("brand_img", is_global=True)
        pos = self.ctx.find_image(brand_img)
        
        if pos:
            if not getattr(self, "action_executed", False):
                self.ctx.log("✅ 找到指定品牌！点击进入...")
                self.ctx.interaction.game_click(pos)
                self.action_executed = True
            if self.wait_in_state(1.0):
                self.change_state("car_select_scroll")
        else:
            if self.time_in_state > 0.2 and not getattr(self, "action_executed", False):
                self.log_throttled("未看到指定品牌，向上滚动...")
                self.ctx.interaction.press_key("up")
                self.state_start_time = time.monotonic() 

    def state_car_select_scroll(self):
        # 1. 边界拦截
        title_img = self.get_asset("title_img", is_global=True)
        if not self.ctx.find_image(title_img):
            self.ctx.log("🚨 已经滑出指定品牌范围，当前品牌下已无目标车辆。")
            self.on_no_more_vehicles()
            return None

        # 2. 状态隔离墙 (点过之后绝对不扫图，等待流转)
        if getattr(self, "action_executed", False):
            if time.monotonic() - getattr(self, "last_action_time", 0) > 0.5:
                self.on_vehicle_selected()
            return None 

        # 3. 高阶特征寻车与滚动逻辑
        anchor_img = self.get_asset("anchor_img")
        features = self.get_features()

        scan_mode = getattr(self, "scan_mode", "fast")
        pos = find_with_roi_features(
            self.ctx, 
            anchor_image=anchor_img, 
            features=features, 
            anchor_threshold=0.9, 
            feature_threshold=0.9, 
            padding=5,
            scan_mode=scan_mode
            )

        if pos:
            self.scroll_active = False
            self.ctx.log("🎯 成功找到目标车辆，点击选中！")
            self.ctx.interaction.game_click(pos)
            self.action_executed = True
            self.last_action_time = time.monotonic()
        else:
            if not getattr(self, "scroll_active", False):
                self.scroll_count = 0
                self.last_scroll_time = time.monotonic()
                self.scroll_active = True
            
            now = time.monotonic()
            if self.scroll_count < 4:
                if now - self.last_scroll_time > 0.1:
                    self.ctx.interaction.press_key("right")
                    self.scroll_count += 1
                    self.last_scroll_time = now
                    self.log_throttled("未看到符合要求的车辆，向右滚动...")
            else:
                if now - self.last_scroll_time > 0.5:
                    self.scroll_active = False 
                    
    # ==================================================
    # --- 抽象钩子方法 (Hooks) ---
    # 不同的任务（买、跑、移除、熟练度），在选完车之后的流转是不一样的。
    # 必须由子类自己实现以下两个方法来决定去向。
    # ==================================================
    def on_vehicle_selected(self):
        raise NotImplementedError("子类必须实现 on_vehicle_selected 方法！")
        
    def on_no_more_vehicles(self):
        raise NotImplementedError("子类必须实现 on_no_more_vehicles 方法！")