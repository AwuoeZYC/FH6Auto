import cv2
import os

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

def find_with_roi_features(ctx, anchor_image: str, features: dict, anchor_threshold: float = 0.8, feature_threshold: float = 0.8, padding: int = 20):
    """
    高级 ROI 复合特征检索引擎 (带人类阅读顺序排序与坐标追踪)。
    """
    # 1. 寻找画面中【所有】符合条件的锚点
    anchor_positions = ctx.find_all_images(anchor_image, threshold=anchor_threshold)
    if not anchor_positions:
        return None
        
    # 【核心升级 1】：对找到的所有嫌疑目标进行强制排序！
    # 按照 Y 坐标（行）优先，X 坐标（列）其次进行排序。
    # 考虑到同一行可能有几个像素的误差，将 Y 坐标除以 50 取整来进行粗略分行
    anchor_positions.sort(key=lambda pt: (pt[1] // 50, pt[0]))

    # 2. 遍历所有找到的锚点，挨个进行三维立体查验
    for i, anchor_pos in enumerate(anchor_positions, 1):
        if not ctx.is_running(): 
            return None
        # ctx.log(f"🔎 正在排查第 {i}/{len(anchor_positions)} 个目标，屏幕坐标: ({anchor_pos[0]}, {anchor_pos[1]})")
        
        try:
            roi_region = calculate_dynamic_roi(ctx, anchor_image, anchor_pos, padding=padding)
        except Exception as e:
            ctx.log(f"🚨 ROI计算异常跳过: {e}")
            continue

        # 3. 遍历特征要求字典进行查验
        anchor_valid = True
        for feature_img, is_required in features.items():
            
            # 【核心升级 2】：如果是排斥特征（False），降低阈值使其极其敏感，宁可错杀绝不漏放卖掉新车！
            current_thresh = feature_threshold if is_required else max(0.6, feature_threshold - 0.15)
            
            feat_pos = ctx.find_image(feature_img, region=roi_region, threshold=current_thresh)
            
            if is_required:
                if not feat_pos:
                    # ctx.log(f"   ❌ 排除: 缺少必须特征 [{feature_img}]")
                    anchor_valid = False
                    break
            else:
                if feat_pos:
                    # ctx.log(f"   ❌ 排除: 发现了排斥特征 [{feature_img}] (相似度过高)")
                    anchor_valid = False
                    break
                
        # 4. 如果该锚点经受住了所有特征验证，则直接返回该锚点坐标
        if anchor_valid:
            # ctx.log(f"🎯 【视觉引擎】 完美锁定目标！坐标: ({anchor_pos[0]}, {anchor_pos[1]})")
            return anchor_pos
            
    # 所有嫌疑目标都排查完了，没一个符合要求的
    return None
