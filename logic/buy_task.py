import time
from logic.base_task import BaseTask

class BuyCarTask(BaseTask):
    """
    批量买车任务 (Router 接管版)
    所有跨界面的导航全部交由 UIRouter 处理，自身仅保留纯粹的“斯巴鲁购车循环”。
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.task_id = "buy"
        self.state_timeout = 60  
        self.transaction_start = 0.0

    # ================= 导航进入阶段 (现在全靠一句话) =================
    def state_init(self):
        if self.current_count == 0 and time.monotonic() - self.task_start_time < 1.0:
            time.sleep(0.5)

        # 1. 打开 GPS 看看我们在哪
        scene = self.ctx.navigator.identify_scene()
        if scene == "scene_unknown":
            scene = self.ctx.navigator.recover_to_safe_state()
            if not scene: return False 
            self.state_start_time = time.monotonic()
            
        self.ctx.log(f"🚩 起点定位成功: {scene}，呼叫 Router 导航至 [车辆收藏]...")
        self.change_state("navigating_to_target")

    def state_navigating_to_target(self):
        if not self.action_executed:
            current_scene = self.ctx.navigator.identify_scene()
            self.ctx.router.start_navigation(current_scene, "scene_car_collection")
            self.action_executed = True
            
        # 让子弹飞：每帧接收路由器返回的进展
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 导航成功，已到达指定区域！移交控制权，开始买车业务...")
            self.change_state("start_brand_search")
        elif status == "FAILED":
            self.ctx.log("❌ 导航系统彻底瘫痪，请求终止。")
            return False

    # ================= 纯粹的买车业务阶段 =================
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
                self.change_state("find_car")
        else:
            # 配合 log_throttled，即便主循环 0.05s 一次，日志和按键也能被规范限流
            if self.time_in_state > 0.2 and not self.action_executed:
                self.log_throttled("未看到指定品牌，向上滚动...")
                self.ctx.interaction.press_key("up")
                # 这里不使用 change_state，而是手动重置计时器，让循环重新判定 0.2s 延时
                self.state_start_time = time.monotonic() 

    def state_find_car(self):
        anchor_img = self.get_asset("anchor_img")
        pos = self.ctx.find_image(anchor_img)
        if pos:
            if not self.action_executed:
                self.ctx.log("看到指定车辆，补按 Enter 进入详情...")
                self.ctx.interaction.game_click(pos)
                self.action_executed = True
                
            if self.wait_in_state(0.5):
                self.ctx.interaction.press_key("enter")
                self.change_state("verify_info_panel")
        else:
            if self.time_in_state > 0.3 and not self.action_executed:
                self.log_throttled("未看到指定车辆，向下滚动...")
                self.ctx.interaction.press_key("down")
                self.state_start_time = time.monotonic()

    def state_verify_info_panel(self):
        info_panel = self.get_asset("info_panel_img")
        if self.ctx.find_image(info_panel):
            self.ctx.log("🔒 确认处于详情页，开始购买循环！")
            self.change_state("buy_press_space")
        else:
            self.log_throttled("⏳ 等待详情弹窗出现...")

    def state_buy_press_space(self):
        if self.current_count >= self.target_count:
            self.ctx.log("🎉 购买数量达标！请求退回。")
            self.change_state("finish_and_return")
            return None
            
        self.ctx.interaction.press_key("space")
        self.log_throttled("按下 Space...")
        self.change_state("buy_wait_yes")

    def state_buy_wait_yes(self):
        pos = self.ctx.find_any_image(["dialog_yes_selected.png", "dialog_yes_normal.png"])
        if pos:
            self.ctx.log("识别到确认按钮")
            self.ctx.interaction.game_click(pos)
            self.transaction_start = time.monotonic()
            self.change_state("buy_wait_buy_btn")
        else:
            self.log_throttled("⏳ 等待确认弹窗...")

    def state_buy_wait_buy_btn(self):
        pos = self.ctx.find_any_image(["dialog_buy_selected.png", "dialog_buy_normal.png"])
        if pos:
            self.ctx.log("识别到购买按钮")
            self.ctx.interaction.game_click(pos)
            self.change_state("buy_wait_success_msg")
        else:
            self.log_throttled("⏳ 等待购买按钮...")

    def state_buy_wait_success_msg(self):
        if self.ctx.find_image("info_purchase_success.png"):
            self.ctx.log("✅ 购买成功")
            self.ctx.interaction.press_key("enter")
            self.change_state("buy_wait_transaction_finish")
        else:
            self.log_throttled("⏳ 等待购买成功提示...")

    def state_buy_wait_transaction_finish(self):
        info_panel = self.get_asset("info_panel_img")
        if self.ctx.find_image(info_panel):
            if time.monotonic() - self.transaction_start > 2.5:
                self.current_count += 1
                self.update_progress("批量买车")
                self.ctx.log(f"✅ 第 {self.current_count}/{self.target_count} 辆购买成功！")
                self.change_state("buy_press_space") 
        else:
            self.log_throttled("⏳ 交易处理中...")

    # ================= 收尾阶段 (微观退回与宏观返航) =================
    def state_finish_and_return(self):
        """
        【小补丁】：微观退回逻辑。
        将控制权交还给路由器前，Task 必须先自己退回到宏观地图节点(车辆收藏大厅)。
        避免直接呼叫全局雷达导致被判定为 unknown 从而触发耗时的盲按脱困。
        """
        # 1. 明确目标：只找车辆收藏大厅的图标。如果看到了，说明已经成功退出了微观页面。
        if self.ctx.find_image("icon_car_collection_beige.png"):
            self.ctx.log("📍 已退回宏观节点 [车辆收藏]，呼叫自动返航...")
            self.change_state("route_to_main_menu")
            return None

        # 2. 如果还没到大厅，负责执行微观退回
        # 刚进入本状态时，立刻按一次 ESC 退出详情页
        if self.time_in_state < 0.1:
            self.ctx.log("离开微观详情页，准备退回大厅...")
            self.ctx.interaction.press_key("esc")
            
        # 如果超过 2.5 秒还没看到大厅，说明退了一级还有一级（比如退到了品牌列表），继续补按 ESC
        elif self.time_in_state > 2.5:
            self.log_throttled("尚未到达车辆收藏大厅，补按 ESC...")
            self.ctx.interaction.press_key("esc")
            self.state_start_time = time.monotonic()  # 重置计时器，开始下一个 2.5s 判定周期

    def state_route_to_main_menu(self):
        if not self.action_executed:
            self.ctx.router.start_navigation("scene_car_collection", "scene_menu_campaign")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 成功退回主菜单！买车任务圆满结束。")
            return True
        elif status == "FAILED":
            self.ctx.log("❌ 自动返航失败。")
            return False