import time
import core.input_driver as input_driver
from logic.base_task import BaseTask

class RaceTask(BaseTask):
    """
    全自动循环跑图任务 (严谨非阻塞状态机版)
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.state_timeout = 90  
        self.share_code = str(self.ctx.config.get("share_code", "123456789")).replace(" ", "")
        
        self.race_start_time = 0.0
        self.e_presses = 0
        
        # 微循环与延时动作追踪
        self.char_idx = 0
        self.last_action_time = 0.0
        self.scroll_count = 0
        self.last_scroll_time = 0.0

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
        curr = self.ctx.navigator.identify_scene()
        if self.ctx.router.navigate_to(curr, "scene_play_event"):
            self.ctx.log("✅ 到达赛事中心，准备搜索蓝图...")
            self.change_state("open_search_menu")
        else:
            return False

    def state_open_search_menu(self):
        if not self.action_executed:
            input_driver.hw_press("backspace")
            self.action_executed = True
            
        pos = self.ctx.find_any_image(["opt_code_normal.png", "opt_code_selected.png"])
        if pos:
            self.ctx.log("识别到代码输入选项，进入...")
            self.ctx.game_click(pos)
            self.change_state("wait_enter_code_input")
        elif self.time_in_state > 3.0:
            self.log_throttled("未找到代码选项，重试...")
            self.action_executed = False
            self.state_start_time = time.monotonic()

    def state_wait_enter_code_input(self):
        if self.wait_in_state(0.5):
            input_driver.hw_press("enter")
            self.change_state("input_share_code")

    def state_input_share_code(self):
        if self.ctx.find_image("title_code.png"):
            if not self.action_executed:
                self.ctx.log(f"⌨️ 正在输入蓝图代码: {self.share_code}...")
                self.char_idx = 0
                self.last_action_time = time.monotonic()
                self.action_executed = True
                
            now = time.monotonic()
            if self.char_idx < len(self.share_code):
                if now - self.last_action_time > 0.1:
                    input_driver.hw_press(self.share_code[self.char_idx])
                    self.char_idx += 1
                    self.last_action_time = now
            else:
                if now - self.last_action_time > 0.5:
                    input_driver.hw_press("enter")
                    self.change_state("confirm_search")
        else:
            self.log_throttled("⏳ 等待代码输入框弹出...")

    def state_confirm_search(self):
        pos = self.ctx.find_any_image(["dialog_confirm_normal.png", "dialog_confirm_selected.png"])
        if pos:
            self.ctx.log("确认搜索...")
            self.ctx.game_click(pos)
            # 点击后无需原地等待，直接进入下一状态，由下个状态的图像识别接管加载延迟
            self.change_state("enter_event_info")
        else:
            self.log_throttled("⏳ 等待搜索确认按钮...")

    # ================= 2. 赛事进入与选车 =================
    def state_enter_event_info(self):
        if self.ctx.find_image("text_view_event_info.png"):
            self.ctx.log("已进入赛事详情，准备单人游玩...")
            input_driver.hw_press("enter")
            self.change_state("select_single_player")
        else:
            self.log_throttled("⏳ 正在检索蓝图...")

    def state_select_single_player(self):
        pos = self.ctx.find_any_image(["opt_single_player_normal.png", "opt_single_player_selected.png"])
        if pos:
            self.ctx.log("选择单人游戏...")
            self.ctx.game_click(pos)
            self.change_state("car_select_initial_check")
        else:
            self.log_throttled("⏳ 等待单人游戏选项...")

    def _is_target_car_on_screen(self):
        car_pos = self.ctx.find_image("car_Subaru_22B_liked.png", threshold=0.6)
        if not car_pos: return None
        text_pos = self.ctx.find_image("text_1998_Subaru.png", threshold=0.8)
        if not text_pos: return None
        tag_pos = self.ctx.find_image("tag_liked.png", threshold=0.8)
        if not tag_pos: return None
        return car_pos

    def state_car_select_initial_check(self):
        if self.time_in_state < 3.0: return
        
        pos = self._is_target_car_on_screen()
        if pos:
            self.ctx.log("🎯 成功识别到斯巴鲁 22B！")
            self.ctx.game_click(pos)
            # 修复点：既然点中了当前车辆，游戏会自动进加载界面，直接流转
            self.change_state("wait_for_race_prep")
        elif self.time_in_state > 6.0:
            if not self.action_executed:
                self.ctx.log("当前界面未找到目标车辆，退回品牌列表寻找...")
                input_driver.hw_press("backspace")
                self.action_executed = True
                self.last_action_time = time.monotonic()
                
            # 修复点：使用独立时间戳判断
            if time.monotonic() - self.last_action_time > 0.5:
                self.change_state("find_subaru_brand")
        else:
            self.log_throttled("🔍 扫描车辆中...")

    def state_find_subaru_brand(self):
        pos = self.ctx.find_image("brand_Subaru.png")
        if pos:
            self.ctx.game_click(pos)
            self.change_state("car_select_scroll")
        else:
            if self.time_in_state > 0.3 and not self.action_executed:
                self.log_throttled("未看到斯巴鲁品牌，向上滚动...")
                input_driver.hw_press("up")
                self.state_start_time = time.monotonic()

    def state_car_select_scroll(self):
        if not self.ctx.find_image("title_Subaru.png"):
            self.ctx.log("🚨 已经滑出斯巴鲁品牌范围，未能找到 22B，任务异常终止！")
            return False
            
        pos = self._is_target_car_on_screen()
        if pos:
            if not self.action_executed:
                self.ctx.log("🎯 成功在列表中找到斯巴鲁 22B！")
                self.ctx.game_click(pos)
                self.action_executed = True
                self.last_action_time = time.monotonic()
            
            # 在列表中点击后，需要补按回车。这里使用准确的独立时间戳。
            if time.monotonic() - self.last_action_time > 0.5:
                input_driver.hw_press("enter")
                self.change_state("wait_for_race_prep")
        else:
            if not self.action_executed:
                self.scroll_count = 0
                self.last_scroll_time = time.monotonic()
                self.action_executed = True
            
            now = time.monotonic()
            if self.scroll_count < 4:
                if now - self.last_scroll_time > 0.1:
                    input_driver.hw_press("right")
                    self.scroll_count += 1
                    self.last_scroll_time = now
                    self.log_throttled("未看到 22B，向右滚动...")
            else:
                if now - self.last_scroll_time > 0.5:
                    self.action_executed = False
                    self.state_start_time = time.monotonic()

    # ================= 3. 赛事准备与起跑 =================
    def state_wait_for_race_prep(self):
        pos = self.ctx.find_any_image(["opt_start_game_normal.png", "opt_start_game_selected.png"])
        if pos:
            self.ctx.log(f"🏁 第 {self.current_count + 1}/{self.target_count} 场比赛准备完毕，点击开始！")
            self.ctx.game_click(pos)
            self.change_state("racing_start")
        else:
            self.log_throttled("⏳ 等待赛事加载与开始按钮...")

    def state_racing_start(self):
        if self.time_in_state > 5.0:
            self.ctx.log("🏎️ 踩下油门 (W)！")
            input_driver.hw_key_down("w")
            self.race_start_time = time.monotonic()
            self.e_presses = 0
            self.change_state("racing_loop")
        else:
            self.log_throttled("🚥 等待起步动画...")

    # ================= 4. 纯净的非阻塞跑图状态机 =================
    def state_racing_loop(self):
        elap = time.monotonic() - self.race_start_time
        if elap >= 3.0 and self.e_presses == 0:
            input_driver.hw_press("e")
            self.e_presses = 1
        elif elap >= 5.0 and self.e_presses == 1:
            input_driver.hw_press("e")
            self.e_presses = 2

        if elap > 10.0:
            pos = self.ctx.find_any_image(["opt_restart.png", "opt_continue.png"])
            if pos:
                self.ctx.log("🏁 比赛结束！松开油门。")
                input_driver.hw_key_up("w")
                self.change_state("race_end_action")
            else:
                self.log_throttled("🏎️ 自动驾驶中，随时监控结算画面...")

    # ================= 5. 结算与收尾 =================
    def state_race_end_action(self):
        if self.current_count >= self.target_count - 1:
            if not self.action_executed:
                self.ctx.log("🎉 所有跑图次数已完成，选择继续并退出...")
                input_driver.hw_press("enter")
                self.action_executed = True
                
            if self.wait_in_state(0.5):
                self.current_count += 1
                self.update_progress("循环跑图")
                self.change_state("check_thumb_up")
        else:
            if not self.action_executed:
                self.ctx.log("🔁 跑图未达标，准备重新开始本赛事...")
                input_driver.hw_press("x")
                self.action_executed = True
                
            if self.wait_in_state(1.0):
                pos = self.ctx.find_any_image(["dialog_yes_selected.png", "dialog_yes_normal.png"])
                if pos:
                    self.ctx.log("确认重新开始...")
                    self.ctx.game_click(pos)
                    self.current_count += 1
                    self.update_progress("循环跑图")
                    self.change_state("wait_for_race_prep")
                else:
                    self.log_throttled("等待重新开始确认弹窗...")
                    
    def state_check_thumb_up(self):
        pos = self.ctx.find_any_image(["dialog_thumb_up_selected.png", "dialog_thumb_up_normal.png"])
        if pos:
            self.ctx.log("👍 随手给蓝图作者点个赞...")
            self.ctx.game_click(pos)
            self.change_state("finish_and_return")
        elif self.time_in_state > 4.0:
            self.change_state("finish_and_return")
            
    def state_finish_and_return(self):
        self.ctx.log("📍 赛事完全结束，退回主菜单...")
        
        curr = self.ctx.navigator.identify_scene()
        if curr == "scene_unknown":
            curr = self.ctx.navigator.recover_to_safe_state()
            if not curr: return False
            
        success = self.ctx.router.navigate_to(curr, "scene_menu_story")
        if success:
            self.ctx.log("✅ 成功退回主菜单！跑图任务圆满结束。")
            return True
            
        return False