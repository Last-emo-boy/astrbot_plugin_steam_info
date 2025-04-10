import json
import os
import time
from typing import Any, Dict, List, Optional

# -----------------------------
# BindData 用于存储用户绑定数据
# 数据结构：{ parent_id: { user_id: { "steam_id": "xxx", "nickname": "xxx" } } }
# -----------------------------
class BindData:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Load BindData error: {e}")
        return {}

    def get(self, parent_id: str, user_id: Optional[str] = None) -> Any:
        if parent_id not in self.content:
            return None
        if user_id is None:
            return self.content.get(parent_id)
        return self.content.get(parent_id, {}).get(user_id)

    def add(self, parent_id: str, data: Dict[str, Any]) -> None:
        if parent_id not in self.content:
            self.content[parent_id] = {}
        user_id = data.get("user_id")
        if user_id:
            self.content[parent_id][user_id] = data

    def remove(self, parent_id: str, user_id: str) -> None:
        if parent_id in self.content and user_id in self.content[parent_id]:
            del self.content[parent_id][user_id]

    def save(self) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.content, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Save BindData error: {e}")

# -----------------------------
# SteamInfoData 用于存储 Steam 用户信息缓存
# 通常存储 API 返回的完整数据，且提供比较与查询方法
# -----------------------------
class SteamInfoData:
    def __init__(self, file_path: str):
        self.file_path = file_path
        # 内部 data 保存结构应与 API 返回数据一致，如： { "response": { "players": [...] } }
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Load SteamInfoData error: {e}")
        return {"response": {"players": []}}

    def save(self) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Save SteamInfoData error: {e}")

    def update_by_players(self, players: List[Dict[str, Any]]) -> None:
        """将最新查询到的玩家数据覆盖内部数据。"""
        self.data = {"response": {"players": players}}

    def get_players(self, steam_ids: List[str]) -> List[Dict[str, Any]]:
        """从缓存数据中筛选出 steamid 在 steam_ids 列表中的玩家数据。"""
        result = []
        for player in self.data.get("response", {}).get("players", []):
            if player.get("steamid") in steam_ids:
                result.append(player)
        return result

    def compare(self, old_players: List[Dict[str, Any]], new_players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对比旧、新的玩家数据，返回变化记录列表。  
        每条记录格式：
          {
            "type": "start" | "stop" | "change" | "error",
            "player": new_player,
            "old_player": old_player (可能为 None)
          }
        实现逻辑（简单示例）：
          - 若新数据有 gameextrainfo 而旧数据没有，则为 "start"
          - 若旧数据有 gameextrainfo 而新数据没有，则为 "stop"
          - 若两者均有且不相同，则为 "change"
        """
        changes = []
        # 构建旧数据索引，按 steamid 建立字典
        old_dict = {player.get("steamid"): player for player in old_players}
        for new in new_players:
            sid = new.get("steamid")
            old = old_dict.get(sid)
            new_game = new.get("gameextrainfo")
            old_game = old.get("gameextrainfo") if old else None
            if new_game and not old_game:
                changes.append({"type": "start", "player": new})
            elif old_game and not new_game:
                changes.append({"type": "stop", "player": new, "old_player": old})
            elif new_game and old_game and new_game != old_game:
                changes.append({"type": "change", "player": new, "old_player": old})
            # 可根据需要扩展其他逻辑
        return changes

# -----------------------------
# ParentData 用于存储群相关信息（例如头像和名称）
# 数据结构：{ parent_id: {"avatar": "avatar_path", "name": "group name"} }
# -----------------------------
class ParentData:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data: Dict[str, Dict[str, str]] = self._load()

    def _load(self) -> Dict[str, Dict[str, str]]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Load ParentData error: {e}")
        return {}

    def get(self, parent_id: str) -> (str, str):
        """返回 (avatar, name)；若不存在，则返回空字符串。"""
        info = self.data.get(parent_id, {})
        return info.get("avatar", ""), info.get("name", "")

    def update(self, parent_id: str, avatar: str, name: str) -> None:
        self.data[parent_id] = {"avatar": avatar, "name": name}
        self.save()

    def save(self) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Save ParentData error: {e}")

# -----------------------------
# DisableParentData 用于存储被禁用播报的群 ID
# 数据结构：{ parent_id: True }
# -----------------------------
class DisableParentData:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data: Dict[str, bool] = self._load()

    def _load(self) -> Dict[str, bool]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Load DisableParentData error: {e}")
        return {}

    def is_disabled(self, parent_id: str) -> bool:
        return self.data.get(parent_id, False)

    def add(self, parent_id: str) -> None:
        self.data[parent_id] = True
        self.save()

    def remove(self, parent_id: str) -> None:
        if parent_id in self.data:
            del self.data[parent_id]
            self.save()

    def save(self) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Save DisableParentData error: {e}")
