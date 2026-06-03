import time
from tasks.base_task import BaseTask
from tasks.mixins import VehicleSelectorMixin
from core.image_utils import find_with_roi_features

class RaceTask(VehicleSelectorMixin, BaseTask):
    """
    全自动循环跑图任务 (多继承 Mixin 极简版)
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.task_id = "race"
        self.state_timeout = 90  
        self.share_code = str(self.ctx.config.get("share_code", "123456789")).replace(" ", "")
        
        self.race_start_time = 0.0
        self.e_presses = 0
        self.char_idx = 0

    # ================= 1. 导航与搜索蓝图 =================
    def state_init(self):
        if self.current_count == 0 and self.time_in_state < 0.5: return None
        scene = self.ctx.navigator.identify_scene()
        if scene == "scene_unknown":
            scene = self.ctx.navigator.recover_to_safe_state()
            if not scene: return False
            self.state_start_time = time.monotonic()
            
        self.ctx.log("🚩 开始导航至 [创意中心 - 蓝图赛事]...")
        self.change_state("navigating_to_eventlab")

    def state_navigating_to_eventlab(self):
        if not getattr(self, "action_executed", False):
            curr = self.ctx.navigator.identify_scene()
            self.ctx.router.start_navigation(curr, "scene_play_event")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 到达赛事中心，准备搜索蓝图...")
            self.change_state("open_search_menu")
        elif status == "FAILED":
            return False

    def state_open_search_menu(self):
        if not getattr(self, "action_executed", False):
            self.ctx.interaction.press_key("backspace")
            self.action_executed = True
            
        pos = self.ctx.find_any_image(["opt_code_normal.png", "opt_code_selected.png"])
        if pos:
            self.ctx.log("识别到代码输入选项，进入...")
            self.ctx.interaction.game_click(pos)
            self.change_state("wait_enter_code_input")
        elif self.time_in_state > 3.0:
            self.log_throttled("未找到代码选项，重试...")
            self.action_executed = False
            self.state_start_time = time.monotonic()

    def state_wait_enter_code_input(self):
        if self.wait_in_state(0.5):
            self.ctx.interaction.press_key("enter")
            self.change_state("input_share_code")

    def state_input_share_code(self):
        if self.ctx.find_image("title_code.png"):
            if not getattr(self, "action_executed", False):
                self.ctx.log(f"⌨️ 正在输入蓝图代码: {self.share_code}...")
                self.char_idx = 0
                self.last_action_time = time.monotonic()
                self.action_executed = True
                
            now = time.monotonic()
            if self.char_idx < len(self.share_code):
                if now - self.last_action_time > 0.01:
                    self.ctx.interaction.press_key(self.share_code[self.char_idx])
                    self.char_idx += 1
                    self.last_action_time = now
            else:
                if now - self.last_action_time > 0.5:
                    self.ctx.interaction.press_key("enter")
                    self.change_state("confirm_search")
        else:
            self.log_throttled("⏳ 等待代码输入框弹出...")

    def state_confirm_search(self):
        pos = self.ctx.find_any_image(["dialog_confirm_normal.png", "dialog_confirm_selected.png"])
        if pos:
            self.ctx.log("确认搜索...")
            self.ctx.interaction.game_click(pos)
            self.change_state("enter_event_info")
        else:
            self.log_throttled("⏳ 等待搜索确认按钮...")

    # ================= 2. 赛事进入与选车 =================
    def state_enter_event_info(self):
        if self.ctx.find_image("text_view_event_info.png"):
            self.ctx.log("已进入赛事详情，准备单人游玩...")
            self.ctx.interaction.press_key("enter")
            self.change_state("select_single_player")
        else:
            self.log_throttled("⏳ 正在检索蓝图...")

    def state_select_single_player(self):
        pos = self.ctx.find_any_image(["opt_single_player_normal.png", "opt_single_player_selected.png"])
        if pos:
            self.ctx.log("选择单人游戏...")
            self.ctx.interaction.game_click(pos)
            self.change_state("car_select_initial_check")
        else:
            self.log_throttled("⏳ 等待单人游戏选项...")
    
    def state_car_select_initial_check(self):
        if self.time_in_state < 3.0: return
        
        # 隔离墙：点到车后锁定并延时流转
        if getattr(self, "action_executed", False):
            if time.monotonic() - self.last_action_time > 0.5:
                self.ctx.interaction.press_key("enter")
                self.change_state("wait_for_race_prep")
            return None

        anchor_img = self.get_asset("anchor_img")
        features = self.get_features()
        
        # 使用和 Mixin 同等严格的 0.9 阈值，彻底阻断假阳性！
        pos = find_with_roi_features(
            self.ctx, 
            anchor_image=anchor_img, 
            features=features, 
            anchor_threshold=0.6, 
            feature_threshold=0.8, 
            padding=5)
        
        if pos:
            self.ctx.log("🎯 成功识别到目标车辆！")
            self.ctx.interaction.game_click(pos)
            self.action_executed = True
            self.last_action_time = time.monotonic()
        elif self.time_in_state > 6.0:
            if not getattr(self, "backspace_pressed", False):
                self.ctx.log("当前界面未找到目标车辆，退回品牌列表寻找...")
                self.ctx.interaction.press_key("backspace")
                self.backspace_pressed = True
                self.last_action_time = time.monotonic()
                
            elif time.monotonic() - self.last_action_time > 0.5:
                self.backspace_pressed = False
                self.change_state("find_brand") # <-- 流转进 Mixin 的找品牌阶段！
        else:
            self.log_throttled("🔍 扫描车辆中...")

    # ================= Mixin 钩子实现 =================
    def on_vehicle_selected(self):
        self.ctx.interaction.press_key("enter")
        self.change_state("wait_for_race_prep")

    def on_no_more_vehicles(self):
        self.ctx.log("🚨 已经滑出指定品牌范围，未能找到指定车辆，任务异常终止！")
        self.change_state("finish_and_return")

    # ================= 3. 赛事准备与起跑 =================
    def state_wait_for_race_prep(self):
        pos = self.ctx.find_any_image(["opt_start_game_normal.png", "opt_start_game_selected.png"])
        if pos:
            self.ctx.log(f"🏁 第 {self.current_count + 1}/{self.target_count} 场比赛准备完毕，点击开始！")
            self.ctx.interaction.game_click(pos)
            self.change_state("racing_start")
        # else:
        #     self.log_throttled("⏳ 等待赛事加载与开始按钮...")

    def state_racing_start(self):
        if self.time_in_state > 3.0:
            self.ctx.log("🏎️ 踩下油门 (W)！")
            self.ctx.interaction.key_down("w")
            self.race_start_time = time.monotonic()
            self.e_presses = 0
            self.change_state("racing_loop")
        else:
            self.log_throttled("🚥 等待起步动画...")

    def state_racing_loop(self):
        elap = time.monotonic() - self.race_start_time
        if elap >= 3.0 and self.e_presses == 0:
            self.ctx.interaction.press_key("e")
            self.e_presses = 1
        elif elap >= 5.0 and self.e_presses == 1:
            self.ctx.interaction.press_key("e")
            self.e_presses = 2

        if elap > 10.0:
            pos = self.ctx.find_any_image(["opt_restart.png", "opt_continue.png"])
            if pos:
                self.ctx.log("🏁 比赛结束！松开油门。")
                self.ctx.interaction.key_up("w")
                self.change_state("race_end_action")

    # ================= 4. 结算与收尾 =================
    def state_race_end_action(self):
        if self.current_count >= self.target_count - 1:
            if not getattr(self, "action_executed", False):
                self.ctx.log("🎉 所有跑图次数已完成，选择继续并退出...")
                self.ctx.interaction.press_key("enter")
                self.action_executed = True
                
            if self.wait_in_state(0.5):
                self.current_count += 1
                self.update_progress("循环跑图")
                self.change_state("check_thumb_up")
        else:
            if not getattr(self, "action_executed", False):
                self.ctx.log("🔁 跑图未达标，准备重新开始本赛事...")
                self.ctx.interaction.press_key("x")
                self.action_executed = True
                
            if self.wait_in_state(1.0):
                pos = self.ctx.find_any_image(["dialog_yes_selected.png", "dialog_yes_normal.png"])
                if pos:
                    self.ctx.log("确认重新开始...")
                    self.ctx.interaction.game_click(pos)
                    self.current_count += 1
                    self.update_progress("循环跑图")
                    self.change_state("wait_for_race_prep")
                else:
                    self.log_throttled("等待重新开始确认弹窗...")
                    
    def state_check_thumb_up(self):
        pos = self.ctx.find_any_image(["dialog_thumb_up_selected.png", "dialog_thumb_up_normal.png"])
        if pos:
            self.ctx.log("👍 随手给蓝图作者点个赞...")
            self.ctx.interaction.game_click(pos)
            self.change_state("finish_and_return")
        elif self.time_in_state > 4.0:
            self.change_state("finish_and_return")
            
    def state_finish_and_return(self):
        if not getattr(self, "action_executed", False):
            self.ctx.log("📍 赛事完全结束，退回主菜单...")
            curr = self.ctx.navigator.identify_scene()
            if curr == "scene_unknown":
                curr = self.ctx.navigator.recover_to_safe_state()
                if not curr: return False
            self.ctx.router.start_navigation(curr, "scene_menu_campaign")
            self.action_executed = True
            
        status = self.ctx.router.tick()
        if status == "SUCCESS":
            self.ctx.log("✅ 成功退回主菜单！跑图任务圆满结束。")
            return True
        elif status == "FAILED":
            return False