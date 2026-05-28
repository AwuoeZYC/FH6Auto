import time
from logic.base_task import BaseTask
import core.input_driver as input_driver

class BuyCarTask(BaseTask):
    """
    批量买车任务 (Router 接管版)
    所有跨界面的导航全部交由 UIRouter 处理，自身仅保留纯粹的“斯巴鲁购车循环”。
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
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
        # 2. 告诉司机我们的终点，司机 (Router) 自动接管方向盘
        # (navigate_to 内部自带 while 循环防抖和超时检查，因此这里会短暂阻塞是安全的)
        current_scene = self.ctx.navigator.identify_scene()
        success = self.ctx.router.navigate_to(current_scene, "scene_car_collection")
        
        if success:
            self.ctx.log("✅ 导航成功，已到达指定区域！移交控制权，开始买车业务...")
            self.change_state("start_brand_search")
        else:
            self.ctx.log("❌ 导航系统彻底瘫痪，请求终止。")
            return False

    # ================= 纯粹的买车业务阶段 =================
    def state_start_brand_search(self):
        # 保证单次进入状态只按一次键
        if not self.action_executed:
            self.log_throttled("按 Backspace 展开制造商列表...")
            input_driver.hw_press("backspace")
            self.action_executed = True

        # 非阻塞等待 1 秒后流转状态
        if self.wait_in_state(1.0):
            self.change_state("find_brand_subaru")

    def state_find_brand_subaru(self):
        pos = self.ctx.find_image("brand_Subaru.png")
        if pos:
            if not self.action_executed:
                self.ctx.log("✅ 找到斯巴鲁品牌！点击进入...")
                self.ctx.game_click(pos)
                self.action_executed = True
                
            if self.wait_in_state(1.0):
                self.change_state("find_car_22b")
        else:
            # 配合 log_throttled，即便主循环 0.05s 一次，日志和按键也能被规范限流
            if self.time_in_state > 0.2 and not self.action_executed:
                self.log_throttled("未看到斯巴鲁，向上滚动...")
                input_driver.hw_press("up")
                # 这里不使用 change_state，而是手动重置计时器，让循环重新判定 0.2s 延时
                self.state_start_time = time.monotonic() 

    def state_find_car_22b(self):
        pos = self.ctx.find_image("car_Subaru_22B_collection.png")
        if pos:
            if not self.action_executed:
                self.ctx.log("看到指定车辆，补按 Enter 进入详情...")
                self.ctx.game_click(pos)
                self.action_executed = True
                
            if self.wait_in_state(0.5):
                input_driver.hw_press("enter")
                self.change_state("verify_info_panel")
        else:
            if self.time_in_state > 0.3 and not self.action_executed:
                self.log_throttled("未看到指定车辆，向下滚动...")
                input_driver.hw_press("down")
                self.state_start_time = time.monotonic()

    def state_verify_info_panel(self):
        if self.ctx.find_image("panel_info_Subaru_22B.png"):
            self.ctx.log("🔒 确认处于详情页，开始购买循环！")
            self.change_state("buy_press_space")
        else:
            self.log_throttled("⏳ 等待 22B 详情弹窗出现...")

    def state_buy_press_space(self):
        if self.current_count >= self.target_count:
            self.ctx.log("🎉 购买数量达标！请求退回。")
            self.change_state("finish_and_return")
            return None
            
        input_driver.hw_press("space")
        self.log_throttled("按下 Space...")
        self.change_state("buy_wait_yes")

    def state_buy_wait_yes(self):
        pos = self.ctx.find_any_image(["dialog_yes_selected.png", "dialog_yes_normal.png"])
        if pos:
            self.ctx.log("识别到确认按钮")
            self.ctx.game_click(pos)
            self.transaction_start = time.monotonic()
            self.change_state("buy_wait_buy_btn")
        else:
            self.log_throttled("⏳ 等待确认弹窗...")

    def state_buy_wait_buy_btn(self):
        pos = self.ctx.find_any_image(["dialog_buy_selected.png", "dialog_buy_normal.png"])
        if pos:
            self.ctx.log("识别到购买按钮")
            self.ctx.game_click(pos)
            self.change_state("buy_wait_success_msg")
        else:
            self.log_throttled("⏳ 等待购买按钮...")

    def state_buy_wait_success_msg(self):
        if self.ctx.find_image("info_purchase_success.png"):
            self.ctx.log("✅ 购买成功")
            input_driver.hw_press("enter")
            self.change_state("buy_wait_transaction_finish")
        else:
            self.log_throttled("⏳ 等待购买成功提示...")

    def state_buy_wait_transaction_finish(self):
        if self.ctx.find_image("panel_info_Subaru_22B.png"):
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
            input_driver.hw_press("esc")
            
        # 如果超过 2.5 秒还没看到大厅，说明退了一级还有一级（比如退到了品牌列表），继续补按 ESC
        elif self.time_in_state > 2.5:
            self.log_throttled("尚未到达车辆收藏大厅，补按 ESC...")
            input_driver.hw_press("esc")
            self.state_start_time = time.monotonic()  # 重置计时器，开始下一个 2.5s 判定周期

    def state_route_to_main_menu(self):
        """
        宏观寻路：直接明确告诉路由器起点和终点，省去 GPS 扫描时间。
        """
        success = self.ctx.router.navigate_to("scene_car_collection", "scene_menu_story")
        
        if success:
            self.ctx.log("✅ 成功退回主菜单！买车任务圆满结束。")
            return True
            
        self.ctx.log("❌ 自动返航失败。")
        return False