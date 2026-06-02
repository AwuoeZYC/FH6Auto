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

def find_with_roi_features(ctx, anchor_image: str, features: dict, anchor_threshold: float = 0.7, feature_threshold: float = 0.7, padding: int = 20):
    """
    高级 ROI 复合特征检索引擎 (多点遍历防漏版)。
    """
    # 1. 寻找画面中【所有】符合条件的锚点（打破单目标陷阱）
    anchor_positions = ctx.find_all_images(anchor_image, threshold=anchor_threshold)
    if not anchor_positions:
        return None
        
    # 2. 遍历所有找到的锚点，挨个进行三维立体查验
    for anchor_pos in anchor_positions:
        try:
            roi_region = calculate_dynamic_roi(ctx, anchor_image, anchor_pos, padding=padding)
        except Exception as e:
            ctx.log(f"🚨 ROI计算异常跳过: {e}")
            continue

        # 3. 遍历特征要求字典进行查验
        anchor_valid = True
        for feature_img, is_required in features.items():
            # 此时底层的找图会自动采用全屏尺寸计算缩放比，消除了畸变
            feat_pos = ctx.find_image(feature_img, region=roi_region, threshold=feature_threshold)
            
            if is_required and not feat_pos:
                anchor_valid = False
                break
            if not is_required and feat_pos:
                anchor_valid = False
                break
                
        # 4. 如果该锚点经受住了所有特征验证，则直接返回该锚点坐标
        if anchor_valid:
            return anchor_pos
            
    # 所有嫌疑目标都排查完了，没一个符合要求的
    return None