"""
main.py - Steam Info 插件（AstrBot 版）

功能包括：
  - steamhelp: 显示使用说明
  - steambind: 绑定自己的 Steam ID（或好友代码）
  - steamunbind: 解绑自己的 Steam ID
  - steaminfo: 查看 Steam 主页信息（支持传入 @某人或直接传入 ID）
  - steamcheck: 检查并播报 Steam 好友状态
  - steamenable/steamdisable: 启用/禁用 Steam 播报
  - steamupdate: 更新群信息（父级信息，包含群头像及名称）
  - steamnickname: 设置绑定玩家昵称

依赖：
  - Python 3.7+
  - AstrBot 框架（参见 AstrBot 插件开发指南）
  - 第三方库：httpx, Pillow, numpy, bs4, pydantic 等（请在插件目录下创建 requirements.txt 声明依赖）
  - 本插件还依赖于内部模块：config、draw、models、steam、utils（建议将原 nonebot 插件中相应代码拆分并移植到对应模块中）
"""

import os
import time
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from io import BytesIO


import httpx
from PIL import Image as PILImage

# 从 AstrBot 内部 API 导入核心对象及装饰器
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.api.all import *

# 假设下面这些内部模块已完成移植或保持不变
from .draw import draw_start_gaming, draw_player_status, draw_friends_status
from .models import ProcessedPlayer, DrawPlayerStatusData
from .steam import get_steam_id, get_user_data, get_steam_users_info, STEAM_ID_OFFSET
from .utils import image_to_bytes, convert_player_name_to_nickname, simplize_steam_player_data, fetch_avatar

