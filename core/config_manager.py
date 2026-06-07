import os
import json
from config import CONFIG_FILE

class ConfigManager:
    """全局配置中心单例，接管所有存盘与默认配置初始化"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init_config()
        return cls._instance
        
    def _init_config(self):
        # 1. 初始化应用的静态默认配比 (应用你要求的全新 99:33:33:33 比例)
        self.config = {
            "target_vehicle": "Subaru_22B",
            "race_count": 99,
            "buy_count": 33,
            "mastery_count": 33,
            "remove_count": 33,
            "chk_1": True,
            "chk_2": True,
            "chk_3": True,
            "chk_4": True,
            "next_1": 2,
            "next_2": 3,
            "next_3": 4,
            "next_4": 1,
            "global_loops": 10,
            "skill_dirs": ["right", "up", "up", "up", "left"],
            "share_code": "170516901",
            "auto_restart": False,
            "restart_cmd": "start steam://run/2483190",
            "base_width": 1024,  
            "base_height": 768, 
        }
        # 2. 自动加载本地文件，覆盖默认值
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception:
                pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass