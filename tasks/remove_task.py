import time
from tasks.base_task import BaseTask
from tasks.mixins import VehicleSelectorMixin

# 【看这里】：通过多继承引入 Mixin，瞬间拥有找车能力！
class RemoveTask(VehicleSelectorMixin, BaseTask):
    """
    全自动批量移除车辆任务 (提炼重构版)
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.task_id = "remove"  
        self.state_timeout = 60
        self.scan_mode = "comprehensive"

    def state_init(self):
        if self.current_count == 0 and self.time_in_state < 0.5: return None
        
        if not getattr(self, "action_executed", False):
            curr = self.ctx.navigator.identify_scene()
            if curr == "scene_unknown":
                curr = self.ctx.navigator.recover_to_safe_state()
                if not curr: return False
            self.ctx.router.start_navigation(curr, "scene_hub_cars")
            self.action_executed = True

        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 到达车库大本营，准备批量移除车辆...")
            self.change_state("enter_my_cars")
        elif status == "FAILED":
            return False

    def state_enter_my_cars(self):
        if getattr(self, "action_executed", False):
            if time.monotonic() - self.last_action_time > 1.5:
                self.change_state("start_brand_search")
            return None # 必须 return，严禁向下穿透去截图
        pos = self.ctx.find_any_image(["opt_my_cars_normal.png", "opt_my_cars_selected.png"], threshold=0.75)
        if pos:
            self.ctx.log("点击进入 [我的车辆]...")
            self.ctx.interaction.game_click(pos)
            self.action_executed = True
            self.last_action_time = time.monotonic()
        else:
            self.log_throttled("⏳ 等待 [我的车辆] 选项...")

    # ================= 拦截重写：判断达标 =================
    def state_car_select_scroll(self):
        if self.current_count >= self.target_count:
            self.ctx.log("🎉 移除车辆数量已达标！准备退回主菜单...")
            self.change_state("finish")
            return None
        # 如果没达标，调用 Mixin 里的原生方法去翻页找车
        super().state_car_select_scroll()

    # ================= 实现 Mixin 的两个钩子 =================
    def on_no_more_vehicles(self):
        """当 Mixin 找不到车（滑出边界）时，会呼叫这个方法"""
        self.ctx.log("🎉 无车可删！提前结束移除任务，准备退回主菜单...")
        self.change_state("finish")

    def on_vehicle_selected(self):
        """当 Mixin 成功点选了一台旧车后，会呼叫这个方法"""
        self.change_state("wait_for_remove_menu")

    # ================= 纯粹的移除逻辑 =================
    def state_wait_for_remove_menu(self):
        pos = self.ctx.find_any_image(["opt_remove_selected.png", "opt_remove_normal.png"], threshold=0.8)
        if pos:
            self.ctx.log("点击 [从车库中移除]...")
            self.ctx.interaction.game_click(pos)
            self.last_action_time = time.monotonic()
            self.change_state("wait_for_confirm")
        elif self.time_in_state > 2.0:
            if not getattr(self, "action_executed", False):
                # self.ctx.log("未看到移除选项，尝试补按回车唤出菜单...")
                self.ctx.interaction.press_key("enter")
                self.action_executed = True
                self.last_action_time = time.monotonic()
            if time.monotonic() - self.last_action_time > 1.0:
                self.action_executed = False
                self.state_start_time = time.monotonic()
        else:
            self.log_throttled("⏳ 等待车辆操作菜单弹出...")

    def state_wait_for_confirm(self):
        pos = self.ctx.find_any_image(["dialog_yes_selected.png", "dialog_yes_normal.png"], threshold=0.8)
        if pos:
            self.ctx.log("确认移除车辆")
            self.ctx.interaction.game_click(pos)
            self.last_action_time = time.monotonic()
            self.change_state("wait_for_remove_finish")
        else:
            self.log_throttled("⏳ 等待移除确认弹窗...")

    def state_wait_for_remove_finish(self):
        if time.monotonic() - self.last_action_time > 2.5:
            self.current_count += 1
            self.update_progress("移除车辆")
            self.ctx.log(f"✅ 成功移除 1 辆，当前进度: {self.current_count}/{self.target_count}")
            # 处理完直接回到寻车状态，下一帧就会拍照寻找下一辆旧车
            self.change_state("car_select_scroll")
        else:
            self.log_throttled("⏳ 等待系统处理移除请求...")

    def state_finish(self):
        if not getattr(self, "action_executed", False):
            self.ctx.router.start_navigation("scene_hub_cars", "scene_menu_campaign")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 成功退回主菜单！批量移除车辆任务全部完成！")
            return True
        elif status == "FAILED":
            self.ctx.log("❌ 自动返航失败。")
            return False