# 插件元数据请参考管理系统（也可以在 metadata.yaml 中配置），这里在 register 装饰器中填写
@register("astrbot_plugin_steam_info", "w33d", "播报绑定的 Steam 好友状态", "1.0.0", "https://github.com/your_repo")
class SteamInfoPlugin(Star):
    """
    SteamInfoPlugin 使用 AstrBot 的事件/指令机制实现以下功能：
      - 用户可通过 /steamhelp 等指令查看说明
      - 通过 /steambind、/steamunbind、/steamnickname 进行用户 Steam ID 和昵称管理
      - /steaminfo 展示 Steam 主页信息（包含绘图展示）
      - 定时任务更新 Steam 数据，并在群聊中播报好友状态
    """

    # 插件使用说明文本
    plugin_usage = (
        "Steam Info 使用说明:\n"
        "  steamhelp: 查看帮助\n"
        "  steambind [Steam ID 或好友代码]: 绑定 Steam ID\n"
        "  steamunbind: 解绑 Steam ID\n"
        "  steaminfo [@某人 或 Steam ID]: 查看 Steam 主页\n"
        "  steamcheck: 检查 Steam 好友状态\n"
        "  steamenable: 启用 Steam 播报\n"
        "  steamdisable: 禁用 Steam 播报\n"
        "  steamupdate [名称] [图片]: 更新群信息\n"
        "  steamnickname [昵称]: 设置玩家昵称"
    )
    def __init__(self, context: Any, config: Dict[str, Any] = None):
        super().__init__(context)
        self.config = config or {}

        # 定义 logger
        # logger = logging.getLogger(__name__)
        
        # 配置数据文件存放目录，使用当前工作目录下的 "data/plugins/astrbot_plugin_steam_info"
        base_dir = Path().cwd() / "data" / "plugins" / "astrbot_plugin_steam_info"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.bind_data_file = base_dir / "bind_data.json"
        self.steam_info_file = base_dir / "steam_info.json"
        self.parent_data_file = base_dir / "parent_data.json"
        self.disable_parent_data_file = base_dir / "disable_parent_data.json"
        # 用于头像等缓存存放目录
        self.cache_dir = base_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

        # 加载数据，若文件不存在则初始化为空字典
        self.bind_data: Dict[str, Dict[str, Any]] = self.load_json(self.bind_data_file)
        self.steam_info_data: Dict[str, Any] = self.load_json(self.steam_info_file)
        self.parent_data: Dict[str, Any] = self.load_json(self.parent_data_file)
        self.disable_parent_data: Dict[str, Any] = self.load_json(self.disable_parent_data_file)

        # 配置字体（调用 draw 模块中的函数设置字体路径）
        # 字体路径从配置中获取，若未传入则使用默认值
        from .draw import set_font_paths, check_font
        set_font_paths(
            self.config.get("steam_font_regular_path", "fonts/MiSans-Regular.ttf"),
            self.config.get("steam_font_light_path", "fonts/MiSans-Light.ttf"),
            self.config.get("steam_font_bold_path", "fonts/MiSans-Bold.ttf")
        )
        try:
            check_font()
        except FileNotFoundError as e:
            logger.error(f"{e}, 插件无法正常使用。")

        # 启动定时任务更新 Steam 信息（定时任务周期由配置项 steam_request_interval 决定）
        asyncio.create_task(self.schedule_update())

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        # 机器人初始化完成后执行一次更新任务
        await self.update_steam_info()
        
    def load_json(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        file_path = Path(file_path)
        if file_path.exists():
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"读取 {file_path} 出错: {e}")
        return {}

    def save_json(self, file_path: Union[str, Path], data: Dict[str, Any]) -> None:
        try:
            Path(file_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"保存 {file_path} 出错: {e}")

    async def schedule_update(self):
        """
        定时任务：每隔 steam_request_interval 秒更新一次 Steam 信息，
        并对每个群组（parent_id）进行好友状态播报。
        """
        while True:
            try:
                bind_data, old_players_dict = await self.update_steam_info()
                # 对每个群组调用广播函数
                for parent_id in self.bind_data.keys():
                    old_players: List[ProcessedPlayer] = old_players_dict.get(parent_id, [])
                    steam_ids = self.bind_data.get(parent_id, {}).keys()
                    new_players: List[ProcessedPlayer] = self.get_players_by_ids(parent_id, list(steam_ids))
                    await self.broadcast_steam_info(parent_id, old_players, new_players)
            except Exception as e:
                logger.error(f"定时任务更新 Steam 信息出错：{e}")
            await asyncio.sleep(self.config.steam_request_interval)

    def get_players_by_ids(self, parent_id: str, steam_ids: List[str]) -> List[ProcessedPlayer]:
        """从 steam_info_data 中获取指定群组绑定的玩家数据（简化版）"""
        # 假设 steam_info_data 存储了最新查询的玩家信息，结构与原版一致
        players = []
        for player in self.steam_info_data.get("players", []):
            if player.get("steamid") in steam_ids:
                players.append(player)
        return players

    async def update_steam_info(self) -> (Dict[str, Any], Dict[str, List[ProcessedPlayer]]):
        """
        拉取 Steam 用户信息并更新缓存文件，返回最新的 bind_data 与每个群组旧的玩家信息字典。
        """
        all_steam_ids = []
        # 遍历所有群组所有用户绑定的 steam_id
        for parent_id, users in self.bind_data.items():
            all_steam_ids.extend([user["steam_id"] for user in users.values()])
        all_steam_ids = list(set(all_steam_ids))
        steam_response = await get_steam_users_info(all_steam_ids, self.config.steam_api_key, proxy=self.config.proxy)
        old_players_dict: Dict[str, List[ProcessedPlayer]] = {}
        for parent_id in self.bind_data.keys():
            steam_ids = list(self.bind_data.get(parent_id, {}).values())
            old_players_dict[parent_id] = self.get_players_by_ids(parent_id, steam_ids)
        # 更新缓存数据（这里只做简单替换，实际项目中可加入对比逻辑）
        self.steam_info_data = steam_response
        self.save_json(self.steam_info_file, steam_response)
        return self.bind_data, old_players_dict

    async def broadcast_steam_info(self, parent_id: str,
                                   old_players: List[ProcessedPlayer],
                                   new_players: List[ProcessedPlayer]):
        """
        对绑定该群的 Steam 用户数据进行对比，生成播报消息（包括文本和图片），并发送到该群。
        若该群在 disable_parent_data 中则不进行播报。
        """
        if parent_id in self.disable_parent_data:
            return

        # 此处调用 utils 模块对比数据，生成文本播报信息；具体对比逻辑参照原 nonebot 版本
        msg_lines = []
        # 遍历对比数据（这里只是简单示例，实际请实现 start/stop/change 等逻辑）
        for player in new_players:
            # 例如：检测是否开始玩游戏
            if player.get("gameextrainfo"):
                msg_lines.append(f"{player.get('personaname')} 正在玩 {player.get('gameextrainfo')}")
        if not msg_lines:
            return

        # 根据配置选择播报类型：all, part, none
        from .draw import draw_friends_status  # 生成好友状态图片
        if self.config.steam_broadcast_type in ["all", "part"]:
            # 根据全量或者部分播报生成不同风格图片，调用 draw 模块即可
            image_obj = draw_friends_status(parent_avatar=PILImage.open(Path(self.parent_data.get(parent_id, {}).get("avatar", ""))),
                                            parent_name=self.parent_data.get(parent_id, {}).get("name", "Steam"),
                                            data=[])  # 这里 data 请根据实际需求构造好友状态数据（可调用 simplize_steam_player_data 转换）
            image_bytes = image_to_bytes(image_obj)
            uni_msg = f"\n".join(msg_lines)  # 文本部分
            # 发送图文消息
            await self.context.send_message(event_origin=parent_id, chains=[uni_msg, {"type": "image", "data": image_bytes}])
        else:
            # 仅播报文本
            await self.context.send_message(event_origin=parent_id, chains=[f"\n".join(msg_lines)])

    # 以下方法用于提取当前消息所在的群 ID（在 AstrBot 中通常存储在 unified_msg_origin 字符串中）
    def get_parent_id(self, event: AstrMessageEvent) -> str:
        # 此处简单返回 event.unified_msg_origin，实际可根据平台细化处理
        return event.unified_msg_origin

    # ========= 指令处理 =========

    @filter.command("steamhelp")
    async def steam_help(self, event: AstrMessageEvent):
        """显示插件使用帮助"""
        yield event.plain_result(self.plugin_usage)

    @filter.command("steambind")
    async def steam_bind(self, event: AstrMessageEvent, args: str):
        """
        绑定 Steam ID 或好友代码：
          格式：steambind [Steam ID 或好友代码]
        """
        parent_id = self.get_parent_id(event)
        arg = args.strip()
        if not arg.isdigit():
            yield event.plain_result("请输入正确的 Steam ID 或好友代码，格式: steambind [Steam ID 或好友代码]")
            return
        steam_id = get_steam_id(arg)
        user_id = event.get_sender_id()
        # 如果该群已有绑定信息，以群为键、用户为子键存储
        if parent_id not in self.bind_data:
            self.bind_data[parent_id] = {}
        self.bind_data[parent_id][user_id] = {"steam_id": steam_id, "nickname": None}
        self.save_json(self.bind_data_file, self.bind_data)
        yield event.plain_result(f"已绑定你的 Steam ID 为 {steam_id}")

    @filter.command("steamunbind")
    async def steam_unbind(self, event: AstrMessageEvent):
        """解绑 Steam ID"""
        parent_id = self.get_parent_id(event)
        user_id = event.get_sender_id()
        if parent_id in self.bind_data and user_id in self.bind_data[parent_id]:
            del self.bind_data[parent_id][user_id]
            self.save_json(self.bind_data_file, self.bind_data)
            yield event.plain_result("已解绑 Steam ID")
        else:
            yield event.plain_result("未绑定 Steam ID")

    @filter.command("steaminfo", aliases={"steam信息"})
    async def steam_info(self, event: AstrMessageEvent, *args, **kwargs):
        # 从事件中获取文本参数（去除指令部分）
        arg_text = event.message_str.strip()
        if arg_text:
            # 如果传入参数是纯数字，则判断大小来转换
            if arg_text.isdigit():
                steam_id_int = int(arg_text)
                if steam_id_int < STEAM_ID_OFFSET:
                    steam_id = str(steam_id_int + STEAM_ID_OFFSET)
                else:
                    steam_id = arg_text
            else:
                # 如果非数字，可尝试从绑定数据中查找（此处示例简单）
                parent_id = self.get_parent_id(event)
                for uid, data in self.bind_data.get(parent_id, {}).items():
                    if uid == arg_text:
                        steam_id = data["steam_id"]
                    break
                else:
                    await event.plain_result("该用户未绑定 Steam ID")
                    return
        else:
            parent_id = self.get_parent_id(event)
            user_id = event.get_sender_id()
            if parent_id in self.bind_data and user_id in self.bind_data[parent_id]:
                steam_id = self.bind_data[parent_id][user_id]["steam_id"]
            else:
                await event.plain_result("未绑定 Steam ID，请先使用 steambind 绑定")
                return

        # 调用 get_user_data 获取用户数据（确保 proxy 已处理为空值的问题）
        player_data = await get_user_data(int(steam_id), cache_path=self.cache_dir, proxy=self.config.get("proxy") or None)
    
        # 使用 PILImage（已别名导入的 PIL.Image）打开图像数据
        from PIL import Image as PILImage
        image_obj = draw_player_status(
            player_bg=PILImage.open(BytesIO(player_data["background"])),
            player_avatar=PILImage.open(BytesIO(player_data["avatar"])),
            player_name=player_data["player_name"],
            player_id=str(int(steam_id) - STEAM_ID_OFFSET),
            player_description=player_data["description"],
            player_last_two_weeks_time=player_data.get("recent_2_week_play_time", ""),
            player_games=[]  # 可根据实际数据构造
        )
        image_bytes = image_to_bytes(image_obj)
        yield event.image_result(image_bytes)



    @filter.command("steamcheck")
    async def steam_check(self, event: AstrMessageEvent, args: str):
        """
        检查 Steam 好友状态并发送好友状态图片至当前群
        格式：steamcheck  （参数可为空）
        """
        parent_id = self.get_parent_id(event)
        # 获取当前群所有绑定的 Steam ID
        steam_ids = []
        if parent_id in self.bind_data:
            for user_data in self.bind_data[parent_id].values():
                steam_ids.append(user_data["steam_id"])
        if not steam_ids:
            yield event.plain_result("本群暂无绑定 Steam 信息")
            return
        steam_response = await get_steam_users_info(steam_ids, self.config.steam_api_key, proxy=self.config.proxy)
        # 获取群头像和群名称，假设 parent_data 中已存储；否则使用默认值
        parent_avatar_path = self.parent_data.get(parent_id, {}).get("avatar", "")
        parent_name = self.parent_data.get(parent_id, {}).get("name", "Steam")
        image_obj = draw_friends_status(
            parent_avatar=PILImage.open(parent_avatar_path) if parent_avatar_path else Image.new("RGB", (72, 72)),
            parent_name=parent_name,
            data=[]  # 此处请调用 simplize_steam_player_data 等方法构造好友状态数据
        )
        image_bytes = image_to_bytes(image_obj)
        yield event.image_result(image_bytes)

    @filter.command("steamenable")
    async def steam_enable(self, event: AstrMessageEvent):
        """启用 Steam 播报（从 disable 数据中移除）"""
        parent_id = self.get_parent_id(event)
        if parent_id in self.disable_parent_data:
            del self.disable_parent_data[parent_id]
            self.save_json(self.disable_parent_data_file, self.disable_parent_data)
        yield event.plain_result("已启用 Steam 播报")

    @filter.command("steamdisable")
    async def steam_disable(self, event: AstrMessageEvent):
        """禁用 Steam 播报（记录该群 ID 到 disable 数据中）"""
        parent_id = self.get_parent_id(event)
        self.disable_parent_data[parent_id] = True
        self.save_json(self.disable_parent_data_file, self.disable_parent_data)
        yield event.plain_result("已禁用 Steam 播报")

    @filter.command("steamupdate")
    async def steam_update_parent(self, event: AstrMessageEvent, args: str):
        """
        更新群信息：需要传入文本和图片（例如：名称与图标）
        格式：steamupdate [名称] [图片]
        解析时，请从消息链中提取文字与图片，具体根据 AstrBot 消息链处理
        """
        parent_id = self.get_parent_id(event)
        # 此处示例：假设 args 中同时包含名称和图片链接，可拆分处理
        parts = args.split()
        if len(parts) < 2:
            yield event.plain_result("文本中应包含图片和文字")
            return
        name = parts[0]
        image_url = parts[1]
        # 下载图片数据
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url)
                if response.status_code != 200:
                    yield event.plain_result("获取图片失败")
                    return
                avatar_image = PILImage.open(BytesIO(response.content))
        except Exception as e:
            yield event.plain_result(f"获取图片错误: {e}")
            return
        # 更新 parent_data 数据（保存图片路径与名称）
        avatar_path = Path(self.cache_dir) / f"parent_{parent_id}.png"
        avatar_image.save(avatar_path)
        self.parent_data[parent_id] = {"avatar": str(avatar_path), "name": name}
        self.save_json(self.parent_data_file, self.parent_data)
        yield event.plain_result("更新成功")

    @filter.command("steamnickname")
    async def steam_nickname(self, event: AstrMessageEvent, args: str):
        """
        设置 Steam 昵称
        格式：steamnickname [昵称]
        """
        parent_id = self.get_parent_id(event)
        nickname = args.strip()
        if not nickname:
            yield event.plain_result("请输入昵称，格式: steamnickname [昵称]")
            return
        user_id = event.get_sender_id()
        if parent_id not in self.bind_data or user_id not in self.bind_data[parent_id]:
            yield event.plain_result("未绑定 Steam ID，请先使用 steambind 绑定")
            return
        self.bind_data[parent_id][user_id]["nickname"] = nickname
        self.save_json(self.bind_data_file, self.bind_data)
        yield event.plain_result(f"已设置你的昵称为 {nickname}，将在 Steam 播报中显示")
