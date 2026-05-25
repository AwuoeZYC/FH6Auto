import time
import core.input_driver as input_driver

def run_buy(ctx, target_count):
    if ctx.car_counter >= target_count:
        return True

    ctx.update_running_ui("批量买车", ctx.car_counter, target_count)

    ctx.log("准备验证/进入菜单...")
    if not ctx.enter_menu():
        return False

    pos = ctx.vision.wait_for_image(
        "collectionjournal.png",
        region=ctx.regions["左"],
        threshold=0.7,
        timeout=30,
        interval=0.4,
        fast_mode=True
    )
    if not pos:
        ctx.log("未找到收集簿")
        return False

    ctx.game_click(pos, double=True)
    time.sleep(0.6)

    pos = ctx.vision.wait_for_image(
        "masterexplorer.png",
        region=ctx.regions["全界面"],
        threshold=0.75,
        timeout=30,
        interval=0.4,
        fast_mode=True
    )
    if not pos:
        ctx.log("未找到探索")
        return False

    ctx.game_click(pos, double=True)
    time.sleep(0.6)

    pos = ctx.vision.wait_for_image(
        "carcollection.png",
        region=ctx.regions["全界面"],
        threshold=0.75,
        timeout=30,
        interval=0.3,
        fast_mode=True
    )
    if not pos:
        ctx.log("未找到车辆收集")
        return False

    ctx.game_click(pos, double=True)
    time.sleep(1.0)

    input_driver.hw_press("backspace")
    time.sleep(0.5)

    brand_pos = None
    for _ in range(20):
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
        ctx.log("未找到品牌")
        return False

    ctx.game_click(brand_pos)
    time.sleep(0.8)
    input_driver.hw_press("down")
    time.sleep(0.4)

    pos_22b = ctx.vision.wait_for_image(
        "consumablecar.png",
        region=ctx.regions["全界面"],
        threshold=0.75,
        timeout=8,
        interval=0.3,
        fast_mode=True
    )
    if not pos_22b:
        ctx.log("未找到消耗品车辆")
        return False

    ctx.game_click(pos_22b, double=True)
    time.sleep(1.0)

    while ctx.car_counter < target_count:
        if not ctx.is_running:
            return False

        input_driver.hw_press("space")
        time.sleep(0.6)
        input_driver.hw_press("down")
        time.sleep(0.2)
        input_driver.hw_press("enter")
        time.sleep(0.6)
        input_driver.hw_press("enter")
        time.sleep(0.6)
        input_driver.hw_press("enter")
        time.sleep(0.7)

        ctx.car_counter += 1
        ctx.update_running_ui("批量买车", ctx.car_counter, target_count)

    for _ in range(5):
        if not ctx.is_running:
            return False
        input_driver.hw_press("esc")
        time.sleep(0.8)

    return True