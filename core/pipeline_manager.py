import time
from typing import List

class PipelineManager:
    """
    动态流水线管理器 (带拓扑路由功能)
    支持从任意节点切入，支持用户自定义下一步跳往何处，并自动判定大循环。
    """
    def __init__(self, ctx):
        self.ctx = ctx
        self.task_queue = []
        self.global_loop_total = int(self.ctx.config.get("global_loops", 10))
        self.global_loop_current = 1

    def register_task(self, step_id: str, task_class, target_count_key: str, chk_key: str, next_key: str):
        self.task_queue.append({
            "id": step_id,
            "class": task_class,
            "count_key": target_count_key,
            "chk_key": chk_key,
            "next_key": next_key
        })

    def run_pipeline(self, start_step: str):
        if self.ctx.ui_loop_callback:
            self.ctx.ui_loop_callback(self.global_loop_current, self.global_loop_total)

        curr_idx = 0
        for i, task in enumerate(self.task_queue):
            if task["id"] == start_step:
                curr_idx = i
                break

        # 【核心修复 1】：用于在当前执行槽位中保持任务实例，防止脱困重试时进度归零
        current_task_instance = None
        last_run_idx = -1

        while self.ctx.is_running():
            if curr_idx < 0 or curr_idx >= len(self.task_queue):
                self.ctx.log("⚠️ 路由指向了不存在的任务序号，流水线终止。")
                break

            task_info = self.task_queue[curr_idx]
            target_count = int(self.ctx.config.get(task_info["count_key"], 0))

            if target_count > 0:
                # 如果是新进入该节点，或者上一轮大循环过来的，则新建实例；否则复用实例保持进度
                if current_task_instance is None or last_run_idx != curr_idx:
                    current_task_instance = task_info["class"](self.ctx, target_count)
                    last_run_idx = curr_idx

                step_success = False
                try:
                    step_success = current_task_instance.run()
                except Exception as e:
                    self.ctx.log(f"🔥 执行模块 {current_task_instance.__class__.__name__} 时遭遇严重崩溃: {e}")

                if not step_success and self.ctx.is_running():
                    self.ctx.log("⚠️ 模块返回失败，尝试执行雷达脱困重置...")
                    if self.ctx.navigator.recover_to_safe_state():
                        # 【核心修复 2】：脱困成功后，使用 continue 阻止进入下一步路由计算！
                        # 循环回到 while 顶部，且由于 last_run_idx == curr_idx，会复用 current_task_instance 接着跑
                        self.ctx.log(f"✅ 成功脱困，准备继续执行当前未完成的任务 (当前进度: {current_task_instance.current_count}/{target_count})...")
                        continue
                    else:
                        self.ctx.log("🚨 无法通过常规手段脱困，流水线终止。")
                        self.ctx.stop_all()
                        return

                # 任务正常执行完毕，清空当前实例，以便下次大循环回来时从零开始计数
                current_task_instance = None

            if not self.ctx.is_running():
                break

            # 3. 动态路由计算：去哪儿？
            should_continue = self.ctx.config.get(task_info["chk_key"], True)
            if not should_continue:
                self.ctx.log("⏹️ 当前步骤已取消勾选“继续”，任务按用户指令结束。")
                break
                
            default_next_ui_value = curr_idx + 2 
            next_idx = int(self.ctx.config.get(task_info["next_key"], default_next_ui_value)) - 1

            if next_idx < 0:
                self.ctx.log("⏹️ 下一步指向 0，任务按用户指令结束。")
                break

            # 4. 大循环判定：如果下一步的序号 <= 当前序号，说明我们发生了“回滚”或“自循环”
            if next_idx <= curr_idx:
                self.global_loop_current += 1
                if self.global_loop_current > self.global_loop_total:
                    self.ctx.log("🎉 已达到设定的总大循环次数，全自动化流程圆满结束。")
                    break
                    
                if self.ctx.ui_loop_callback:
                    self.ctx.ui_loop_callback(self.global_loop_current, self.global_loop_total)
                self.ctx.log(f"🔄 路由回环，开启新一轮大循环 ({self.global_loop_current}/{self.global_loop_total})")

            # 将游标指向下一步
            curr_idx = next_idx