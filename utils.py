import time
import pytz
import httpx
import datetime
import calendar
from PIL import Image
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from .models import Player
from .data_source import BindData  # 请确保 data_source 模块已移植，如无可根据实际情况调整或实现

async def _fetch_avatar(avatar_url: str, proxy: str = None) -> Image.Image:
    """
    根据传入的头像 URL 获取头像图像（返回 PIL Image 对象）。
    若获取失败，则返回默认的 unknown_avatar 图片。
    """
    async with httpx.AsyncClient(proxy=proxy) as client:
        response = await client.get(avatar_url)
        if response.status_code != 200:
            return Image.open(Path(__file__).parent / "res/unknown_avatar.jpg")
        return Image.open(BytesIO(response.content))

async def fetch_avatar(
    player: Player, avatar_dir: Optional[Path], proxy: str = None
) -> Image.Image:
    """
    根据 Player 对象获取头像图像，并缓存到指定目录（如果设置了 avatar_dir）。
    """
    if avatar_dir is not None:
        avatar_path = avatar_dir / f"avatar_{player['steamid']}_{player['avatarhash']}.png"
        if avatar_path.exists():
            avatar = Image.open(avatar_path)
        else:
            avatar = await _fetch_avatar(player["avatarfull"], proxy)
            avatar.save(avatar_path)
    else:
        avatar = await _fetch_avatar(player["avatarfull"], proxy)
    return avatar

def convert_player_name_to_nickname(
    data: Dict[str, str], parent_id: str, bind_data: BindData
) -> Dict[str, str]:
    """
    根据绑定数据，将玩家昵称从 BindData 中查找后添加到数据字典中。
    """
    data["nickname"] = bind_data.get_by_steam_id(parent_id, data["steamid"])["nickname"]
    return data

async def simplize_steam_player_data(
    player: Player, proxy: str = None, avatar_dir: Optional[Path] = None
) -> Dict[str, str]:
    """
    简化 Steam 玩家数据，主要提取 SteamID、头像、名称、状态和在线状态标识。
    状态根据 personastate 及 lastlogoff 数据生成自然语言描述。
    """
    avatar = await fetch_avatar(player, avatar_dir, proxy)
    if player["personastate"] == 0:
        if not player.get("lastlogoff"):
            status = "离线"
        else:
            time_logged_off = player["lastlogoff"]  # Unix 时间戳
            time_to_now = calendar.timegm(time.gmtime()) - time_logged_off
            if time_to_now < 60:
                status = "上次在线 刚刚"
            elif time_to_now < 3600:
                status = f"上次在线 {time_to_now // 60} 分钟前"
            elif time_to_now < 86400:
                status = f"上次在线 {time_to_now // 3600} 小时前"
            elif time_to_now < 2592000:
                status = f"上次在线 {time_to_now // 86400} 天前"
            elif time_to_now < 31536000:
                status = f"上次在线 {time_to_now // 2592000} 个月前"
            else:
                status = f"上次在线 {time_to_now // 31536000} 年前"
    elif player["personastate"] in [1, 2, 4]:
        status = "在线" if player.get("gameextrainfo") is None else player["gameextrainfo"]
    elif player["personastate"] == 3:
        status = "离开" if player.get("gameextrainfo") is None else player["gameextrainfo"]
    elif player["personastate"] in [5, 6]:
        status = "在线"
    else:
        status = "未知"
    return {
        "steamid": player["steamid"],
        "avatar": avatar,
        "name": player["personaname"],
        "status": status,
        "personastate": player["personastate"],
    }

def image_to_bytes(image: Image.Image) -> bytes:
    """
    将 PIL Image 对象转换为 PNG 格式的字节数据。
    """
    with BytesIO() as bio:
        image.save(bio, format="PNG")
        return bio.getvalue()

def hex_to_rgb(hex_color: str):
    """
    将 6 位十六进制颜色字符串（不含 '#'）转换为 RGB 元组。
    """
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def convert_timestamp_to_beijing_time(timestamp: int) -> str:
    """
    将 Unix 时间戳转换为北京时间格式字符串（格式：YYYY-MM-DD HH:MM:SS）。
    """
    beijing_timezone = pytz.timezone("Asia/Shanghai")
    date_utc = datetime.datetime.fromtimestamp(timestamp, pytz.utc)
    date_beijing = date_utc.astimezone(beijing_timezone)
    return date_beijing.strftime("%Y-%m-%d %H:%M:%S")
