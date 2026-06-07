import os
import json
import shutil

class ProfileManager:
    """车辆档案全局单例管理器，切断各模块对 UI 的数据依赖"""
    _instance = None
    _profiles = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProfileManager, cls).__new__(cls)
        return cls._instance
    
    def _extract_default_profile(self, target_filepath: str):
        """核心机制：从 exe 内部临时目录释放默认的车辆 JSON 配置到外部工作区"""
        # 判断是否是 PyInstaller 打包环境
        if hasattr(sys, '_MEIPASS'):
            internal_path = os.path.join(sys._MEIPASS, 'config', 'vehicle_profiles.json')
        else:
            # 源码运行环境兜底
            internal_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'vehicle_profiles.json')
            
        internal_path = os.path.abspath(internal_path)
        target_abs_path = os.path.abspath(target_filepath)

        # 如果内部文件存在，且路径与外部不冲突（防止开发时自己覆盖自己）
        if os.path.exists(internal_path) and internal_path != target_abs_path:
            os.makedirs(os.path.dirname(target_abs_path), exist_ok=True)
            try:
                shutil.copy2(internal_path, target_abs_path)
                print(f"✅ [自我修复] 已在本地生成默认车辆配置文件: {target_abs_path}")
            except Exception as e:
                print(f"⚠️ [自我修复失败] 无法释放默认配置: {e}")

    def load_profiles(self, filepath: str = "config/vehicle_profiles.json"):
        # 1. 环境感知：如果外部文件不存在，尝试从 EXE 内部“吐”出一份默认配置
        if not os.path.exists(filepath):
            self._extract_default_profile(filepath)

        # 2. 极限兜底：如果依然不存在（比如打包没带上该文件），提供空字典防止程序崩溃
        if not os.path.exists(filepath):
            print("🚨 严重警告: 无法加载车辆配置文件，UI 将无法渲染可选车辆！")
            self._profiles = {}
            return

        # 3. 正常读取外部配置文件
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self._profiles = json.load(f)
        except Exception as e:
            print(f"🚨 解析 vehicle_profiles.json 失败，请检查格式: {e}")
            self._profiles = {}

    def get_profile(self, vehicle_id: str) -> dict:
        return self._profiles.get(vehicle_id, {})

    def get_available_vehicles(self) -> list:
        """返回给 UI 下拉框使用的数据格式: [(id, display_name), ...]"""
        return [(vid, data.get("display_name", vid)) for vid, data in self._profiles.items()]

    def get_asset(self, vehicle_id: str, task_id: str, asset_key: str, is_global: bool = False):
        """精准提取资产名称，向下兼容原有的 is_global 逻辑"""
        profile = self.get_profile(vehicle_id)
        if not profile:
            return None
            
        if is_global:
            return profile.get(asset_key)
        return profile.get("tasks", {}).get(task_id, {}).get(asset_key)

    def get_features(self, vehicle_id: str, task_id: str) -> dict:
        """提取高阶特征字典"""
        profile = self.get_profile(vehicle_id)
        if not profile:
            return None
        return profile.get("tasks", {}).get(task_id, {}).get("features")
    
    def get_cost_cr(self, vehicle_id: str) -> int:
        """获取单车购买所需的CR成本"""
        return self.get_profile(vehicle_id).get("cost_cr")

    def get_skill_sp(self, vehicle_id: str) -> int:
        """获取单车加点所需的SP技能点数"""
        return self.get_profile(vehicle_id).get("skill_sp")