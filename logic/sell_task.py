import time
from logic.base_task import BaseTask
from core.image_utils import find_with_roi_features

class SellTask(BaseTask):
    """
    全自动批量移除车辆任务 (纯非阻塞状态机版)
    利用严格特征提取，自动寻找指定状态的车辆并从车库中安全删除。
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.task_id = "sell"  # <--- 严格声明本任务的作用域
        self.state_timeout = 60
        self.scroll_count = 0
        self.last_action_time = 0.0

    # ================= 1. 导航与搜索品牌 =================
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

    # ================= 2. 寻车与删车 =================
    def state_start_brand_search(self):
        if not self.action_executed:
            self.ctx.interaction.press_key("backspace")
            self.action_executed = True
            
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
            if self.time_in_state > 0.2 and not self.action_executed:
                self.log_throttled("未看到指定品牌，向上滚动...")
                self.ctx.interaction.press_key("up")
                self.state_start_time = time.monotonic() 

    # ================= 2. 高阶特征寻车与滚动 =================
    def state_car_select_scroll(self):
        # 1. 目标达成拦截
        if self.current_count >= self.target_count:
            self.ctx.log("🎉 移除车辆数量已达标！准备退回主菜单。")
            self.change_state("finish")
            return None

        # 2. 边界拦截：如果品牌标题消失，说明车已经删光了
        title_img = self.get_asset("title_img", is_global=True)
        if not self.ctx.find_image(title_img):
            self.ctx.log("🚨 已经滑出品牌范围 (无车可删)。提前结束移除任务！")
            self.change_state("finish")
            return None

        if getattr(self, "action_executed", False):
            if time.monotonic() - self.last_action_time > 0.5:
                self.change_state("wait_for_remove_menu")
            return None  # 退出当前帧，严禁向下穿透、
        
        anchor_img = self.get_asset("anchor_img")
        features = self.get_features()

        pos = find_with_roi_features(self.ctx, anchor_image=anchor_img, features=features, anchor_threshold=0.9, feature_threshold=0.9, padding=5)

        if pos:
            # 找到了！重置滚动状态，触发点击，并打上动作锁
            self.scroll_active = False
            self.ctx.log("🎯 找到符合要求的车辆，点击唤出操作菜单...")
            self.ctx.interaction.game_click(pos)
            self.action_executed = True
            self.last_action_time = time.monotonic()
        else:
            # 没找到！执行滚动
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
                    self.log_throttled("未看到符合要求的旧车，向右滚动...")
            else:
                # 滚动四轮后，停顿0.5秒等待画面稳定，下一帧重新触发寻图
                if now - self.last_scroll_time > 0.5:
                    self.scroll_active = False

    # ================= 3. 移除逻辑循环 =================
    def state_wait_for_remove_menu(self):
        pos = self.ctx.find_any_image(["opt_remove_selected.png", "opt_remove_normal.png"])
        if pos:
            self.ctx.log("点击 [从车库中移除]...")
            self.ctx.interaction.game_click(pos)
            self.last_action_time = time.monotonic()
            self.change_state("wait_for_confirm")
        elif self.time_in_state > 2.0:
            if not self.action_executed:
                self.ctx.log("未看到移除选项，尝试补按回车唤出菜单...")
                self.ctx.interaction.press_key("enter")
                self.action_executed = True
                self.last_action_time = time.monotonic()
                
            if time.monotonic() - self.last_action_time > 1.0:
                self.action_executed = False
                self.state_start_time = time.monotonic()
        else:
            self.log_throttled("⏳ 等待车辆操作菜单弹出...")

    def state_wait_for_confirm(self):
        pos = self.ctx.find_any_image(["dialog_yes_selected.png", "dialog_yes_normal.png"])
        if pos:
            self.ctx.log("确认移除车辆！")
            self.ctx.interaction.game_click(pos)
            self.last_action_time = time.monotonic()
            self.change_state("wait_for_remove_finish")
        else:
            self.log_throttled("⏳ 等待移除确认弹窗...")

    def state_wait_for_remove_finish(self):
        # 移除车辆后，弹窗消失，游戏会有不到一秒钟的黑屏处理，随后自动回到车辆网格。
        # 这里给足 2.5 秒钟的容错等待时间，防止游戏卡顿。
        if time.monotonic() - self.last_action_time > 2.5:
            self.current_count += 1
            self.update_progress("移除车辆")
            self.ctx.log(f"✅ 成功移除 1 辆，当前进度: {self.current_count}/{self.target_count}")
            # 处理完直接回到寻车状态，下一帧就会拍照寻找下一辆旧车
            self.change_state("car_select_scroll")
        else:
            self.log_throttled("⏳ 等待系统处理移除请求...")

    # ================= 4. 收尾返航 =================
    def state_finish(self):
        if not self.action_executed:
            self.ctx.router.start_navigation("scene_hub_cars", "scene_menu_campaign")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 成功退回主菜单！批量移除车辆任务全部完成！")
            return True
        elif status == "FAILED":
            self.ctx.log("❌ 自动返航失败。")
            return False