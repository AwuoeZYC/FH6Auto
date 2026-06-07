import cv2
import os
from core.interaction import BotStoppedException

def calculate_dynamic_roi(ctx, image_name: str, center_pos: tuple, padding: int = 0) -> tuple:
    """
    动态计算 ROI 包围盒。遇到异常直接抛出，绝不使用魔术数字兜底。
    """
    x, y = center_pos
    base_w, base_h = ctx.base_res
    folder = ctx.vision._get_aspect_ratio_folder(base_w, base_h)
    actual_path = ctx.vision._resolve_template_path(ctx.search_dirs, folder, image_name)
    
    if not os.path.exists(actual_path):
        # 直接抛出错误，拒绝模糊处理
        raise FileNotFoundError(f"计算 ROI 失败: 找不到原图像文件 {actual_path}")
        
    img = cv2.imread(actual_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"计算 ROI 失败: OpenCV 无法解码图像 {actual_path}")
        
    h, w = img.shape[:2]
    
    roi_x = max(0, int(x - (w / 2) - padding))
    roi_y = max(0, int(y - (h / 2) - padding))
    roi_w = int(w + padding * 2)
    roi_h = int(h + padding * 2)
    
    return (roi_x, roi_y, roi_w, roi_h)

def find_with_roi_features(ctx, anchor_image: str, features: dict, anchor_threshold: float = 0.8, feature_threshold: float = 0.8, padding: int = 20, scan_mode: str = "fast"):
    """
    高级 ROI 复合特征检索引擎
    - fast: 利用全局极值，极速返回单一最强匹配目标。
    - comprehensive: 扫描全图所有目标，按空间顺序（从左到右，从上到下）逐一校验特征，消除多目标检索盲区。
    """
    if not ctx.is_running(): 
        raise BotStoppedException("🚨 视觉引擎收到 F8 停止指令！")

    if scan_mode == "fast":
        # 极速模式：单次全屏搜索，只取全图最像的那一个锚点
        anchor_pos = ctx.find_image(anchor_image, threshold=anchor_threshold)
        anchors = [anchor_pos] if anchor_pos else []
    else:
        # 详尽模式：获取所有符合阈值的锚点，并进行空间排序
        anchors = ctx.find_all_images(anchor_image, threshold=anchor_threshold)
        if anchors:
            # 空间排序：按 X 坐标分组（使用 50 像素作为容差消除微小错位），再按 Y 坐标排序
            # 完美契合车库网格 A1,A2,A3, B1,B2,B3 的遍历需求
            anchors.sort(key=lambda pos: (pos[0] // 50, pos[1]))

    if not anchors:
        return None

    # 依次校验所有捕获到的锚点
    for anchor_pos in anchors:
        try:
            # TODO: calculate_dynamic_roi 依赖你的外部实现，这里保持原样调用
            roi_region = calculate_dynamic_roi(ctx, anchor_image, anchor_pos, padding=padding)
        except Exception as e:
            ctx.log(f"🚨 ROI计算异常跳过: {e}")
            continue

        is_valid = True
        for feature_img, is_required in features.items():
            if not ctx.is_running(): 
                raise BotStoppedException("🚨 视觉引擎收到 F8 停止指令！")
                
            current_thresh = feature_threshold if is_required else max(0.6, feature_threshold - 0.15)
            feat_pos = ctx.find_image(feature_img, region=roi_region, threshold=current_thresh)
            
            if is_required and not feat_pos:
                is_valid = False
                break
            elif not is_required and feat_pos:
                is_valid = False
                break
                
        if is_valid:
            return anchor_pos  # 找到第一个经受住所有特征验证的锚点，立即返回

    return None

def read_screen_number(ctx, anchor_img: str, digit_tpl_path: str, base_offset_x: int, base_offset_y: int, base_roi_w: int, base_roi_h: int, threshold: float = 0.92) -> int:
    """
    轻量级模板匹配数字读取引擎 (附带全分辨率自适应缩放)
    """
    anchor_pos = ctx.find_image(anchor_img)
    if not anchor_pos:
        ctx.log(f"⚠️ [SP识别] 未能在当前画面中找到锚点图标 [{anchor_img}]")
        return -1
        
    # --- 【新增】：计算全分辨率自适应缩放因子 ---
    base_w, base_h = ctx.base_res
    curr_w, curr_h = ctx.game_region[2], ctx.game_region[3]
    
    scale_x = curr_w / float(base_w)
    scale_y = curr_h / float(base_h)
    
    # 将基于 1024x768 测量的“基准值”映射为当前屏幕的“物理像素真实值”
    real_offset_x = int(base_offset_x * scale_x)
    real_offset_y = int(base_offset_y * scale_y)
    real_roi_w = int(base_roi_w * scale_x)
    real_roi_h = int(base_roi_h * scale_y)
    
    # 2. 划定数字所在的精准 ROI 区域 (使用映射后的真实像素)
    start_x = int(anchor_pos[0] + real_offset_x)
    start_y = int(anchor_pos[1] + real_offset_y)
    roi_region = (start_x, start_y, real_roi_w, real_roi_h)
    
    # ctx.log(f"🔍 [SP识别] 分辨率倍率: {scale_x:.2f}x. 真实划定ROI: 左上角({start_x}, {start_y}), 宽{real_roi_w}, 高{real_roi_h}")
    
    digits = []
    
    # 3. 遍历 0-9 模板，搜集 ROI 内所有的数字碎片
    for i in range(10):
        img_name = digit_tpl_path.format(i)
        # 注意：寻找碎片依然在这个真实物理框里找
        matches = ctx.find_all_images(img_name, region=roi_region, threshold=threshold)
        
        for match_pos in matches:
            digits.append({'val': i, 'x': match_pos[0]})
            
    if not digits:
        ctx.log("⚠️ [SP识别] 锚点正常，但框内未能识别出任何数字！")
        return -1
        
    # 4. 根据 X 轴坐标从左到右排序，重组为整数
    # 增加一个小容差机制：如果两个数字靠得特别近(比如重叠了像素)，过滤掉重复识别的假阳性
    digits.sort(key=lambda d: d['x'])
    filtered_digits = [digits[0]]
    for d in digits[1:]:
        # 如果 X 轴间距大于 5 个物理像素，才认为是新的数字
        if d['x'] - filtered_digits[-1]['x'] > 5 * scale_x:
            filtered_digits.append(d)
            
    num_str = "".join([str(d['val']) for d in filtered_digits])
    
    # ctx.log(f"🎯 [SP识别] 碎片拼合完成！读取结果: {num_str}")
    return int(num_str)