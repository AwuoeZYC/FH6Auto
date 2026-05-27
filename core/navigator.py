import time
from core import input_driver
from core.ui_graph import NODE_IDENTIFIERS

class SceneNavigator:
    """
    全局定位雷达 (The GPS)
    只在任务开局或迷路时，调用一次进行全图扫描。它不关心怎么走路，只告诉你当前在哪。
    """
    def __init__(self, ctx):
        self.ctx = ctx  

    def identify_scene(self) -> str:
        """
        截取单帧画面，遍历 UI_GRAPH 的特征库，判断当前处于哪个节点。
        """
        screen_bgr = self.ctx.vision.capture_region(self.ctx.game_region)

        for node_name, rules in NODE_IDENTIFIERS.items():
            mode = rules.get("mode", "ANY")
            images = rules.get("images", [])
            
            if mode == "ALL":
                # 必须所有特征图都在画面中 (如探索大师，必须同时有标题和排序文字)
                match = all(self.ctx.check_image_in_buffer(screen_bgr, img) for img in images)
            else:
                # 只要有一张特征图在画面中即可匹配 (如包含多种状态的主菜单)
                match = any(self.ctx.check_image_in_buffer(screen_bgr, img) for img in images)
                
            if match:
                return node_name
                
        return "scene_unknown"

    def recover_to_safe_state(self):
        """盲按狂暴脱困协议：一直按 ESC，直到雷达能认出当前界面"""
        self.ctx.log("⚠️ 场景识别为未知状态，尝试回到已知节点...")
        
        for i in range(20):
            if not self.ctx.is_running(): return None 
            
            scene = self.identify_scene()
            if scene != "scene_unknown":
                self.ctx.log(f"✅ 成功逃离未知状态，当前识别为: {scene}")
                return scene  
                
            input_driver.hw_press("esc")
            time.sleep(1.5)
            
        self.ctx.log("🚨 无法通过 ESC 回到任何已知节点，脱困彻底失败！")
        return None