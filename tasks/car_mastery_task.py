import time
from tasks.base_task import BaseTask
from tasks.mixins import VehicleSelectorMixin
from core.profile_manager import ProfileManager
from core.image_utils import read_screen_number

class CarMasteryTask(VehicleSelectorMixin, BaseTask):
    """
    全自动车辆熟练度加点任务 (多继承 Mixin 重构极简版)
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.task_id = "mastery" 
        self.state_timeout = 120  
        self.skill_dirs = self.ctx.config.get("skill_dirs", [])
        
        self.skill_idx = 0
        self.skill_step = 0
        self.exit_clicks = 0

    # ================= 1. 导航与进入车库 =================
    def state_init(self):
        if self.current_count == 0 and self.time_in_state < 0.5: return None
        
        if not getattr(self, "action_executed", False):
            scene = self.ctx.navigator.identify_scene()
            if scene == "scene_unknown":
                scene = self.ctx.navigator.recover_to_safe_state()
                if not scene: return False
            self.ctx.router.start_navigation(scene, "scene_hub_cars")
            self.action_executed = True

        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 到达车库大本营，准备选择车辆...")
            self.change_state("enter_my_cars")
        elif status == "FAILED":
            return False

    def state_enter_my_cars(self):
        if getattr(self, "action_executed", False):
            if time.monotonic() - getattr(self, "last_action_time", 0) > 1.5:
                self.change_state("start_brand_search") # 接入 Mixin 流转！
            return None

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
            self.ctx.log("🎉 加点车辆数量已达标！准备退回主菜单...")
            self.change_state("finish")
            return None
        super().state_car_select_scroll()

    # ================= 实现 Mixin 钩子 =================
    def on_no_more_vehicles(self):
        self.ctx.log("🚨 已经滑出指定品牌范围，未能找到全新指定车辆，任务结束！")
        self.change_state("finish")

    def on_vehicle_selected(self):
        self.change_state("get_in_car")

    # ================= 纯粹的加点业务流转 =================
    def state_get_in_car(self):
        pos = self.ctx.find_any_image(["opt_get_in_normal.png", "opt_get_in_selected.png"])
        if pos:
            self.ctx.log("找到驾驶选项，点击上车...")
            self.ctx.interaction.game_click(pos)
            self.last_action_time = time.monotonic()
            self.change_state("wait_and_back_to_hub")
        elif self.time_in_state > 2.0:
            if not getattr(self, "action_executed", False):
                self.ctx.interaction.press_key("enter")
                self.action_executed = True
                self.last_action_time = time.monotonic()
            if time.monotonic() - self.last_action_time > 1.0:
                self.action_executed = False
                self.state_start_time = time.monotonic()
        else:
            self.log_throttled("⏳ 等待上车菜单弹出...")

    def state_wait_and_back_to_hub(self):
        if time.monotonic() - getattr(self, "last_action_time", 0) < 2.0: return
        
        pos = self.ctx.find_image("text_back.png")
        if pos:
            self.ctx.log("车辆加载完成，点击返回以退出车库列表...")
            self.ctx.interaction.game_click(pos)
            self.change_state("enter_upgrades_tuning")
        # else:
        #     self.log_throttled("⏳ 等待上车动画完成与返回按钮...")

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
            self.change_state("check_sp_balance")
        else:
            self.log_throttled("⏳ 等待车辆熟练度选项...")

    def state_check_sp_balance(self):
        # 强制等待 1.5 秒，确保进入熟练度界面的过渡动画彻底播放完毕，数字渲染清晰
        if self.time_in_state < 1.5: 
            return
            
        # 注意：这里的 offset_x 等参数需要你根据 icon_SP.png 和数字的实际相对位置进行微调测试
        # 假设 icon_SP.png 在数字左边，偏移量设为宽度的粗略估值
        current_sp = read_screen_number(
            self.ctx, 
            anchor_img="icon_SP.png", 
            digit_tpl_path="num_SP_mastery_{}.png", 
            base_offset_x=-45,  # X轴偏移：锚点向右移动多少像素开始画框
            base_offset_y=-12, # Y轴偏移：锚点向上/下移动多少像素
            base_roi_w=45,    # 框宽：能包住999的宽度即可
            base_roi_h=24      # 框高：能包住数字高度即可
        )
        
        if current_sp == -1:
            if self.time_in_state > 3.0:
                self.ctx.log("⚠️ 视觉引擎未能成功拼合 SP 余额，降级为盲点模式...")
                self.change_state("check_mastery_status")
            return
            
        target_vid = self.ctx.config.get("target_vehicle")
        required_sp = ProfileManager().get_skill_sp(target_vid)
        
        self.ctx.log(f"🔍 当前账户 SP 余额 [{current_sp}]，单台需 [{required_sp}]")
        
        # 1. 余额不足单台消耗：硬性阻断，放弃本台车辆
        if current_sp < required_sp:
            self.ctx.log("🚨 SP 余额不足！放弃该车辆，并提前结束本轮批量加点任务。")
            self.out_of_sp = True
            self.change_state("exit_mastery")
            return
            
        # 2. 余额充裕：动态下发目标规划 (仅在该任务生命周期内计算一次)
        if not getattr(self, "sp_calculated", False):
            max_affordable_cars = current_sp // required_sp
            remaining_target = self.target_count - self.current_count
            
            # 如果算出来的可点台数，小于当前剩余的目标台数，则动态缩减目标并更新 UI
            if max_affordable_cars < remaining_target:
                new_target = self.current_count + max_affordable_cars
                self.ctx.log(f"💡 智能规划：SP 仅够支撑 {max_affordable_cars} 台，下调本轮加点目标：{self.target_count} -> {new_target}")
                self.target_count = new_target
                self.update_progress("车辆熟练度加点") # 同步刷新右上角迷你面板
                
            self.sp_calculated = True
            
        # 检查完毕，放行至实际的技能加点流程
        self.change_state("check_mastery_status")

    def state_check_mastery_status(self):
        if self.time_in_state < 1.0: return
        
        pos_exp = self.ctx.find_image("icon_super_wheelspin_used.png")
        if pos_exp:
            self.ctx.log("⚠️ 该车辆技能已点过，跳过加点流程...")
            self.change_state("exit_mastery")
            return
            
        if not getattr(self, "action_executed", False):
            self.ctx.log("💡 解锁初始根节点技能点...")
            self.ctx.interaction.press_key("enter")
            self.action_executed = True
            self.last_action_time = time.monotonic()
            
        if time.monotonic() - self.last_action_time > 0.7:
            self.skill_idx = 0
            self.skill_step = 0
            self.change_state("apply_skill_tree")

    def state_apply_skill_tree(self):
        if self.skill_idx >= len(self.skill_dirs):
            self.ctx.log("✅ 配置的技能路径全部点击完毕！")
            self.change_state("exit_mastery")
            return
            
        now = time.monotonic()
        
        if self.ctx.find_image("title_insufficient_sp.png"):
            self.ctx.log("🚨 技能点不足！提前结束熟练度加点。")
            self.ctx.interaction.press_key("enter")
            self.out_of_sp = True
            self.change_state("exit_mastery")
            return

        if self.skill_step == 0:
            if now - getattr(self, "last_action_time", 0) > 0.05:
                direction = self.skill_dirs[self.skill_idx]
                self.ctx.interaction.press_key(direction)
                self.skill_step = 1
                self.last_action_time = now
        elif self.skill_step == 1:
            if now - self.last_action_time > 0.05:
                self.ctx.interaction.press_key("enter")
                self.skill_step = 2
                self.last_action_time = now
        elif self.skill_step == 2:
            if now - self.last_action_time > 0.4:
                self.skill_idx += 1
                self.skill_step = 0
                self.last_action_time = now

    def state_exit_mastery(self):
        if not getattr(self, "action_executed", False):
            self.exit_clicks = 0
            self.action_executed = True
            self.last_action_time = time.monotonic()
            
        now = time.monotonic()
        if self.exit_clicks == 0:
            if now - self.last_action_time > 0.5:
                pos = self.ctx.find_image("text_back.png")
                if pos: self.ctx.interaction.game_click(pos)
                else: self.ctx.interaction.press_key("esc")
                self.ctx.log("退出车辆熟练度...")
                self.exit_clicks = 1
                self.last_action_time = now
                
        elif self.exit_clicks == 1:
            if now - self.last_action_time > 1.5:
                pos = self.ctx.find_image("text_back.png")
                if pos: self.ctx.interaction.game_click(pos)
                else: self.ctx.interaction.press_key("esc")
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
                    self.action_executed = False 
                    self.change_state("route_to_hub")

    def state_route_to_hub(self):
        if not getattr(self, "action_executed", False):
            # 乐观预测。99%的情况退出调校后在 scene_hub_cars
            if self.ctx.router.verify_node("scene_hub_cars"):
                curr = "scene_hub_cars"
            else:
                # 只有当发生意外（吞键没退干净）时，才呼叫沉重的全图雷达
                self.ctx.log("⚠️ 预测位置失败，启动全图雷达扫描...")
                curr = self.ctx.navigator.identify_scene()
                if curr == "scene_unknown":
                    curr = self.ctx.navigator.recover_to_safe_state()
                    if not curr: return False
                    
            self.ctx.router.start_navigation(curr, "scene_hub_cars")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.change_state("enter_my_cars")
        elif status == "FAILED":
            return False

    def state_finish(self):
        if not getattr(self, "action_executed", False):
            self.ctx.router.start_navigation("scene_home_garage", "scene_menu_campaign")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 成功退回主菜单！熟练度加点任务全部完成！")
            return True
        elif status == "FAILED":
            self.ctx.log("❌ 自动返航失败。")
            return False