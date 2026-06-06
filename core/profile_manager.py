import os
import json

class ProfileManager:
    """车辆档案全局单例管理器，切断各模块对 UI 的数据依赖"""
    _instance = None
    _profiles = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProfileManager, cls).__new__(cls)
        return cls._instance

    def load_profiles(self, filepath: str = "config/vehicle_profiles.json"):
        if not os.path.exists(filepath):
            # 如果文件不存在，给一个空字典兜底或抛出异常，防止程序崩溃
            self._profiles = {}
            return

        with open(filepath, "r", encoding="utf-8") as f:
            self._profiles = json.load(f)

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