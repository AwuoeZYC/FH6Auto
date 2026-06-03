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

def find_with_roi_features(ctx, anchor_image: str, features: dict, anchor_threshold: float = 0.8, feature_threshold: float = 0.8, padding: int = 20):
    """
    高级 ROI 复合特征检索引擎 (单目标极速最佳匹配版)
    利用 OpenCV 默认的全局极值检索，消除多目标遍历造成的盲区与性能损耗。
    """
    if not ctx.is_running(): 
        raise BotStoppedException("🚨 视觉引擎收到 F8 停止指令！")

    # 1. 回退至极速单次全屏搜索，只取全图最像的那一个锚点
    anchor_pos = ctx.find_image(anchor_image, threshold=anchor_threshold)
    if not anchor_pos:
        return None
        
    # 2. 计算该最佳目标的 ROI 区域
    try:
        roi_region = calculate_dynamic_roi(ctx, anchor_image, anchor_pos, padding=padding)
    except Exception as e:
        ctx.log(f"🚨 ROI计算异常跳过: {e}")
        return None

    # 3. 遍历特征要求字典进行三维查验
    for feature_img, is_required in features.items():
        if not ctx.is_running(): 
            raise BotStoppedException("🚨 视觉引擎收到 F8 停止指令！")
            
        # 排斥特征（False）依然保持极高敏感度
        current_thresh = feature_threshold if is_required else max(0.6, feature_threshold - 0.15)
        
        feat_pos = ctx.find_image(feature_img, region=roi_region, threshold=current_thresh)
        
        if is_required:
            if not feat_pos:
                return None  # 缺少必须特征，直接否定当前最佳目标
        else:
            if feat_pos:
                return None  # 发现了排斥特征，直接否定当前最佳目标
                
    # 4. 经受住所有特征验证，返回坐标
    return anchor_pos