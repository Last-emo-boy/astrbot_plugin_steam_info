from typing import TypedDict, List

class Player(TypedDict):
    steamid: str
    communityvisibilitystate: int
    profilestate: int
    personaname: str
    profileurl: str
    avatar: str
    avatarmedium: str
    avatarfull: str
    avatarhash: str
    lastlogoff: int
    personastate: int
    realname: str
    primaryclanid: str
    timecreated: int
    personastateflags: int
    # 可根据需要添加 gameextrainfo、gameid 等字段

class PlayerSummariesResponse(TypedDict):
    players: List[Player]

class PlayerSummaries(TypedDict):
    response: PlayerSummariesResponse

class ProcessedPlayer(Player):
    game_start_time: int  # Unix 时间戳

class PlayerSummariesProcessedResponse(TypedDict):
    players: List[ProcessedPlayer]

class Achievements(TypedDict):
    name: str
    image: bytes

class GameData(TypedDict):
    game_name: str
    play_time: str      # 例如 "10.2"
    last_played: str    # 例如 "10月2日"
    game_image: bytes
    achievements: List[Achievements]
    completed_achievement_number: int
    total_achievement_number: int

class PlayerData(TypedDict):
    steamid: str
    player_name: str
    background: bytes
    avatar: bytes
    description: str
    recent_2_week_play_time: str
    game_data: List[GameData]

class DrawPlayerStatusData(TypedDict):
    game_name: str
    game_time: str      # 例如 "10.2 小时"（过去 2 周）
    last_play_time: str # 例如 "10月2日"
    game_header: bytes
    achievements: List[Achievements]
    completed_achievement_number: int
    total_achievement_number: int

__all__ = [
    "Player",
    "PlayerSummaries",
    "PlayerSummariesResponse",
    "ProcessedPlayer",
    "PlayerSummariesProcessedResponse",
    "DrawPlayerStatusData",
    "Achievements",
    "GameData",
    "PlayerData",
]
