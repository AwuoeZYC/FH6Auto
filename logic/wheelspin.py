import time
import core.input_driver as input_driver

def run_wheelspin(ctx, target_count):
    if ctx.cj_counter >= target_count:
        return True

    ctx.update_running_ui("超级抽奖", ctx.cj_counter, target_count)

    ctx.log("准备验证/进入菜单...")
    if not ctx.enter_menu():
        return False

    ctx.log("进入车辆与收藏...")
    input_driver.hw_press("pagedown", delay=0.15)
    time.sleep(1.0)

    pos_buycar = ctx.vision.wait_for_image(
        "BNandUC.png",
        region=ctx.regions["左"],
        threshold=0.75,
        timeout=12,
        interval=0.3,
        fast_mode=True
    )
    if not pos_buycar:
        ctx.log("未识别到 购买新车与二手车")
        return False

    ctx.game_click(pos_buycar)
    time.sleep(0.8)
    input_driver.hw_press("enter")
    time.sleep(5)

    pos_bs = ctx.vision.wait_for_any_image(
        ["buyandsell-w.png", "buyandsell-b.png"],
        region=ctx.regions["左"],
        threshold=0.75,
        timeout=60,
        interval=0.5,
        fast_mode=True
    )
    if not pos_bs:
        ctx.log("未找到购买与出售")
        return False

    ctx.game_click(pos_bs)
    time.sleep(1.0)
    input_driver.hw_press("pagedown", delay=0.15)
    ctx.log("进入车辆界面...")
    time.sleep(0.5)

    while ctx.cj_counter < target_count:
        if not ctx.is_running:
            return False
        ctx.log("进入我的车辆.")
        input_driver.hw_press("enter")
        time.sleep(2.0)
        input_driver.hw_press("backspace")
        time.sleep(1.0)

        brand_pos = None
        for _ in range(30):
            if not ctx.is_running:
                return False

            brand_pos = ctx.vision.wait_for_any_image(
                ["CCbrand.png"],
                region=ctx.regions["全界面"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if brand_pos:
                break

            input_driver.hw_press("up")
            time.sleep(0.25)

        if not brand_pos:
            ctx.log("选品牌失败")
            return False

        ctx.game_click(brand_pos)
        time.sleep(1.0)

        found_car = False
        for _ in range(85):
            if not ctx.is_running:
                return False
            pos_target = ctx.vision.find_image_with_element(
                "newCC.png",
                "newcartag.png",
                region=ctx.regions["全界面"],
                threshold=0.85,
                fast_mode=False
            )
            if pos_target:
                ctx.game_click(pos_target)
                found_car = True
                break
            for _ in range(4):
                input_driver.hw_press("right", delay=0.05)
                time.sleep(0.08)
            time.sleep(0.4)
            
        if not found_car:
            ctx.log("列表中未找到目标车辆")
            return False
            
        # 此时刚才的 ctx.game_click(pos_target) 已经点中了车，等待右下角菜单弹出
        time.sleep(0.5)
                
        ctx.log("识别上车选项...")
        # 【核心修改】：使用 wait_for_any_image，传入包含两张图片的列表
        pos_shangche = ctx.vision.wait_for_any_image(
            ["rc_normal.png", "rc_hover.png"], 
            region=ctx.regions["全界面"], 
            threshold=0.65, 
            timeout=2.0, 
            interval=0.2,
            fast_mode=True
        )

        # 2. 如果没找到，说明刚才真的只是选中了车，此时我们才补按 Enter
        if not pos_shangche:
            ctx.log("菜单未弹出，补按 Enter 键唤出菜单...")
            input_driver.hw_press("enter")
            time.sleep(1.0)
            pos_shangche = ctx.vision.wait_for_any_image(
                ["rc_normal.png", "rc_hover.png"], 
                region=ctx.regions["全界面"], 
                threshold=0.65, 
                timeout=2.0, 
                interval=0.2,
                fast_mode=True
            )
        
        if pos_shangche:
            ctx.log("点击上车选项")
            ctx.game_click(pos_shangche)
            time.sleep(1.5)

            input_driver.hw_press("enter")
            time.sleep(1.5)
        else:
            ctx.log("识别上车选项超时，执行退回...")
            input_driver.hw_press("esc")
            time.sleep(1.0)
            return False  # 返回 False 触发断点恢复，比一路错下去好得多

        pos_sjy = None
        for _ in range(60):
            if not ctx.is_running:
                return False

            pos_sjy = ctx.vision.wait_for_any_image(
                ["UandT-w.png", "UandT-b.png"],
                region=ctx.regions["左下"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if pos_sjy:
                break

            input_driver.hw_press("esc")
            time.sleep(0.5)

        if not pos_sjy:
            ctx.log("找不到升级页面")
            return False

        ctx.game_click(pos_sjy)
        time.sleep(0.5)

        pos_cls = ctx.vision.wait_for_any_image(
            ["clsldcnw.png", "clsldcnb.png"],
            region=ctx.regions["左下"],
            threshold=0.75,
            timeout=20,
            interval=0.4,
            fast_mode=True
        )
        if not pos_cls:
            ctx.log("找不到熟练度入口")
            return False

        ctx.game_click(pos_cls)
        ctx.log("进入熟练度界面...")
        time.sleep(1.0)

        pos_exp = ctx.vision.wait_for_any_image(
            ["EXPwU.png"],
            region=ctx.regions["左"],
            threshold=0.75,
            timeout=1,
            interval=0.3,
            fast_mode=True
        )

        if pos_exp:
            ctx.log("该车辆技能已点过，跳过计数")
        else:
            time.sleep(1.0)
            input_driver.hw_press("enter")
            time.sleep(1.5)

            for dk in ctx.config["skill_dirs"]:
                if not ctx.is_running:
                    return False
                input_driver.hw_press(dk)
                time.sleep(0.2)
                input_driver.hw_press("enter")
                time.sleep(1.2)
                
            if ctx.vision.find_image("SPNE.png", region=ctx.regions["全界面"], threshold=0.7, fast_mode=True):
                ctx.log("已无技能点或技能已点完，提前结束抽奖！")
                time.sleep(1.0)
                input_driver.hw_press("enter")
                time.sleep(0.8)
                input_driver.hw_press("esc")
                time.sleep(1.0)
                input_driver.hw_press("esc")
                time.sleep(1.0)
                input_driver.hw_press("esc")
                time.sleep(1.0)
                return True
                
            ctx.cj_counter += 1
            ctx.update_running_ui("超级抽奖", ctx.cj_counter, target_count)

        input_driver.hw_press("esc")
        time.sleep(1.2)
        input_driver.hw_press("esc")
        time.sleep(0.8)
        input_driver.hw_press("up", delay=0.15)
        time.sleep(0.8)
        
    input_driver.hw_press("esc")
    time.sleep(1.2)
    input_driver.hw_press("esc")
    time.sleep(1.2)
    return True