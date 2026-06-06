import time
from core.interaction import BotStoppedException
from core.profile_manager import ProfileManager

class BaseTask:
    """
    自动化任务的通用状态机基类。
    统一提供异常捕获、超时熔断、日志节流以及状态路由流转。
    """
    def __init__(self, ctx, target_count=1):
        # 这里的 ctx 在后续拆分中将不再是臃肿的 UI 实例，而是统筹所有服务的 BotController
        self.ctx = ctx  
        self.target_count = target_count
        self.current_count = 0            
        
        self.current_state = None
        self.state_start_time = 0.0
        self.task_start_time = 0.0
        self.action_executed = False  # 动作执行锁，保证进入新状态时触发动作只执行一次
        
        self.global_timeout = 4200  
        self.state_timeout = 45     
        self.last_log_time = {}     

    def run(self) -> bool:
        """
        状态机主循环。
        返回 True 表示任务达标正常结束，返回 False 表示任务死锁或异常熔断请求全局重置。
        """
        self.ctx.log(f"🚀 开始执行任务: {self.__class__.__name__}")
        # 【修改】：使用单调时钟，免疫操作系统时间篡改或 NTP 同步偏移
        self.task_start_time = time.monotonic()
        self.update_progress(self.__class__.__name__)
        self.change_state("init")

        try:
            while getattr(self.ctx, 'is_running', lambda: False)():
                now = time.monotonic()
                
                # 全局熔断检查
                if now - self.task_start_time > self.global_timeout:
                    self.ctx.log("❌ 任务全局超时，强制终止")
                    return False

                # 单一状态死锁检查
                if self.time_in_state > self.state_timeout:
                    self.ctx.log(f"⚠️ 状态 [{self.current_state}] 停留超时({self.state_timeout}s)，请求断点恢复")
                    return False

                state_method = getattr(self, f"state_{self.current_state}", None)
                if state_method:
                    result = state_method()
                    if result is True:
                        return True
                    elif result is False:
                        return False
                else:
                    self.ctx.log(f"🔥 未知的状态节点: {self.current_state}")
                    return False
                
                time.sleep(0.05)  # 主循环节奏，保持足够频繁以响应 F8 熔断指令，同时避免过度占用 CPU
        
        # 不管代码走到哪里，只要抛出这个异常，瞬间就跳到这里安全结束！
        except BotStoppedException as e:
            self.ctx.log(str(e))
            self.ctx.log("⏹️ 任务已响应安全中断指令。")
            return False
        
        except Exception as e:
            self.ctx.log(f"🔥 状态 [{self.current_state}] 发生未捕获异常: {e}")
            return False
        
        return False

    def change_state(self, new_state: str):
        """流转状态并重置单调计时器"""
        if self.current_state != new_state:
            self.current_state = new_state
            self.state_start_time = time.monotonic()
            self.action_executed = False  # 状态切换时自动复位锁

    @property
    def time_in_state(self) -> float:
        """返回当前状态停留的时长 (秒)"""
        return time.monotonic() - self.state_start_time

    def update_progress(self, task_name: str):
        # 【修改】：不再使用 hasattr 猜 UI，而是通过 ctx 统一派发事件
        # 这要求 BotController 提供 update_running_ui 方法（目前已存在）
        if self.ctx and hasattr(self.ctx, "update_running_ui"):
            self.ctx.update_running_ui(task_name, self.current_count, self.target_count)

    def wait_in_state(self, wait_seconds: float) -> bool:
        """
        【新增】：非阻塞等待判定器。
        用法: if not self.wait_in_state(1.5): return None
        它允许当前状态函数立即返回，使得主循环继续保持呼吸（监听 F8），
        直到在当前状态停留的时间超过 wait_seconds 后，才放行执行后续代码。
        """
        return self.time_in_state >= wait_seconds

    def log_throttled(self, msg: str, interval: float = 3.0):
        """防刷屏日志限流器"""
        now = time.monotonic()
        if now - self.last_log_time.get(msg, 0) > interval:
            self.ctx.log(msg)
            self.last_log_time[msg] = now

    
    def get_asset(self, asset_key: str, is_global: bool = False) -> str:
        """【严格资产提取器】：通过 ProfileManager 直接查询外部 JSON"""
        target_vid = self.ctx.config.get("target_vehicle")
        if not target_vid:
            raise ValueError("🚨 致命异常：全局配置中未找到目标车辆 ID (target_vehicle)！")
            
        val = ProfileManager().get_asset(target_vid, getattr(self, "task_id", ""), asset_key, is_global)
        
        if not val:
            scope = "全局配置" if is_global else f"任务 [{getattr(self, 'task_id', 'unknown')}] 专属配置"
            raise KeyError(f"🚨 致命异常：车辆 [{target_vid}] 的 {scope} 中缺少必须的特征资产 '{asset_key}'！")
        return val

    def get_features(self) -> dict:
        """【严格特征提取器】：通过 ProfileManager 直接查询外部 JSON"""
        target_vid = self.ctx.config.get("target_vehicle")
        features = ProfileManager().get_features(target_vid, getattr(self, "task_id", ""))
        
        if features is None:
            raise KeyError(f"🚨 致命异常：车辆 [{target_vid}] 任务 [{getattr(self, 'task_id', 'unknown')}] 中缺少 'features' 特征字典！")
        return features