import time
import core.input_driver as input_driver

def run_race(ctx, target_count, share_code):
    """
    循环跑图业务逻辑
    :param ctx: 上下文对象 (即 main.py 中的 FH_UltimateBot 实例)
    :param target_count: 目标跑图次数
    :param share_code: 蓝图共享代码
    """
    if ctx.race_counter >= target_count:
        return True

    ctx.update_running_ui("循环跑图", ctx.race_counter, target_count)

    ctx.log("准备验证/进入菜单...")
    if not ctx.enter_menu():
        return False

    ctx.log("切换到创意中心...")
    for _ in range(4):
        input_driver.hw_press("pagedown", delay=0.15)
        time.sleep(0.3)

    time.sleep(0.8)

    pos_el = ctx.vision.wait_for_any_image(
        ["eventlab.png", "eventlabcar.png"],
        region=ctx.regions["全界面"],
        threshold=0.5,
        timeout=5,
        interval=0.25,
        fast_mode=True
    )
    if not pos_el:
        ctx.log("未找到 eventlab")
        return False

    ctx.game_click(pos_el)
    time.sleep(1.2)

    pos_yg = ctx.vision.wait_for_image(
        "playenent.png",
        region=ctx.regions["中间"],
        threshold=0.75,
        timeout=40,
        interval=0.3,
        fast_mode=True
    )
    if not pos_yg:
        ctx.log("未找到游玩赛事")
        return False

    ctx.game_click(pos_yg)
    time.sleep(1.5)

    input_driver.hw_press("backspace")
    time.sleep(0.8)
    input_driver.hw_press("up")
    time.sleep(0.4)
    input_driver.hw_press("enter")
    time.sleep(0.8)

    # 提取纯数字共享代码并输入
    code_text = "".join(c for c in share_code if c.isdigit())
    for char in code_text:
        if not ctx.is_running:
            return False
        if char in input_driver.DIK_CODES:
            input_driver.hw_press(char, delay=0.05)
            time.sleep(0.05)

    time.sleep(0.4)
    input_driver.hw_press("enter")
    time.sleep(0.8)
    input_driver.hw_press("down")
    time.sleep(0.3)
    input_driver.hw_press("enter")
    time.sleep(1.5)

    pos_ck = ctx.vision.wait_for_image(
        "VEI.png",
        region=ctx.regions["下"],
        threshold=0.75,
        timeout=100,
        interval=1.0,
        fast_mode=True
    )
    if not pos_ck:
        ctx.log("链接超时")
        return False

    input_driver.hw_press("enter")
    time.sleep(1.5)
    input_driver.hw_press("enter")
    time.sleep(2.0)

    pos_target = ctx.vision.wait_for_image_with_element_multi(
        "skillcar.png",
        "liketag.png",
        region=ctx.regions["全界面"],
        fast_mode=False,
        main_threshold=0.60,
        like_threshold=0.7,
        final_threshold=0.7,
        timeout=10,
        interval=0.25
    )

    if not pos_target:
        ctx.log("未找到带 liketag 的目标车辆，重新选品牌...")
        input_driver.hw_press("backspace")
        time.sleep(1.2)

        found_brand = False
        for _ in range(3):
            if not ctx.is_running:
                return False

            pos_brand = ctx.vision.wait_for_image(
                "skillcarbrand.png",
                region=ctx.regions["全界面"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if pos_brand:
                ctx.game_click(pos_brand)
                time.sleep(1.2)
                found_brand = True
                break

            input_driver.hw_press("up")
            time.sleep(0.4)

        if not found_brand:
            ctx.log("三次尝试未找到刷图车辆品牌。")
            return False

        for _ in range(200):
            if not ctx.is_running:
                return False

            pos_target = ctx.vision.wait_for_image_with_element(
                "skillcar.png",
                "liketag.png",
                region=ctx.regions["全界面"],
                threshold=0.8,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if pos_target:
                break

            for _ in range(4):
                input_driver.hw_press("right", delay=0.08)
                time.sleep(0.08)
            time.sleep(0.4)

    if not pos_target:
        ctx.log("翻页未能找到带有 liketag 的刷图车辆！")
        return False

    ctx.game_click(pos_target)
    time.sleep(0.5)
    input_driver.hw_press("enter")
    time.sleep(4.0)

    ctx.log("前置完成，开始循环跑图！")

    while ctx.race_counter < target_count:
        if not ctx.is_running:
            return False

        ctx.log(f"跑图 {ctx.race_counter + 1}/{target_count}: 找赛事起点...")

        pos = None
        for _ in range(1500):
            if not ctx.is_running:
                return False

            pos = ctx.vision.wait_for_any_image(
                ["start.png", "startw.png"],
                region=ctx.regions["左下"],
                threshold=0.75,
                timeout=0.7,
                interval=0.2,
                fast_mode=True
            )
            if pos:
                break

            input_driver.hw_press("down")
            time.sleep(0.25)

        if not pos:
            ctx.log("找不到赛事起点，退出跑图。")
            return False

        ctx.game_click(pos)
        time.sleep(4.0)
        input_driver.hw_key_down("w")

        start_w = time.time()
        e_pressed = 0
        last_chk = 0
        finished = False

        while ctx.is_running:
            elap = time.time() - start_w

            if elap >= 3.0 and e_pressed == 0:
                input_driver.hw_press("e")
                e_pressed = 1
            elif elap >= 5.0 and e_pressed == 1:
                input_driver.hw_press("e")
                e_pressed = 2

            if time.time() - last_chk >= 1.0:
                if ctx.vision.find_image("restart.png", region=ctx.regions["下"], threshold=0.75, fast_mode=True):
                    finished = True
                    break
                last_chk = time.time()

            time.sleep(0.3)

        input_driver.hw_key_up("w")

        if not finished or not ctx.is_running:
            return False

        if ctx.race_counter == target_count - 1:
            input_driver.hw_press("enter")
            time.sleep(2.0)
        else:
            input_driver.hw_press("x")
            time.sleep(0.8)
            input_driver.hw_press("enter")
            time.sleep(2.0)

        ctx.race_counter += 1
        ctx.update_running_ui("循环跑图", ctx.race_counter, target_count)

    return True