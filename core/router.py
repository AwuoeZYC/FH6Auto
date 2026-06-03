import time
from collections import deque
from core.ui_graph import UI_GRAPH, NODE_IDENTIFIERS
import core.input_driver as hw_driver

class UIRouter:
    def __init__(self, ctx):
        self.ctx = ctx  
        self.status = "IDLE"  # 路由器专属状态标识
        
        self.target_node = None
        self.curr_node = None
        self.path = []
        self.step_idx = 0
        self.wait_start = 0.0
        self.last_retry = 0.0
        self.attempt = 1
        self.max_retries = 5

    def verify_node(self, node_name: str) -> bool:
        """
        【定向降维验证】：只抓取一张截图，并且只验证当前指定的节点所需的特征图。
        绝对不遍历无关图片。
        """
        if node_name not in NODE_IDENTIFIERS:
            self.ctx.log(f"🚨 图鉴中不存在节点 {node_name} 的特征定义！")
            return False

        rules = NODE_IDENTIFIERS[node_name]
        mode = rules.get("mode", "ANY")
        images = rules.get("images", [])
        excludes = rules.get("exclude", [])  # 【新增】：获取排斥列表
        
        # 截取单帧画面，在内存中进行高频多图判定
        screen_bgr = self.ctx.vision.capture_region(self.ctx.game_region)
        
        # --- 1. 正向特征匹配 ---
        is_match = False
        if mode == "ALL":
            is_match = True
            for img in images:
                if not self.ctx.check_image_in_buffer(screen_bgr, img):
                    is_match = False
                    break  # 只要有一张不在，直接打破循环，判负
        else:
            for img in images:
                if self.ctx.check_image_in_buffer(screen_bgr, img):
                    is_match = True
                    break  # 只要找到一张，直接打破循环，判正

        # 如果正向都没通过，直接结束，省去后续检查
        if not is_match:
            return False
            
        # --- 2. 反向排斥特征匹配 ---
        # 既然正向通过了，我们来检查画面里有没有绝对不能出现的违禁图
        for ex_img in excludes:
            if self.ctx.check_image_in_buffer(screen_bgr, ex_img):
                return False  # 踩雷了，一票否决
                
        # 顺利通过正反双重验证
        return True

    def find_shortest_path(self, start_node: str, target_node: str) -> list:
        """
        利用 BFS (广度优先搜索) 在 UI_GRAPH 中寻找两个节点之间的最短操作路径。
        返回格式: [(下个节点, 动作类型, 动作值), ...]
        """
        if start_node == target_node:
            return []

        queue = deque([(start_node, [])])
        visited = set([start_node])

        while queue:
            current, path = queue.popleft()
            
            neighbors = UI_GRAPH.get(current, {})
            for neighbor_node, action_data in neighbors.items():
                if neighbor_node not in visited:
                    new_path = path + [(neighbor_node, action_data["action"], action_data["value"])]
                    if neighbor_node == target_node:
                        return new_path
                        
                    visited.add(neighbor_node)
                    queue.append((neighbor_node, new_path))
                    
        return None # 无法抵达

    def start_navigation(self, current_node: str, target_node: str, max_retries: int = 5):
        """【非阻塞入口】：只初始化寻路数据并计算拓扑路线，立即交出控制权"""
        self.status = "RUNNING"
        self.target_node = target_node
        self.curr_node = current_node
        self.max_retries = max_retries
        self.attempt = 1

        self.ctx.log("⚡ 发送防挂机唤醒信号...")
        self.ctx.interaction.anti_afk_wake()
        
        self._plan_route()

    def _plan_route(self):
        """内部拓扑规划"""
        if self.curr_node == self.target_node:
            if self.verify_node(self.target_node):
                self.ctx.log(f"📍 视觉核验通过：已经在目标节点 [{self.target_node}]")
                self.status = "SUCCESS"
                return
            else:
                self.ctx.log(f"⚠️ 认知与画面不符：预期在 {self.target_node} 但未识别到特征，强制重新规划...")

        self.path = self.find_shortest_path(self.curr_node, self.target_node)
        if not self.path:
            self.ctx.log(f"🚨 寻路失败：无法找到从 {self.curr_node} 到 {self.target_node} 的拓扑路线！")
            self._handle_failure()
            return

        self.ctx.log(f"🗺️ 算出最短路径，需经过 {len(self.path)} 步...")
        self.step_idx = 0
        self._execute_action()

    def _execute_action(self):
        """单步动作下发"""
        if self.step_idx >= len(self.path): 
            # 当所有动作下发完毕，记录当前时间，用于终点核验的稳定缓冲
            self.wait_start = time.monotonic() 
            return
            
        next_node, action_type, action_value = self.path[self.step_idx]
        
        if action_type == "key":
            self.ctx.interaction.press_key(action_value)
        elif action_type == "click_image":
            pos = self.ctx.find_any_image(action_value) if isinstance(action_value, list) else self.ctx.find_image(action_value)
            if pos:
                self.ctx.interaction.game_click(pos)
            else:
                self.ctx.log(f"🚨 寻路中断：无法在画面中找到所需的互动按钮 [{action_value}]")
                self.wait_start = 0 
                return

        self.wait_start = time.monotonic()
        self.last_retry = self.wait_start

    def _handle_failure(self):
        """全局纠错与自愈流转"""
        self.ctx.log(f"⚠️ 寻路受阻，尝试重新定位... (尝试 {self.attempt}/{self.max_retries})")
        new_node = self.ctx.navigator.identify_scene()
        if new_node == "scene_unknown":
            new_node = self.ctx.navigator.recover_to_safe_state()
        
        if not new_node:
            self.ctx.log("🚨 彻底迷失，无法重定位，寻路终止。")
            self.status = "FAILED"
            return

        self.curr_node = new_node
        self.attempt += 1
        if self.attempt > self.max_retries:
            self.ctx.log(f"🚨 达到最大重试次数 ({self.max_retries})，寻路彻底失败！")
            self.status = "FAILED"
            return
            
        self._plan_route()

    def tick(self) -> str:
        """【核心】：外层任务主循环每帧调用一次此方法，纯无阻塞推进寻路进度"""
        if self.status != "RUNNING":
            return self.status

        # ==================================================
        # 1. 到达核验 (带 UI 缓冲墙)
        # ==================================================
        if self.step_idx >= len(self.path):
            # 走完最后一步后，强制等游戏动画飞 0.5 秒，再睁开眼睛看！
            if time.monotonic() - getattr(self, "wait_start", 0) < 0.5:
                return self.status

            if self.verify_node(self.target_node):
                self.ctx.log(f"🎯 寻路完成且核验通过！成功抵达终点: {self.target_node}")
                self.status = "SUCCESS"
            else:
                self.ctx.log(f"⚠️ 寻路核验未通过，未能到达终点 [{self.target_node}]")
                self._handle_failure()
            return self.status

        # ==================================================
        # 2. 单步过程核验
        # ==================================================
        next_node, action_type, action_value = self.path[self.step_idx]
        
        edge_info = UI_GRAPH.get(self.curr_node, {}).get(next_node, {})
        edge_timeout = edge_info.get("timeout", 15.0)
        retry_interval = edge_info.get("retry", 2.5)

        now = time.monotonic()

        # 1. 到达核验
        if self.verify_node(next_node):
            self.ctx.log(f"✅ 导航进度 {self.step_idx+1}/{len(self.path)}: 成功到达 [{next_node}]")
            self.curr_node = next_node
            self.step_idx += 1
            if self.step_idx < len(self.path):
                self._execute_action()
            else:
                self.wait_start = time.monotonic() # 走完最后一步，开始计时缓冲
            return self.status

        # 2. 吞键防抖
        if now - self.last_retry > retry_interval:
            # self.ctx.log(f"⚠️ 疑似长加载或吞键，重试动作前往 [{next_node}]...")
            if action_type == "key":
                self.ctx.interaction.press_key(action_value)
            elif action_type == "click_image":
                pos = self.ctx.find_any_image(action_value) if isinstance(action_value, list) else self.ctx.find_image(action_value)
                if pos: self.ctx.interaction.game_click(pos)
            self.last_retry = now

        # 3. 超时熔断
        if now - self.wait_start > edge_timeout:
            self.ctx.log(f"🚨 寻路超时：无法抵达步骤节点 [{next_node}]，放弃当前路径。")
            self._handle_failure()

        return self.status