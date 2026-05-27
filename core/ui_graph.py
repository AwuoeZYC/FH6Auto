# ==========================================
# --- 节点识别特征配置 (The Identifiers) ---
# ==========================================
# 规定：只在特定需要时验证对应图像，不作全图扫描。
# mode: "ANY" (或关系), "ALL" (且关系)

NODE_IDENTIFIERS = {
    # --- 主菜单 6 大 Tab ---
    "scene_menu_story":    {"mode": "ANY", "images": ["btn_collection_journal.png"]},
    "scene_menu_cars":     {"mode": "ANY", "images": ["btn_buy_new_used.png"]},
    "scene_menu_horizon":  {"mode": "ANY", "images": ["btn_residence.png", "btn_super_wheelspin.png"]}, # OR
    "scene_menu_online":   {"mode": "ANY", "images": ["btn_team.png"]},
    "scene_menu_creative": {"mode": "ANY", "images": ["btn_eventlab.png"]},
    "scene_menu_store":    {"mode": "ANY", "images": ["btn_treasure_map.png"]},

    # --- 买车支线 ---
    "scene_coll_journal":    {"mode": "ANY", "images": ["btn_master_explorer.png"]},
    "scene_master_explorer": {"mode": "ALL", "images": ["text_master_explorer.png", "text_sorted.png"]}, # AND
    "scene_car_collection":  {"mode": "ALL", "images": ["text_car_collection_statement.png", "icon_car_collection_beige.png"]},

    # --- 跑图支线 ---
    "scene_eventlab":   {"mode": "ANY", "images": ["btn_play_event.png"]}, # 蓝图页
    "scene_play_event": {"mode": "ALL", "images": ["title_event.png", "text_view_event_info.png"]}, # 赛事准备页
}

# ==========================================
# --- 节点拓扑寻路地图 (The Directed Graph) ---
# ==========================================
# 规定：每一个键代表当前节点，其值代表可以通过何种动作前往相邻节点。

UI_GRAPH = {
    # ---------------- 1. 环形主菜单 (双向链表) ----------------
    "scene_menu_story": {
        "scene_menu_store":    {"action": "key", "value": "pageup"},   # 向左
        "scene_menu_cars":     {"action": "key", "value": "pagedown"}, # 向右
        "scene_coll_journal":  {"action": "click_image", "value": "btn_collection_journal.png"} # 深入支线
    },
    "scene_menu_cars": {
        "scene_menu_story":    {"action": "key", "value": "pageup"},
        "scene_menu_horizon":  {"action": "key", "value": "pagedown"}
    },
    "scene_menu_horizon": {
        "scene_menu_cars":     {"action": "key", "value": "pageup"},
        "scene_menu_online":   {"action": "key", "value": "pagedown"}
    },
    "scene_menu_online": {
        "scene_menu_horizon":  {"action": "key", "value": "pageup"},
        "scene_menu_creative": {"action": "key", "value": "pagedown"}
    },
    "scene_menu_creative": {
        "scene_menu_online":   {"action": "key", "value": "pageup"},
        "scene_menu_store":    {"action": "key", "value": "pagedown"},
        "scene_eventlab":      {"action": "click_image", "value": "btn_eventlab.png"} # 深入跑图支线
    },
    "scene_menu_store": {
        "scene_menu_creative": {"action": "key", "value": "pageup"},
        "scene_menu_story":    {"action": "key", "value": "pagedown"}
    },

    # ---------------- 2. 买车支线 ----------------
    "scene_coll_journal": {
        "scene_menu_story":      {"action": "key", "value": "esc"}, # 退出返回
        "scene_master_explorer": {"action": "click_image", "value": "btn_master_explorer.png"} # 继续深入
    },
    "scene_master_explorer": {
        "scene_coll_journal":    {"action": "key", "value": "esc"},
        "scene_car_collection":  {"action": "click_image", "value": "btn_car_collection_white.png"}
    },
    "scene_car_collection": {
        "scene_master_explorer": {"action": "key", "value": "esc"}
        # 到达终点，不需要深入的边，具体买车业务由 buy_task.py 接管
    },

    # ---------------- 3. 跑图支线 ----------------
    "scene_eventlab": {
        "scene_menu_creative": {"action": "key", "value": "esc"},
        "scene_play_event":    {"action": "click_image", "value": "btn_play_event.png"}
    },
    "scene_play_event": {
        "scene_eventlab":      {"action": "key", "value": "esc"}
        # 到达终点，由 race_task.py 接管
    }
}