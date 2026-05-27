import time
from collections import deque
from core.ui_graph import UI_GRAPH, NODE_IDENTIFIERS
import core.input_driver as input_driver

class UIRouter:
    """
    UI 界面全局导航路由器 (The Driver)
    利用 BFS 算法计算最短路径，并采用状态机机制严格确认每一步的到达。
    """
    def __init__(self, ctx):
        self.ctx = ctx  # 注入 BotController

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
        
        # 截取单帧画面，在内存中进行高频多图判定
        screen_bgr = self.ctx.vision.capture_region(self.ctx.game_region)
        
        if mode == "ALL":
            # 必须全部图像都找到
            for img in images:
                if not self.ctx.check_image_in_buffer(screen_bgr, img):
                    return False
            return True
        else:
            # 找到任意一张即为真
            for img in images:
                if self.ctx.check_image_in_buffer(screen_bgr, img):
                    return True
            return False

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

    def navigate_to(self, current_node: str, target_node: str) -> bool:
        """
        执行寻路，并包含防抖、自愈、超时重试的主动确认状态机机制。
        """
        if current_node == target_node:
            self.ctx.log(f"📍 已经在目标节点 [{target_node}]，无需寻路。")
            return True

        path = self.find_shortest_path(current_node, target_node)
        if not path:
            self.ctx.log(f"🚨 寻路失败：无法找到从 {current_node} 到 {target_node} 的路线！")
            return False

        self.ctx.log(f"🗺️ 算出最短路径，需经过 {len(path)} 步...")

        for step_idx, (next_node, action_type, action_value) in enumerate(path, 1):
            if not self.ctx.is_running(): return False
            
            # --- 执行过图动作 ---
            if action_type == "key":
                input_driver.hw_press(action_value)
            elif action_type == "click_image":
                pos = self.ctx.find_image(action_value)
                if pos:
                    self.ctx.game_click(pos)
                else:
                    self.ctx.log(f"🚨 寻路中断：无法在画面中找到所需的互动按钮 [{action_value}]")
                    return False
            
            # --- 主动确认防抖循环 (防卡死，最多等 8 秒) ---
            wait_start = time.monotonic()
            arrived = False
            last_retry = wait_start
            
            while time.monotonic() - wait_start < 8.0:
                if not self.ctx.is_running(): return False
                
                # 【精准雷达】：只看下一步的节点到了没
                if self.verify_node(next_node):
                    self.ctx.log(f"✅ 导航进度 {step_idx}/{len(path)}: 成功到达 [{next_node}]")
                    arrived = True
                    time.sleep(0.5) # 给界面的 UI 动画(如 Tab 滑动)留微小喘息时间
                    break
                    
                # 【自愈机制】：如果超过 2.5 秒还没到达，说明按键大概率被吞了，补按一次！
                if time.monotonic() - last_retry > 2.5:
                    self.ctx.log(f"⚠️ 疑似丢包或游戏卡顿，重试动作前往 [{next_node}]...")
                    if action_type == "key":
                        input_driver.hw_press(action_value)
                    elif action_type == "click_image":
                        pos = self.ctx.find_image(action_value)
                        if pos: self.ctx.game_click(pos)
                    last_retry = time.monotonic()
                    
                time.sleep(0.1)

            if not arrived:
                self.ctx.log(f"🚨 寻路超时：无法抵达节点 [{next_node}]，放弃导航。")
                return False

        self.ctx.log(f"🎯 寻路完成！成功抵达终点: {target_node}")
        return True