import time
from logic.base_task import BaseTask
from core.image_utils import calculate_dynamic_roi, find_with_roi_features

class CarMasteryTask(BaseTask):
    """
    全自动车辆熟练度加点任务 (全非阻塞状态机版)
    负责从车库中找出未驾驶过的新车，上车后进入升级与调校，按配置路径加点。
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.task_id = "mastery"
        self.state_timeout = 120  # 加点流程涉及动画等待较多，放宽熔断限制
        self.skill_dirs = self.ctx.config.get("skill_dirs", [])
        
        # 追踪微循环与防抖延时
        self.scroll_count = 0
        self.last_action_time = 0.0
        
        self.skill_idx = 0
        self.skill_step = 0
        self.exit_clicks = 0

    # ================= 1. 导航与进入车库 =================
    def state_init(self):
        if self.current_count == 0 and self.time_in_state < 0.5: return None
        
        scene = self.ctx.navigator.identify_scene()
        if scene == "scene_unknown":
            scene = self.ctx.navigator.recover_to_safe_state()
            if not scene: return False
            self.state_start_time = time.monotonic()
        
        self.ctx.log(f"🚩 起点定位成功: {scene}")
        self.ctx.log("🚩 开始导航至 [车辆]...")
        self.change_state("navigating_to_hub")

    def state_navigating_to_hub(self):
        if not self.action_executed:
            curr = self.ctx.navigator.identify_scene()
            self.ctx.router.start_navigation(curr, "scene_hub_cars")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 到达车库大本营，准备选择车辆...")
            self.change_state("enter_my_cars")
        elif status == "FAILED":
            return False

    def state_enter_my_cars(self):
        pos = self.ctx.find_any_image(["opt_my_cars_normal.png", "opt_my_cars_selected.png"], threshold=0.75)
        if pos:
            if not self.action_executed:
                self.ctx.log("点击进入 [我的车辆]...")
                self.ctx.interaction.game_click(pos)
                self.action_executed = True
                self.change_state("start_brand_search")
        else:
            self.log_throttled("⏳ 等待 [我的车辆] 选项...")

    # ================= 2. 寻车与上车 =================
    def state_start_brand_search(self):
        # 保证单次进入状态只按一次键
        if not self.action_executed:
            self.log_throttled("按 Backspace 展开制造商列表...")
            self.ctx.interaction.press_key("backspace")
            self.action_executed = True

        # 非阻塞等待 1 秒后流转状态
        if self.wait_in_state(1.0):
            self.change_state("find_brand")

    def state_find_brand(self):
        brand_img = self.get_asset("brand_img", is_global=True)
        pos = self.ctx.find_image(brand_img)
        if pos:
            if not self.action_executed:
                self.ctx.log("✅ 找到指定品牌！点击进入...")
                self.ctx.interaction.game_click(pos)
                self.action_executed = True
                
            if self.wait_in_state(1.0):
                self.change_state("car_select_scroll")
        else:
            # 配合 log_throttled，即便主循环 0.05s 一次，日志和按键也能被规范限流
            if self.time_in_state > 0.2 and not self.action_executed:
                self.log_throttled("未看到指定品牌，向上滚动...")
                self.ctx.interaction.press_key("up")
                # 这里不使用 change_state，而是手动重置计时器，让循环重新判定 0.2s 延时
                self.state_start_time = time.monotonic() 

    def state_car_select_scroll(self):
        title_img = self.get_asset("title_img", is_global=True)
        anchor_img = self.get_asset("anchor_img")
        features = self.get_features()
        # 1. 边界检测：滑出品牌范围，说明车库里没新车了
        if not self.ctx.find_image(title_img):
            self.ctx.log("🚨 已经滑出指定品牌范围，未能找到全新指定车辆，任务结束！")
            return True 
        
        # 2. 多点遍历防漏检引擎
        pos = find_with_roi_features(self.ctx, anchor_image=anchor_img, features=features, padding=20)

        # ==========================================
        # 3. 状态分支隔离处理
        # ==========================================
        if pos:
            # 状态清洗：如果上一帧还在滚动，这一帧突然找到车了，必须复位执行锁！
            if getattr(self, "is_scrolling", False):
                self.action_executed = False
                self.is_scrolling = False

            # 分支 A：点击逻辑
            if not self.action_executed:
                self.ctx.log("🎯 成功在列表中找到全新指定车辆！")
                self.ctx.interaction.game_click(pos)
                self.action_executed = True
                self.last_action_time = time.monotonic()
            
            # 分支 B：非阻塞延时流转逻辑（独立在外部，不受 if not 限制）
            elif time.monotonic() - self.last_action_time > 0.5:
                self.change_state("get_in_car")
                
        else:
            # 状态声明：当前进入滚动分支
            self.is_scrolling = True
            
            # 滚动参数初始化
            if not self.action_executed:
                self.scroll_count = 0
                self.last_scroll_time = time.monotonic()
                self.action_executed = True 
            
            # 滚动的 Tick 微循环
            now = time.monotonic()
            if self.scroll_count < 4:
                if now - self.last_scroll_time > 0.1:
                    # 注意：必须使用封装过的 press_key 以支持全局 F8 熔断
                    self.ctx.interaction.press_key("right") 
                    self.scroll_count += 1
                    self.last_scroll_time = now
                    self.log_throttled("未看到全新指定车辆，向右滚动...")
            else:
                if now - self.last_scroll_time > 0.5:
                    # 滚动四轮完毕，彻底复位所有标志位，下一帧重新拍照扫描
                    self.action_executed = False
                    self.is_scrolling = False

    def state_get_in_car(self):
        pos = self.ctx.find_any_image(["opt_get_in_normal.png", "opt_get_in_selected.png"])
        if pos:
            self.ctx.log("找到上车选项，点击上车...")
            self.ctx.interaction.game_click(pos)
            self.last_action_time = time.monotonic()
            self.change_state("wait_and_back_to_hub")
        elif self.time_in_state > 2.0:
            if not self.action_executed:
                # self.ctx.log("未看到上车选项，尝试补按回车唤出菜单...")
                self.ctx.interaction.press_key("enter")
                self.action_executed = True
                self.last_action_time = time.monotonic()
                
            # 如果补按后依然未出菜单，重置循环继续监测
            if time.monotonic() - self.last_action_time > 1.0:
                self.action_executed = False
                self.state_start_time = time.monotonic()
        else:
            self.log_throttled("⏳ 等待上车菜单弹出...")

    def state_wait_and_back_to_hub(self):
        # 刚点完上车，必须给游戏留出加载车辆模型和关闭列表的时间
        if time.monotonic() - self.last_action_time < 2.0: return
        
        pos = self.ctx.find_image("text_back.png")
        if pos:
            self.ctx.log("车辆加载完成，点击返回以退出车库列表...")
            self.ctx.interaction.game_click(pos)
            self.change_state("enter_upgrades_tuning")
        # else:
        #     self.log_throttled("⏳ 等待上车动画完成与返回按钮...")

    # ================= 3. 导航至熟练度界面 =================
    def state_enter_upgrades_tuning(self):
        pos = self.ctx.find_any_image(["opt_upgrades_tuning_selected.png", "opt_upgrades_tuning_normal.png"])
        if pos:
            self.ctx.log("点击升级与调校...")
            self.ctx.interaction.game_click(pos)
            self.change_state("enter_car_mastery")
        else:
            self.log_throttled("⏳ 等待升级与调校选项...")

    def state_enter_car_mastery(self):
        pos = self.ctx.find_any_image(["opt_car_mastery_normal.png", "opt_car_mastery_selected.png"])
        if pos:
            self.ctx.log("进入车辆熟练度...")
            self.ctx.interaction.game_click(pos)
            self.change_state("check_mastery_status")
        else:
            self.log_throttled("⏳ 等待车辆熟练度选项...")

    # ================= 4. 技能树判定与加点微循环 =================
    def state_check_mastery_status(self):
        # 必须给予 UI 技能树渲染的时间
        if self.time_in_state < 1.0: return
        
        pos_exp = self.ctx.find_image("icon_super_wheelspin_used.png")
        if pos_exp:
            self.ctx.log("⚠️ 该车辆技能已点过，跳过加点流程...")
            self.change_state("exit_mastery")
            return
            
        if not self.action_executed:
            self.ctx.log("💡 解锁初始根节点技能点...")
            self.ctx.interaction.press_key("enter")
            self.action_executed = True
            self.last_action_time = time.monotonic()
            
        if time.monotonic() - self.last_action_time > 1.5:
            self.skill_idx = 0
            self.skill_step = 0
            self.change_state("apply_skill_tree")

    def state_apply_skill_tree(self):
        if self.skill_idx >= len(self.skill_dirs):
            self.ctx.log("✅ 配置的技能路径全部点击完毕！")
            self.change_state("exit_mastery")
            return
            
        now = time.monotonic()
        
        # 【熔断判定】：随时监控技能点是否耗尽
        if self.ctx.find_image("title_insufficient_sp.png"):
            self.ctx.log("🚨 技能点不足！提前结束熟练度加点。")
            self.ctx.interaction.press_key("enter")
            self.out_of_sp = True
            self.change_state("exit_mastery")
            return

        if self.skill_step == 0:
            if now - self.last_action_time > 0.2:
                direction = self.skill_dirs[self.skill_idx]
                self.ctx.interaction.press_key(direction)
                self.skill_step = 1
                self.last_action_time = now
        elif self.skill_step == 1:
            if now - self.last_action_time > 0.2:
                self.ctx.interaction.press_key("enter")
                self.skill_step = 2
                self.last_action_time = now
        elif self.skill_step == 2:
            # 给予技能解锁动画的等待时间
            if now - self.last_action_time > 0.6:
                self.skill_idx += 1
                self.skill_step = 0
                self.last_action_time = now

    # ================= 5. 双重返回与循环判定 =================
    def state_exit_mastery(self):
        if not self.action_executed:
            self.exit_clicks = 0
            self.action_executed = True
            self.last_action_time = time.monotonic()
            
        now = time.monotonic()
        if self.exit_clicks == 0:
            if now - self.last_action_time > 0.5:
                pos = self.ctx.find_image("text_back.png")
                self.ctx.interaction.game_click(pos) if pos else self.ctx.interaction.press_key("esc")
                self.ctx.log("退出车辆熟练度...")
                self.exit_clicks = 1
                self.last_action_time = now
                
        elif self.exit_clicks == 1:
            if now - self.last_action_time > 1.5:
                pos = self.ctx.find_image("text_back.png")
                self.ctx.interaction.game_click(pos) if pos else self.ctx.interaction.press_key("esc")
                self.ctx.log("退出升级与调校界面...")
                self.exit_clicks = 2
                self.last_action_time = now
                
        elif self.exit_clicks == 2:
            if now - self.last_action_time > 1.0:
                self.current_count += 1
                self.update_progress("车辆熟练度加点")
                
                if getattr(self, "out_of_sp", False) or self.current_count >= self.target_count:
                    self.change_state("finish")
                else:
                    self.ctx.log("🔁 准备进行下一辆车的加点...")
                    self.change_state("enter_my_cars")

    def state_finish(self):
        if not self.action_executed:
            self.ctx.router.start_navigation("scene_hub_cars", "scene_menu_campaign")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 成功退回主菜单！熟练度加点任务全部完成！")
            return True
        elif status == "FAILED":
            self.ctx.log("❌ 自动返航失败。")
            return False