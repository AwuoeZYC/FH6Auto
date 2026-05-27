import time

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
        
        self.global_timeout = 3600  
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

            handler_method_name = f"state_{self.current_state}"
            handler = getattr(self, handler_method_name, None)

            if not handler:
                self.ctx.log(f"🚨 严重异常：未找到状态处理函数 '{handler_method_name}'")
                return False

            try:
                # 状态处理函数返回 True/False 决定退出，返回 None 维持状态流转
                result = handler()
                
                if result is True:
                    self.ctx.log(f"✅ 任务 {self.__class__.__name__} 完成")
                    return True
                elif result is False:
                    self.ctx.log(f"❌ 任务在状态 [{self.current_state}] 返回失败，请求断点恢复")
                    return False
                    
            except Exception as e:
                self.ctx.log(f"🔥 状态 [{self.current_state}] 发生未捕获异常: {e}")
                return False

            # 保持主线程呼吸频率
            time.sleep(0.05)

        self.ctx.log("⏹️ 任务已收到系统停止指令。")
        return False

    def change_state(self, new_state: str):
        """流转状态并重置单调计时器"""
        if self.current_state != new_state:
            self.current_state = new_state
            self.state_start_time = time.monotonic()

    @property
    def time_in_state(self) -> float:
        """返回当前状态停留的时长 (秒)"""
        return time.monotonic() - self.state_start_time

    def update_progress(self, task_name: str):
        # 解耦 UI 直接调用，交由上下文分发
        if hasattr(self.ctx, "update_running_ui"):
            self.ctx.update_running_ui(task_name, self.current_count, self.target_count)

    def log_throttled(self, msg: str, interval: float = 3.0):
        """防刷屏日志限流器"""
        now = time.monotonic()
        if now - self.last_log_time.get(msg, 0) > interval:
            self.ctx.log(msg)
            self.last_log_time[msg] = now