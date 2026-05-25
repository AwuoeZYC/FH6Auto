import time
import core.input_driver as input_driver

def run_sell(ctx, target_count):
    if ctx.sc_count >= target_count:
        return True

    ctx.update_running_ui("移除车辆", ctx.sc_count, target_count)

    ctx.log("准备验证/进入菜单！！！使用前请人工核验到正常移除车辆再进行自动化移除处理")
    if not ctx.enter_menu():
        return False

    ctx.log("进入车辆与收藏！！！使用前请人工核验到正常移除车辆再进行自动化移除处理")
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
        region=ctx.regions["上"],
        threshold=0.75,
        timeout=40,
        interval=0.5,
        fast_mode=True
    )
    if not pos_bs:
        ctx.log("未找到购买与出售")
        return False

    ctx.game_click(pos_bs)
    time.sleep(1.0)

    input_driver.hw_press("pagedown", delay=0.15)
    time.sleep(1.0)

    input_driver.hw_press("enter")  
    time.sleep(2.0)
    
    input_driver.hw_press("y") 
    time.sleep(1.0)
    input_driver.hw_press("enter")
    time.sleep(0.8)
    input_driver.hw_press("esc") 
    time.sleep(1.5)
    
    input_driver.hw_press("enter")
    time.sleep(0.8)
    ctx.move_to_game_coord(5, 5)
    time.sleep(0.2)
    
    pos = ctx.vision.wait_for_image(
        "rc.png",
        region=ctx.regions["全界面"],
        threshold=0.65,
        timeout=5,
        interval=0.2,
        fast_mode=True
    )
    if pos:
        ctx.log("找到上车，执行点击")
        ctx.game_click(pos) 
        time.sleep(2.0)
    else:
        ctx.log("该车辆已经驾驶，或未找到图片，执行两次ESC")
        input_driver.hw_press("esc")
        time.sleep(1.5)
        input_driver.hw_press("esc")
    time.sleep(2.0)

    found = False
    for i in range(30):
        if not ctx.is_running:
            return False
        pos = ctx.vision.wait_for_any_image(
            ["buyandsell-b.png", "buyandsell-w.png"],
            region=ctx.regions["上"],
            threshold=0.70,
            timeout=0.8,
            interval=0.2,
            fast_mode=True
        )
        if pos:
            ctx.log(f"第 {i + 1} 次检测到购买与出售，进入车辆界面")
            input_driver.hw_press("enter")
            found = True
            break
        ctx.log(f"第 {i + 1} 次未检测到购买与出售，等待后重试")
        time.sleep(1.0)
        
    if not found:
        ctx.log("30次内未找到购买与出售")
        return False
    
    time.sleep(1.5)
    input_driver.hw_press("x")
    time.sleep(0.5)
    ctx.move_to_game_coord(5, 5)
    
    ctx.log("切换到 最近获得 的排序...")
    for _ in range(6):
        if not ctx.is_running:
            return False
        input_driver.hw_press("down")
        time.sleep(0.25)
    time.sleep(0.2)
    input_driver.hw_press("enter")
    time.sleep(1.2)
    ctx.log("回到最近获得的前面")
    
    input_driver.hw_press("backspace")
    time.sleep(0.8)
    input_driver.hw_press("enter")
    time.sleep(1.5)

    ctx.log("开始删除最近获得的车辆！！！请人工确认是否移除")

    while ctx.sc_count < target_count:
        ctx.log(f"is_running = {ctx.is_running}")
        if not ctx.is_running:
            return False
            
        input_driver.hw_press("enter")
        time.sleep(1.2)
        
        for _ in range(6):
            if not ctx.is_running:
                return False
            input_driver.hw_press("down")
            time.sleep(0.2)
            
        input_driver.hw_press("enter")
        time.sleep(0.5)
        input_driver.hw_press("down")
        time.sleep(0.3)
        input_driver.hw_press("enter")
        time.sleep(0.8)
        
        ctx.sc_count += 1
        ctx.log(f"已尝试删除车辆 {ctx.sc_count}/{target_count}")

    for _ in range(3):
        if not ctx.is_running:
            return False
        input_driver.hw_press("esc")
        time.sleep(1.0)

    return True