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
# def find_with_roi_features(ctx, anchor_image: str, features: dict, anchor_threshold: float = 0.8, feature_threshold: float = 0.8, padding: int = 20):
#     """
#     高级 ROI 复合特征检索引擎 (单目标极速最佳匹配版)
#     利用 OpenCV 默认的全局极值检索，消除多目标遍历造成的盲区与性能损耗。
#     """
#     if not ctx.is_running(): 
#         raise BotStoppedException("🚨 视觉引擎收到 F8 停止指令！")

#     # 1. 回退至极速单次全屏搜索，只取全图最像的那一个锚点
#     anchor_pos = ctx.find_image(anchor_image, threshold=anchor_threshold)
#     if not anchor_pos:
#         return None
        
#     # 2. 计算该最佳目标的 ROI 区域
#     try:
#         roi_region = calculate_dynamic_roi(ctx, anchor_image, anchor_pos, padding=padding)
#     except Exception as e:
#         ctx.log(f"🚨 ROI计算异常跳过: {e}")
#         return None

#     # 3. 遍历特征要求字典进行三维查验
#     for feature_img, is_required in features.items():
#         if not ctx.is_running(): 
#             raise BotStoppedException("🚨 视觉引擎收到 F8 停止指令！")
            
#         # 排斥特征（False）依然保持极高敏感度
#         current_thresh = feature_threshold if is_required else max(0.6, feature_threshold - 0.15)
        
#         feat_pos = ctx.find_image(feature_img, region=roi_region, threshold=current_thresh)
        
#         if is_required:
#             if not feat_pos:
#                 return None  # 缺少必须特征，直接否定当前最佳目标
#         else:
#             if feat_pos:
#                 return None  # 发现了排斥特征，直接否定当前最佳目标
                
#     # 4. 经受住所有特征验证，返回坐标
#     return anchor_pos