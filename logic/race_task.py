import time
import core.input_driver as input_driver
from logic.base_task import BaseTask

class RaceTask(BaseTask):
    """
    全自动循环跑图任务 (基于蓝图搜索与全辅助驾驶)
    """
    def __init__(self, ctx, target_count):
        super().__init__(ctx, target_count)
        self.state_timeout = 90  # 跑图流程较长，延长状态超时时间
        self.share_code = str(self.ctx.config.get("share_code", "123456789")).replace(" ", "")
        
        # 跑图内部计时器
        self.race_start_time = 0.0
        self.e_presses = 0

    # ================= 1. 导航与搜索蓝图 =================
    def state_init(self):
        if self.current_count == 0 and time.monotonic() - self.task_start_time < 1.0:
            time.sleep(0.5)

        scene = self.ctx.navigator.identify_scene()
        if scene == "scene_unknown":
            scene = self.ctx.navigator.recover_to_safe_state()
            if not scene: return False
            self.state_start_time = time.monotonic()
            
        self.ctx.log("🚩 开始导航至 [创意中心 - 蓝图赛事]...")
        self.change_state("navigating_to_eventlab")

    def state_navigating_to_eventlab(self):
        curr = self.ctx.navigator.identify_scene()
        # 路由到 scene_play_event (游玩赛事页，此时按 Backspace 可搜索)
        success = self.ctx.router.navigate_to(curr, "scene_play_event")
        if success:
            self.ctx.log("✅ 到达赛事中心，准备搜索蓝图...")
            self.change_state("open_search_menu")
        else:
            return False

    def state_open_search_menu(self):
        # 按 Backspace 呼出搜索菜单
        if self.time_in_state < 0.1:
            input_driver.hw_press("backspace")
            
        pos = self.ctx.find_any_image(["opt_code_normal.png", "opt_code_selected.png"])
        if pos:
            self.ctx.log("识别到代码输入选项，进入...")
            self.ctx.game_click(pos)
            time.sleep(0.5)
            input_driver.hw_press("enter")
            self.change_state("input_share_code")
        elif self.time_in_state > 3.0:
            self.log_throttled("未找到代码选项，重试...")
            input_driver.hw_press("backspace")
            self.state_start_time = time.monotonic()

    def state_input_share_code(self):
        if self.ctx.find_image("title_code.png"):
            self.ctx.log(f"⌨️ 正在输入蓝图代码: {self.share_code}...")
            # 模拟键盘输入代码
            for char in self.share_code:
                if not self.ctx.is_running(): return False
                input_driver.hw_press(char)
                time.sleep(0.1)
            time.sleep(0.5)
            input_driver.hw_press("enter")
            self.change_state("confirm_search")
        else:
            self.log_throttled("⏳ 等待代码输入框弹出...")

    def state_confirm_search(self):
        pos = self.ctx.find_any_image(["dialog_confirm_normal.png", "dialog_confirm_selected.png"])
        if pos:
            self.ctx.log("确认搜索...")
            self.ctx.game_click(pos)
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
        """精准且极具容错的车辆识别逻辑 (三维印证)"""
        # 1. 找轮廓图 (降低阈值防涂装干扰)
        car_pos = self.ctx.find_image("car_Subaru_22B_liked.png", threshold=0.6)
        if not car_pos: return None
        
        # 2. 找年份品牌文字
        text_pos = self.ctx.find_image("text_1998_Subaru.png", threshold=0.8)
        if not text_pos: return None
        
        # 3. 找点赞 Tag
        tag_pos = self.ctx.find_image("tag_liked.png", threshold=0.8)
        if not tag_pos: return None
        
        return car_pos # 三者同时存在，返回车辆坐标

    def state_car_select_initial_check(self):
        # 给加载选车界面留出充足时间
        if self.time_in_state < 3.0: return
        
        pos = self._is_target_car_on_screen()
        if pos:
            self.ctx.log("🎯 成功识别到斯巴鲁 22B！")
            self.ctx.game_click(pos)
            self.change_state("wait_for_race_prep")
        elif self.time_in_state > 6.0:
            self.ctx.log("当前界面未找到目标车辆，退回品牌列表寻找...")
            input_driver.hw_press("backspace")
            self.change_state("find_subaru_brand")
        else:
            self.log_throttled("🔍 扫描车辆中...")

    def state_find_subaru_brand(self):
        pos = self.ctx.find_image("brand_Subaru.png")
        if pos:
            self.ctx.log("✅ 找到斯巴鲁品牌，进入...")
            self.ctx.game_click(pos)
            time.sleep(1.0)
            self.change_state("car_select_scroll")
        else:
            self.log_throttled("未看到斯巴鲁品牌，向上滚动...")
            input_driver.hw_press("up")
            time.sleep(0.3)

    def state_car_select_scroll(self):
        if not self.ctx.find_image("title_Subaru.png"):
            self.ctx.log("🚨 已经滑出斯巴鲁品牌范围，未能找到 22B，任务异常终止！")
            return False
            
        pos = self._is_target_car_on_screen()
        if pos:
            self.ctx.log("🎯 成功在列表中找到斯巴鲁 22B！")
            self.ctx.game_click(pos)
            time.sleep(0.5)
            input_driver.hw_press("enter")
            self.change_state("wait_for_race_prep")
        else:
            self.log_throttled("未看到 22B，向右滚动 4 次...")
            for _ in range(4):
                if not self.ctx.is_running(): return False
                input_driver.hw_press("right")
                time.sleep(0.1)
            time.sleep(0.5)

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
        # 赛事刚开始有倒计时，延时按 W，彻底替换原代码的死循环识别
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
        
        # 3 秒和 5 秒时的换挡/确认操作
        if elap >= 3.0 and self.e_presses == 0:
            input_driver.hw_press("e")
            self.e_presses = 1
        elif elap >= 5.0 and self.e_presses == 1:
            input_driver.hw_press("e")
            self.e_presses = 2

        # 给足够的时间离开起点，再去识别终点按钮，防止误判
        if elap > 10.0:
            # 原代码通过寻找 restart 判定结束，这里寻找任意结算按钮
            pos = self.ctx.find_any_image(["opt_restart.png", "opt_continue.png"])
            if pos:
                self.ctx.log("🏁 比赛结束！松开油门。")
                input_driver.hw_key_up("w")
                self.change_state("race_end_action")
            else:
                self.log_throttled("🏎️ 自动驾驶中，随时监控结算画面...")

    # ================= 5. 结算与收尾 =================
    def state_race_end_action(self):
        if self.current_count == self.target_count - 1:
            # 已经是最后一把，不点了，直接按 Enter (继续)
            self.ctx.log("🎉 所有跑图次数已完成，选择继续并退出...")
            input_driver.hw_press("enter")
            self.current_count += 1
            self.update_progress("循环跑图")
            self.change_state("check_thumb_up")
        else:
            # 还没跑够，按 X (重试)，然后按 Enter (确认)
            if self.time_in_state < 0.1:
                self.ctx.log("🔁 跑图未达标，准备重新开始本赛事...")
                input_driver.hw_press("x")
            elif self.time_in_state > 1.0:
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
        # 检查是否弹出点赞界面
        pos = self.ctx.find_any_image(["dialog_thumb_up_selected.png", "dialog_thumb_up_normal.png"])
        if pos:
            self.ctx.log("👍 随手给蓝图作者点个赞...")
            self.ctx.game_click(pos)
            self.change_state("finish_and_return")
        elif self.time_in_state > 4.0:
            # 4秒没弹出点赞，大概率是没触发，直接走人
            self.change_state("finish_and_return")
            
    def state_finish_and_return(self):
        self.ctx.log("📍 赛事完全结束，退回主菜单...")
        
        # 让 GPS 扫描确认已经退回到漫游模式或菜单
        curr = self.ctx.navigator.identify_scene()
        if curr == "scene_unknown":
            curr = self.ctx.navigator.recover_to_safe_state()
            if not curr: return False
            
        success = self.ctx.router.navigate_to(curr, "scene_menu_story")
        if success:
            self.ctx.log("✅ 成功退回主菜单！跑图任务圆满结束。")
            return True
            
        return False