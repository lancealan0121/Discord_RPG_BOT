import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import subprocess
import os
import tempfile
import time
import random
import asyncio
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

# ==================== 基本設定 ====================
TOKEN = 'token'
FOREGROUND_VIDEO = './fire.mp4'
TRANSFER_FEE_RATE = 0.05
EARN_MONEY_COOLDOWN = 5

# 隨機回覆訊息列表
RANDOM_REPLIES = [
    "你為什麼要和機器人吵架", "skill issue", "loser", "lol", "幹", "笑死",
    "哈哈哈哈", "廢物", "可憐", "就這？", "已讀", "拒絕", "下次一定", "fuck",
    "不知道欸", "你媽知道嗎？", "🗿", "不要", "好麻煩", "等等再說", "消失",
    "no", "cope", "L", "ratio", "誰問你了", "didn't ask", "touch grass",
    "很忙", "閉嘴", "吵死了", "shut up", "cringe", "💀", "🤡",
    "nobody cares", "ok and?", "so what", "煩", "annoying af", "mald",
    "seethe", "cope harder", "L + ratio + cope", "沒人在乎", "不關我事",
    "已讀不回", "seen", "哈？", "所以呢", "誰管你", "👎", "🖕", "cry more",
    "whatever", "隨便啦", "不想理你", "滾", "get rekt", "gg ez", "trash",
    "菜雞", "笑你", "弱爆", "爛", "呵呵", "嗯哼", "sure jan", "yikes", "oof",
    "懶得說", "無語", "speechless", "😑", "🙄", "😴", "🥱", "稍微",
    "差不多得了", "算了吧你", "省省吧", "別鬧了", "can't relate",
    "not my problem", "idc", "idk", "nah", "nope", "pass", "blocked",
    "muted", "ignored", "懶", "不想", "免談", "謝謝指教", "下一位", "next",
    "skip", "boring", "無聊", "沒梗", "老梗", "heard it before", "繼續",
    "then what", "and?", "your point?", "重點呢？", "所以咧", "不然",
    "who asked tho", "還好吧", "就那樣", "普普", "mid", "想得美", "做夢",
    "想太多", "overthinking", "delusional", "真敢說", "好意思說", "I'm dead",
    "💩", "📉", "🚮", "not it", "hard pass", "major L", "massive L",
    "你開心就好", "自己爽就好", "加油好嗎", "自我感覺良好", "stay mad",
    "keep crying", "git gud", "uninstall", "重開吧，別玩了", "seriously?",
    "for real?", "真的假的", "sure buddy", "ok boomer", "過氣", "outdated",
    "沒救了", "hopeless", "你完了", "it's over", "gg ez", "FUCK OFF",
    "nigger", "stfu"
]

# ==================== Discord Bot 初始化 ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==================== 金錢系統 ====================
class MoneySystem:
    user_money: Dict[int, int] = {}  # 用戶金錢
    user_stats: Dict[int, dict] = {}  # 用戶統計數據
    earn_cooldowns: Dict[int, datetime] = {}  # 賺錢冷卻

    @classmethod
    def get_money(cls, user_id: int) -> int:
        """獲取用戶金錢"""
        if user_id not in cls.user_money:
            cls.user_money[user_id] = 0
        return cls.user_money[user_id]

    @classmethod
    def add_money(cls, user_id: int, amount: int):
        """增加金錢 (整合商城 Buff)"""
        # ===== 🆕 發財符效果 =====
        if ShopSystem.has_active_item(user_id, 'double_money'):
            amount *= 2

        if user_id not in cls.user_money:
            cls.user_money[user_id] = 0

        # 檢查破產
        if cls.user_money[user_id] == 0 and amount > 0:
            tracking = AchievementSystem.get_user_tracking(user_id)
            tracking['bankruptcy_count'] += 1

        cls.user_money[user_id] += amount
        cls._update_stats(user_id, 'total_earned', amount)

    @classmethod
    def deduct_money(cls, user_id: int, amount: int) -> bool:
        """扣除金錢，返回是否成功"""
        if cls.get_money(user_id) >= amount:
            cls.user_money[user_id] -= amount
            cls._update_stats(user_id, 'total_spent', amount)
            return True
        return False

    @classmethod
    def transfer_money(cls, from_user: int, to_user: int, amount: int) -> Tuple[bool, int]:
        """
        轉帳功能
        返回：(是否成功, 手續費)
        """
        fee = int(amount * TRANSFER_FEE_RATE)
        total_cost = amount + fee

        if cls.get_money(from_user) >= total_cost:
            cls.user_money[from_user] -= total_cost
            cls.add_money(to_user, amount)
            cls._update_stats(from_user, 'total_spent', total_cost)
            cls._update_stats(from_user, 'transfer_sent', amount)
            cls._update_stats(to_user, 'transfer_received', amount)
            return True, fee
        return False, 0

    @classmethod
    def check_cooldown(cls, user_id: int) -> Optional[int]:
        """
        檢查冷卻時間
        返回：剩餘秒數（None 表示可以使用）
        """
        if user_id not in cls.earn_cooldowns:
            return None

        elapsed = (datetime.now() - cls.earn_cooldowns[user_id]).total_seconds()
        remaining = EARN_MONEY_COOLDOWN - elapsed

        if remaining <= 0:
            return None
        return int(remaining)

    @classmethod
    def set_cooldown(cls, user_id: int):
        """設置冷卻時間"""
        cls.earn_cooldowns[user_id] = datetime.now()

    @classmethod
    def get_stats(cls, user_id: int) -> dict:
        """獲取用戶統計數據"""
        if user_id not in cls.user_stats:
            cls.user_stats[user_id] = {
                'total_earned': 0,
                'total_spent': 0,
                'gamble_wins': 0,
                'gamble_losses': 0,
                'gamble_total_won': 0,
                'gamble_total_lost': 0,
                'transfer_sent': 0,
                'transfer_received': 0,
                'games_played': 0,
                'games_won': 0,
            }
        return cls.user_stats[user_id]

    @classmethod
    def _update_stats(cls, user_id: int, stat_name: str, amount: int):
        """更新統計數據"""
        stats = cls.get_stats(user_id)
        if stat_name in stats:
            stats[stat_name] += amount


# ==================== 物品管理系統 ====================
class InventorySystem:
    """
    物品管理系統
    管理用戶的抽卡物品庫存
    """
    user_inventory: Dict[int, Dict[str, int]] = {}  # {user_id: {'blue': 數量, 'purple': 數量, ...}}

    # 物品價格表
    ITEM_PRICES = {
        'blue': 30,  # 三星
        'purple': 170,  # 四星
        'gold_up': 2600,  # 五星UP
        'gold_off': 2000  # 五星歪
    }

    @classmethod
    def get_inventory(cls, user_id: int) -> Dict[str, int]:
        """獲取用戶物品庫存"""
        if user_id not in cls.user_inventory:
            cls.user_inventory[user_id] = {
                'blue': 0,
                'purple': 0,
                'gold_up': 0,
                'gold_off': 0
            }
        return cls.user_inventory[user_id]

    @classmethod
    def add_item(cls, user_id: int, item_type: str, amount: int = 1):
        """增加物品"""
        inventory = cls.get_inventory(user_id)
        if item_type in inventory:
            inventory[item_type] += amount

    @classmethod
    def remove_item(cls, user_id: int, item_type: str, amount: int = 1) -> bool:
        """移除物品，返回是否成功"""
        inventory = cls.get_inventory(user_id)
        if item_type in inventory and inventory[item_type] >= amount:
            inventory[item_type] -= amount
            return True
        return False

    @classmethod
    def sell_item(cls, user_id: int, item_type: str, amount: int = 1) -> Tuple[bool, int]:
        """
        出售物品
        返回：(是否成功, 獲得金額)
        """
        if item_type not in cls.ITEM_PRICES:
            return False, 0

        if cls.remove_item(user_id, item_type, amount):
            total_price = cls.ITEM_PRICES[item_type] * amount
            MoneySystem.add_money(user_id, total_price)
            return True, total_price
        return False, 0

    @classmethod
    def get_total_value(cls, user_id: int) -> int:
        """計算庫存總價值"""
        inventory = cls.get_inventory(user_id)
        total = 0
        for item_type, count in inventory.items():
            if item_type in cls.ITEM_PRICES:
                total += cls.ITEM_PRICES[item_type] * count
        return total


# ==================== 抽卡系統 ====================
class GachaSystem:
    """
    崩壞星穹鐵道風格的抽卡系統
    包含軟保底、硬保底、大保底機制
    """
    # 常駐五星角色池
    STANDARD_5STAR = ['布洛妮婭', '克拉拉', '姬子', '傑帕德', '白露', '瓦爾特', '彥卿']

    # UP 角色名稱
    current_up_character = '火花'

    # 存儲每個用戶的抽卡狀態
    user_data: Dict[int, dict] = {}

    @classmethod
    def get_user_pity(cls, user_id: int):
        """獲取用戶的保底狀態"""
        if user_id not in cls.user_data:
            cls.user_data[user_id] = {
                'pity_count': 0,  # 距離上次五星的抽數
                'guarantee': False,  # 是否大保底
                'four_star_pity': 0,  # 四星保底計數
                'history': [],  # 抽卡歷史記錄
                'total_pulls': 0,  # 總抽卡次數
                'five_star_count': 0,  # 五星總數
                'five_star_up_count': 0,  # UP五星數量
            }
        return cls.user_data[user_id]

    @classmethod
    def single_pull(cls, user_id: int):
        """單抽邏輯"""
        data = cls.get_user_pity(user_id)
        data['pity_count'] += 1
        data['four_star_pity'] += 1
        data['total_pulls'] += 1

        # 五星判定（90抽硬保底）
        base_5star_rate = 0.006  # 0.6% 基礎五星率

        if ShopSystem.has_active_item(user_id, 'gacha_luck'):
            base_5star_rate += 0.03  # 幸運草 +3%

        # 軟保底機制（73抽後提升概率）
        if data['pity_count'] >= 73:
            base_5star_rate += (data['pity_count'] - 72) * 0.06

        # 硬保底或抽中五星
        if data['pity_count'] >= 90 or random.random() < base_5star_rate:
            current_pull = data['pity_count']
            data['five_star_count'] += 1

            if data['guarantee']:
                # 大保底：必定UP
                result = ('gold_up', current_pull)
                data['guarantee'] = False
                data['five_star_up_count'] += 1
                data['history'].append(('五星UP', cls.current_up_character, current_pull))
                InventorySystem.add_item(user_id, 'gold_up')  # ← 新增
            else:
                # 小保底：50%概率UP
                if random.random() < 0.5:
                    result = ('gold_up', current_pull)
                    data['guarantee'] = False
                    data['five_star_up_count'] += 1
                    data['history'].append(('五星UP', cls.current_up_character, current_pull))
                    InventorySystem.add_item(user_id, 'gold_up')  # ← 新增
                else:
                    # 歪了
                    off_banner_char = random.choice(cls.STANDARD_5STAR)
                    result = ('gold_off', off_banner_char, current_pull)
                    data['guarantee'] = True
                    data['history'].append(('五星歪', off_banner_char, current_pull))
                    InventorySystem.add_item(user_id, 'gold_off')  # ← 新增

            data['pity_count'] = 0
            data['four_star_pity'] = 0
            return result

        # 四星判定（10抽硬保底）
        base_4star_rate = 0.051

        if data['four_star_pity'] >= 10 or random.random() < base_4star_rate:
            data['four_star_pity'] = 0
            InventorySystem.add_item(user_id, 'purple')  # ← 新增
            return 'purple'

        # 三星
        InventorySystem.add_item(user_id, 'blue')  # ← 新增
        return 'blue'

    @classmethod
    def ten_pull(cls, user_id: int):
        """十連抽"""
        results = []
        for _ in range(10):
            results.append(cls.single_pull(user_id))
        return results

    @staticmethod
    def rarity_to_emoji(rarity):
        """稀有度轉 emoji"""
        if rarity == 'blue':
            return '🔵'
        elif rarity == 'purple':
            return '🟣'
        elif isinstance(rarity, tuple):
            if rarity[0] == 'gold_up':
                return '🟡'
            elif rarity[0] == 'gold_off':
                return '🟠'
        return '⚪'

    @staticmethod
    def format_results(results: list):
        """格式化成 5x2 顯示"""
        lines = []
        for i in range(0, 10, 5):
            row = results[i:i + 5]
            lines.append(' '.join([GachaSystem.rarity_to_emoji(r) for r in row]))
        return '\n'.join(lines)

    @classmethod
    def get_gacha_stats(cls, user_id: int) -> dict:
        """獲取抽卡統計"""
        data = cls.get_user_pity(user_id)
        total_pulls = data['total_pulls']
        five_star_count = data['five_star_count']

        return {
            'total_pulls': total_pulls,
            'five_star_count': five_star_count,
            'five_star_rate': (five_star_count / total_pulls * 100) if total_pulls > 0 else 0,
            'up_count': data['five_star_up_count'],
            'up_rate': (data['five_star_up_count'] / five_star_count * 100) if five_star_count > 0 else 0,
        }


# ==================== 賭博系統 ====================
class GambleSystem:
    """賭博系統"""

    @staticmethod
    def get_tier_info(amount: int) -> Tuple[str, int, float]:
        """
        根據賭注金額返回：(等級名稱, 賠率, 勝率)
        """
        if amount <= 500:
            return "小賭怡情", 2, 0.6
        elif amount <= 2000:
            return "中等賭局", 3, 0.4
        elif amount <= 5000:
            return "高風險賭局", 5, 0.19
        else:
            return "豪賭", 10, 0.1

    # 找到 GambleSystem.gamble 方法，修改如下：
    @classmethod
    def gamble(cls, user_id: int, amount: int) -> Tuple[bool, int, str]:
        """執行賭博 (整合商城 Buff)"""
        tier, multiplier, win_rate = cls.get_tier_info(amount)

        # ===== 🆕 商城 Buff 加成 =====
        if ShopSystem.has_active_item(user_id, 'gamble_boost'):
            win_rate += 0.15  # 直接加 0.15，相當於 +15%
            win_rate = min(win_rate, 0.95)  # 上限改為 0.95

        is_win = random.random() < win_rate

        # ===== 追蹤連勝 (成就用) =====
        tracking = AchievementSystem.get_user_tracking(user_id)

        if is_win:
            reward = amount * multiplier
            profit = reward - amount
            MoneySystem.get_stats(user_id)['gamble_wins'] += 1
            MoneySystem.get_stats(user_id)['gamble_total_won'] += profit

            # 連勝計數
            tracking['gamble_streak'] += 1

            return True, reward, tier
        else:
            MoneySystem.get_stats(user_id)['gamble_losses'] += 1
            MoneySystem.get_stats(user_id)['gamble_total_lost'] += amount

            # 連勝中斷
            tracking['gamble_streak'] = 0

            return False, amount, tier


# ==================== 小遊戲系統 ====================
class MiniGames:
    """小遊戲集合"""

    @staticmethod
    def guess_number_game() -> int:
        """猜數字遊戲：返回正確答案（1-5）"""
        return random.randint(1, 5)

    @staticmethod
    def rock_paper_scissors(player_choice: str) -> Tuple[str, str]:
        """
        剪刀石頭布
        返回：(機器人選擇, 結果: 'win'/'lose'/'tie')
        """
        choices = ['剪刀', '石頭', '布']
        bot_choice = random.choice(choices)

        win_conditions = {
            '剪刀': '布',
            '石頭': '剪刀',
            '布': '石頭'
        }

        if player_choice == bot_choice:
            return bot_choice, 'tie'
        elif win_conditions[player_choice] == bot_choice:
            return bot_choice, 'win'
        else:
            return bot_choice, 'lose'

    @staticmethod
    def dice_game() -> Tuple[int, int, str]:
        """
        骰子比大小
        返回：(玩家點數, 機器人點數, 結果: 'win'/'lose'/'tie')
        """
        player_dice = random.randint(1, 6)
        bot_dice = random.randint(1, 6)

        if player_dice > bot_dice:
            return player_dice, bot_dice, 'win'
        elif player_dice < bot_dice:
            return player_dice, bot_dice, 'lose'
        else:
            return player_dice, bot_dice, 'tie'


# ==================== 排行榜系統 ====================
class LeaderboardSystem:
    """排行榜系統"""

    @staticmethod
    def get_money_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
        """金錢排行榜"""
        sorted_users = sorted(
            MoneySystem.user_money.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_users[:limit]

    @staticmethod
    def get_gacha_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
        """抽卡次數排行榜"""
        gacha_counts = [
            (user_id, data['total_pulls'])
            for user_id, data in GachaSystem.user_data.items()
        ]
        sorted_users = sorted(gacha_counts, key=lambda x: x[1], reverse=True)
        return sorted_users[:limit]

    @staticmethod
    def get_gamble_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
        """賭博贏最多排行榜"""
        gamble_profits = [
            (user_id, stats['gamble_total_won'] - stats['gamble_total_lost'])
            for user_id, stats in MoneySystem.user_stats.items()
        ]
        sorted_users = sorted(gamble_profits, key=lambda x: x[1], reverse=True)
        return sorted_users[:limit]


# ==================== FFmpeg 影片合成系統 ====================
class FFmpegComposer:
    """使用 FFmpeg 進行影片合成"""

    @staticmethod
    def create_temp_path(ext: str) -> str:
        """生成臨時檔案路徑"""
        timestamp = int(time.time() * 1000)
        random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
        return os.path.join(tempfile.gettempdir(), f'fire-{timestamp}-{random_str}{ext}')

    @staticmethod
    async def download_file(url: str, dest: str) -> None:
        """下載檔案"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f'Failed to download file: HTTP {resp.status}')
                with open(dest, 'wb') as f:
                    f.write(await resp.read())

    @staticmethod
    def get_video_dimensions(video_path: str) -> tuple[int, int]:
        """使用 ffprobe 取得影片尺寸"""
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        width, height = map(int, result.stdout.strip().split(','))
        return width, height

    @staticmethod
    def render_mp4(background_path: str, foreground_path: str, output_path: str, low_quality: bool = False) -> None:
        """使用 FFmpeg 合成影片"""
        bg_width, bg_height = FFmpegComposer.get_video_dimensions(background_path)

        out_height = 360
        out_width = round((bg_width / bg_height) * out_height / 2) * 2

        filter_complex = (
            f"[0:v]scale={out_width}:{out_height}:flags=lanczos[bg];"
            f"[1:v]colorkey=black:0.3:0.2[ck];"
            f"[ck]scale={out_width}:{out_height}:force_original_aspect_ratio=increase:flags=lanczos[scaled];"
            f"[scaled]colorchannelmixer=aa=0.8[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

        crf = '43' if low_quality else '35'

        cmd = [
            'ffmpeg', '-i', background_path, '-i', foreground_path,
            '-filter_complex', filter_complex,
            '-c:v', 'libx264', '-preset', 'ultrafast',
            '-crf', crf, '-pix_fmt', 'yuv420p',
            '-an', '-y', output_path
        ]

        subprocess.run(cmd, check=True, capture_output=True)

    @staticmethod
    def mp4_to_gif(mp4_path: str, gif_path: str) -> None:
        """將 MP4 轉換為 GIF"""
        filter_complex = (
            "[0:v]fps=15[f];"
            "[f]split[s0][s1];"
            "[s0]palettegen=max_colors=64[p];"
            "[s1][p]paletteuse=dither=bayer:bayer_scale=3"
        )

        cmd = [
            'ffmpeg', '-i', mp4_path,
            '-filter_complex', filter_complex,
            '-loop', '0', '-y', gif_path
        ]

        subprocess.run(cmd, check=True, capture_output=True)

    @staticmethod
    async def compose(background_path: str, foreground_path: str, output_path: str,
                      output_format: str = 'mp4', low_quality: bool = False) -> str:
        """主要合成函數"""
        if output_format == 'mp4':
            await asyncio.get_event_loop().run_in_executor(
                None,
                FFmpegComposer.render_mp4,
                background_path, foreground_path, output_path, low_quality
            )
            return output_path

        tmp_mp4 = FFmpegComposer.create_temp_path('.mp4')
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                FFmpegComposer.render_mp4,
                background_path, foreground_path, tmp_mp4, low_quality
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                FFmpegComposer.mp4_to_gif,
                tmp_mp4, output_path
            )
            return output_path
        finally:
            if os.path.exists(tmp_mp4):
                os.remove(tmp_mp4)


# ==================== 📅 每日簽到系統 ====================
class DailyCheckIn:
    """每日簽到系統"""
    user_checkin: Dict[int, dict] = {}  # {user_id: {'last_checkin': datetime, 'streak': int}}

    # 簽到獎勵表
    CHECKIN_REWARDS = [200, 400, 800, 1200, 2000, 2200]
    BONUS_REWARD = 300  # 第7天起每天額外獎勵

    @classmethod
    def get_user_data(cls, user_id: int) -> dict:
        """獲取用戶簽到資料"""
        if user_id not in cls.user_checkin:
            cls.user_checkin[user_id] = {
                'last_checkin': None,
                'streak': 0,
                'total_checkins': 0,
                'total_earned': 0
            }
        return cls.user_checkin[user_id]

    @classmethod
    def can_checkin(cls, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        檢查是否可以簽到
        返回：(是否可以簽到, 錯誤訊息)
        """
        data = cls.get_user_data(user_id)

        if data['last_checkin'] is None:
            return True, None

        now = datetime.now()
        last_checkin = data['last_checkin']

        # 計算距離上次簽到的時間
        time_diff = now - last_checkin

        # 如果距離上次簽到未滿24小時
        if time_diff < timedelta(hours=24):
            remaining = timedelta(hours=24) - time_diff
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return False, f"⏰ 你今天已經簽到過了！\n下次簽到時間：**{hours}小時{minutes}分鐘**後"

        return True, None

    @classmethod
    def calculate_reward(cls, streak: int) -> int:
        """計算簽到獎勵"""
        if streak < len(cls.CHECKIN_REWARDS):
            return cls.CHECKIN_REWARDS[streak]
        else:
            # 第7天起，基礎2200 + 額外300
            days_after_six = streak - len(cls.CHECKIN_REWARDS)
            return cls.CHECKIN_REWARDS[-1] + (cls.BONUS_REWARD * (days_after_six + 1))

    @classmethod
    def checkin(cls, user_id: int) -> Tuple[int, int, bool]:
        """
        執行簽到
        返回：(獲得金額, 連續天數, 是否斷簽)
        """
        data = cls.get_user_data(user_id)
        now = datetime.now()

        broke_streak = False

        # 檢查是否斷簽
        if data['last_checkin'] is not None:
            time_diff = now - data['last_checkin']

            # 如果超過48小時，視為斷簽
            if time_diff >= timedelta(hours=48):
                data['streak'] = 0
                broke_streak = True
            else:
                data['streak'] += 1
        else:
            # 第一次簽到
            data['streak'] = 0

        # 計算獎勵
        reward = cls.calculate_reward(data['streak'])

        # 更新資料
        data['last_checkin'] = now
        data['total_checkins'] += 1
        data['total_earned'] += reward

        # 給予獎勵
        MoneySystem.add_money(user_id, reward)

        current_streak = data['streak'] + 1  # +1 因為今天算進去

        return reward, current_streak, broke_streak

    @classmethod
    def get_next_rewards(cls, current_streak: int, count: int = 7) -> List[Tuple[int, int]]:
        """
        獲取接下來幾天的獎勵預覽
        返回：[(天數, 獎勵金額), ...]
        """
        rewards = []
        for i in range(count):
            day = current_streak + i
            reward = cls.calculate_reward(day)
            rewards.append((day + 1, reward))
        return rewards


# ==================== 📅 簽到指令 ====================

@bot.tree.command(name="簽到", description="每日簽到領取獎勵")
async def daily_checkin(interaction: discord.Interaction):
    """每日簽到"""
    user_id = interaction.user.id

    # 檢查是否可以簽到
    can_checkin, error_msg = DailyCheckIn.can_checkin(user_id)

    if not can_checkin:
        await interaction.response.send_message(error_msg, ephemeral=True)
        return

    # 執行簽到
    reward, streak, broke_streak = DailyCheckIn.checkin(user_id)

    # 構建訊息
    message_parts = [
        f"✅ **簽到成功！**",
        f"",
    ]

    if broke_streak:
        message_parts.append(f"⚠️ 連續簽到中斷！重新開始計算")
        message_parts.append(f"")

    message_parts.extend([
        f"💰 獲得金錢：**{reward}** 元",
        f"🔥 連續簽到：**{streak}** 天",
        f"💵 目前金錢：**{MoneySystem.get_money(user_id)}** 元",
        f"",
    ])

    # 顯示接下來7天的獎勵
    next_rewards = DailyCheckIn.get_next_rewards(streak, 7)
    message_parts.append("📅 **未來獎勵預覽：**")

    for day, amount in next_rewards:
        if day == streak + 1:
            message_parts.append(f"├ 明天（第{day}天）：**{amount}** 元")
        else:
            message_parts.append(f"├ 第{day}天：**{amount}** 元")

    # 特別提示
    if streak >= 6:
        message_parts.append(f"")
        message_parts.append(f"🎉 恭喜達成連續簽到6天！之後每天額外 +300 元！")

    await AchievementSystem.check_and_unlock(user_id, interaction.channel)
    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="簽到資訊", description="查看你的簽到統計")
async def checkin_info(interaction: discord.Interaction):
    """簽到資訊"""
    user_id = interaction.user.id
    data = DailyCheckIn.get_user_data(user_id)

    if data['last_checkin'] is None:
        await interaction.response.send_message(
            "📅 你還沒有簽到過喔！\n使用 `/簽到` 開始你的簽到旅程吧！",
            ephemeral=True
        )
        return

    # 檢查今天是否已簽到
    can_checkin, _ = DailyCheckIn.can_checkin(user_id)
    today_status = "❌ 今天已簽到" if not can_checkin else "✅ 今天尚未簽到"

    # 計算下次簽到時間
    if not can_checkin:
        now = datetime.now()
        time_diff = now - data['last_checkin']
        remaining = timedelta(hours=24) - time_diff
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        next_checkin = f"{hours}小時{minutes}分鐘後"
    else:
        next_checkin = "現在就可以簽到！"

    message = f"""
📅 **{interaction.user.display_name} 的簽到資訊**

🔥 **目前連續：{data['streak'] + 1}** 天
📊 **累計簽到：{data['total_checkins']}** 次
💰 **簽到總收入：{data['total_earned']}** 元

{today_status}
⏰ **下次簽到：{next_checkin}**

💡 **提示：**
- 連續簽到獎勵會遞增
- 超過48小時未簽到會中斷連續記錄
- 第7天起每天固定 2200 + 300×天數
"""

    await interaction.response.send_message(message)


@bot.tree.command(name="簽到排行榜", description="查看簽到排行榜")
async def checkin_leaderboard(interaction: discord.Interaction):
    """簽到排行榜"""
    # 排序：先按連續天數，再按總簽到次數
    sorted_users = sorted(
        DailyCheckIn.user_checkin.items(),
        key=lambda x: (x[1]['streak'], x[1]['total_checkins']),
        reverse=True
    )[:10]

    if not sorted_users:
        await interaction.response.send_message("📊 目前還沒有簽到資料！", ephemeral=True)
        return

    message_parts = [
        "🏆 **簽到排行榜 Top 10**",
        "（按連續天數排序）",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, data) in enumerate(sorted_users, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        streak = data['streak'] + 1
        total = data['total_checkins']

        message_parts.append(f"{medal} **{name}**: {streak}天連續 ({total}次總計)")

    await interaction.response.send_message('\n'.join(message_parts))

# ==================== 💾 資料管理系統 ====================
class DataManager:
    """資料管理系統 - 穩定版本"""
    DATA_FILE = Path("bot_data.json")
    BACKUP_DIR = Path("backups")
    MAX_BACKUPS = 5  # 保留最近 5 個備份

    @classmethod
    def ensure_backup_dir(cls):
        """確保備份目錄存在"""
        if not cls.BACKUP_DIR.exists():
            cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_backup(cls):
        """創建備份"""
        if not cls.DATA_FILE.exists():
            return

        try:
            cls.ensure_backup_dir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = cls.BACKUP_DIR / f"bot_data_{timestamp}.json"

            shutil.copy(cls.DATA_FILE, backup_file)
            print(f"📦 已創建備份：{backup_file.name}")

            # 清理舊備份
            cls.cleanup_old_backups()
        except Exception as e:
            print(f"⚠️ 備份失敗：{e}")

    @classmethod
    def cleanup_old_backups(cls):
        """清理舊備份，只保留最近幾個"""
        try:
            backups = sorted(cls.BACKUP_DIR.glob("bot_data_*.json"), reverse=True)

            for old_backup in backups[cls.MAX_BACKUPS:]:
                old_backup.unlink()
                print(f"🗑️ 已刪除舊備份：{old_backup.name}")
        except Exception as e:
            print(f"⚠️ 清理備份失敗：{e}")

    @classmethod
    def load_data(cls):
        """載入資料（帶錯誤恢復）"""
        if not cls.DATA_FILE.exists():
            print("ℹ️ 尚無儲存資料，將使用空白資料")
            return

        try:
            with open(cls.DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ==================== 載入各系統資料 ====================
            cls._load_money_data(data)
            cls._load_gacha_data(data)
            cls._load_inventory_data(data)
            cls._load_checkin_data(data)
            cls._load_stock_data(data)
            cls._load_achievement_data(data)
            cls._load_shop_data(data)
            cls._load_ranking_data(data)
            cls._load_fortune_data(data)

            print("✅ 資料載入成功！")
            cls._print_load_summary()

        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析錯誤：{e}")
            print(f"   錯誤位置：第 {e.lineno} 行，第 {e.colno} 列")
            print("🔄 嘗試從備份恢復...")

            if cls._restore_from_backup():
                print("✅ 已從備份恢復資料")
                cls.load_data()  # 重新載入
            else:
                print("❌ 無可用備份，將使用空白資料")

        except Exception as e:
            print(f"❌ 資料載入失敗：{e}")
            import traceback
            traceback.print_exc()

    @classmethod
    def _restore_from_backup(cls) -> bool:
        """從備份恢復"""
        try:
            cls.ensure_backup_dir()
            backups = sorted(cls.BACKUP_DIR.glob("bot_data_*.json"), reverse=True)

            for backup in backups:
                try:
                    with open(backup, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # 備份有效，複製回主檔案
                    shutil.copy(backup, cls.DATA_FILE)
                    print(f"✅ 已從 {backup.name} 恢復")
                    return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"❌ 恢復失敗：{e}")
            return False

    @classmethod
    def _load_money_data(cls, data):
        """載入金錢資料"""
        if 'money' in data:
            MoneySystem.user_money = {int(k): v for k, v in data['money'].items()}
        if 'stats' in data:
            MoneySystem.user_stats = {int(k): v for k, v in data['stats'].items()}

    @classmethod
    def _load_gacha_data(cls, data):
        """載入抽卡資料"""
        if 'gacha' in data:
            for user_id, user_data in data['gacha'].items():
                GachaSystem.user_data[int(user_id)] = user_data

    @classmethod
    def _load_inventory_data(cls, data):
        """載入物品資料"""
        if 'inventory' in data:
            InventorySystem.user_inventory = {int(k): v for k, v in data['inventory'].items()}

    @classmethod
    def _load_checkin_data(cls, data):
        """載入簽到資料"""
        if 'checkin' in data:
            for user_id, user_data in data['checkin'].items():
                DailyCheckIn.user_checkin[int(user_id)] = {
                    'last_checkin': None,
                    'streak': user_data.get('streak', 0),
                    'total_checkins': user_data.get('total_checkins', 0),
                    'total_earned': user_data.get('total_earned', 0)
                }
                if user_data.get('last_checkin'):
                    try:
                        DailyCheckIn.user_checkin[int(user_id)]['last_checkin'] = \
                            datetime.fromisoformat(user_data['last_checkin'])
                    except:
                        pass

    @classmethod
    def _load_stock_data(cls, data):
        """載入股票資料"""
        if 'stock_holdings' in data:
            StockSystem.user_holdings = {int(k): v for k, v in data['stock_holdings'].items()}

        if 'stock_trade_history' in data:
            for user_id, trades in data['stock_trade_history'].items():
                StockSystem.trade_history[int(user_id)] = [
                    {**trade, 'time': datetime.fromisoformat(trade['time'])}
                    for trade in trades
                ]

        if 'stock_prices' in data:
            StockSystem.current_prices = data['stock_prices']

        if 'stock_price_history' in data:
            StockSystem.price_history = data['stock_price_history']

    @classmethod
    def _load_achievement_data(cls, data):
        """載入成就資料"""
        if 'achievements' in data:
            AchievementSystem.user_achievements = {
                int(k): v for k, v in data['achievements'].items()
            }

        if 'achievement_tracking' in data:
            AchievementSystem.user_tracking = {
                int(k): v for k, v in data['achievement_tracking'].items()
            }

    @classmethod
    def _load_shop_data(cls, data):
        """載入商城道具"""
        if 'shop_inventory' in data:
            for user_id, items in data['shop_inventory'].items():
                ShopSystem.user_inventory[int(user_id)] = {}
                for item_id, item_data in items.items():
                    ShopSystem.user_inventory[int(user_id)][item_id] = {
                        'quantity': item_data['quantity'],
                        'expires': datetime.fromisoformat(item_data['expires']) if item_data.get('expires') else None,
                        'purchased_at': datetime.fromisoformat(item_data['purchased_at'])
                    }

    @classmethod
    def _load_ranking_data(cls, data):
        """載入牌位資料"""
        if 'rankings' in data:
            RankingSystem.user_rankings = {
                int(k): v for k, v in data['rankings'].items()
            }

    @classmethod
    def _load_fortune_data(cls, data):
        """載入占卜資料"""
        # 簡化版，不處理 date
        if 'fortunes' in data:
            FortuneSystem.user_fortunes = {int(k): v for k, v in data['fortunes'].items()}

        if 'fortune_history' in data:
            FortuneSystem.fortune_history = {int(k): v for k, v in data['fortune_history'].items()}

    @classmethod
    def _print_load_summary(cls):
        """顯示載入摘要"""
        print(f"   - 金錢：{len(MoneySystem.user_money)} 位用戶")
        print(f"   - 統計：{len(MoneySystem.user_stats)} 位用戶")
        print(f"   - 抽卡：{len(GachaSystem.user_data)} 位用戶")
        print(f"   - 物品：{len(InventorySystem.user_inventory)} 位用戶")
        print(f"   - 簽到：{len(DailyCheckIn.user_checkin)} 位用戶")
        print(f"   - 股票：{len(StockSystem.user_holdings)} 位用戶")
        print(f"   - 成就：{len(AchievementSystem.user_achievements)} 位用戶")
        print(f"   - 牌位：{len(RankingSystem.user_rankings)} 位用戶")

    @classmethod
    def save_data(cls):
        """儲存資料（帶備份）"""
        try:
            # 1. 創建備份
            if cls.DATA_FILE.exists():
                cls.create_backup()

            # 2. 準備所有資料
            data = cls._prepare_all_data()

            # 3. 先寫入臨時檔案
            temp_file = cls.DATA_FILE.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 4. 驗證臨時檔案
            with open(temp_file, 'r', encoding='utf-8') as f:
                json.load(f)  # 測試是否能正確讀取

            # 5. 替換主檔案
            if cls.DATA_FILE.exists():
                cls.DATA_FILE.unlink()
            temp_file.rename(cls.DATA_FILE)

            print("✅ 資料已安全儲存")
            cls._print_save_summary()

        except Exception as e:
            print(f"❌ 資料儲存失敗：{e}")
            import traceback
            traceback.print_exc()

            # 嘗試刪除損壞的臨時檔案
            temp_file = cls.DATA_FILE.with_suffix('.tmp')
            if temp_file.exists():
                temp_file.unlink()

    @classmethod
    def _prepare_all_data(cls) -> dict:
        """準備所有資料"""
        # 簽到資料
        checkin_data = {}
        for user_id, user_data in DailyCheckIn.user_checkin.items():
            checkin_data[user_id] = {
                'last_checkin': user_data['last_checkin'].isoformat() if user_data.get('last_checkin') else None,
                'streak': user_data.get('streak', 0),
                'total_checkins': user_data.get('total_checkins', 0),
                'total_earned': user_data.get('total_earned', 0)
            }

        # 商城道具
        shop_data = {}
        for user_id, items in ShopSystem.user_inventory.items():
            shop_data[user_id] = {}
            for item_id, item_data in items.items():
                shop_data[user_id][item_id] = {
                    'quantity': item_data['quantity'],
                    'expires': item_data['expires'].isoformat() if item_data.get('expires') else None,
                    'purchased_at': item_data['purchased_at'].isoformat() if item_data.get('purchased_at') else None
                    # 🔧 加上檢查
                }

        # 股票交易記錄
        stock_trades = {}
        for user_id, trades in StockSystem.trade_history.items():
            stock_trades[user_id] = [
                {
                    **{k: v for k, v in trade.items() if k != 'time'},  # 🔧 排除 time
                    'time': trade['time'].isoformat() if 'time' in trade and trade['time'] else None  # 🔧 安全轉換
                }
                for trade in trades
            ]

        # 🆕 占卜資料（簡化版，不處理 datetime）
        fortune_data = {}
        for user_id, fortune in FortuneSystem.user_fortunes.items():
            fortune_data[user_id] = {
                'fortune_id': fortune.get('fortune_id'),
                'special_event': fortune.get('special_event')
            }

        # 組合所有資料
        return {
            'money': MoneySystem.user_money,
            'stats': MoneySystem.user_stats,
            'gacha': GachaSystem.user_data,
            'inventory': InventorySystem.user_inventory,
            'checkin': checkin_data,
            'stock_holdings': StockSystem.user_holdings,
            'stock_trade_history': stock_trades,
            'stock_prices': StockSystem.current_prices,
            'stock_price_history': StockSystem.price_history,
            'fortunes': fortune_data,
            'fortune_history': FortuneSystem.fortune_history,
            'achievements': AchievementSystem.user_achievements,
            'achievement_tracking': AchievementSystem.user_tracking,
            'shop_inventory': shop_data,
            'rankings': RankingSystem.user_rankings
        }


    @classmethod
    def _print_save_summary(cls):
        """顯示儲存摘要"""
        print(f"   - 金錢：{len(MoneySystem.user_money)} 位用戶")
        print(f"   - 統計：{len(MoneySystem.user_stats)} 位用戶")
        print(f"   - 抽卡：{len(GachaSystem.user_data)} 位用戶")
        print(f"   - 物品：{len(InventorySystem.user_inventory)} 位用戶")
        print(f"   - 簽到：{len(DailyCheckIn.user_checkin)} 位用戶")
        print(f"   - 股票：{len(StockSystem.user_holdings)} 位用戶")


def cleanup_files(*files: str) -> None:
    """清理檔案"""
    for file in files:
        try:
            if os.path.exists(file):
                os.remove(file)
        except:
            pass


# ==================== 定期自動儲存 ====================
async def auto_save():
    """每 5 分鐘自動儲存一次"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(300)  # 5 分鐘
        DataManager.save_data()
        print("🔄 自動儲存完成")


# ==================== Bot 事件處理 ====================
@bot.event
async def on_ready():
    """當 Bot 準備就緒時"""
    print(f'🔥 Bot 已登入為 {bot.user}')

    # 載入資料
    DataManager.load_data()

    # ⭐ 初始化股票系統
    StockSystem.initialize()

    # ⭐ 啟動股票價格更新
    bot.loop.create_task(update_stock_prices())

    # 啟動自動儲存
    bot.loop.create_task(auto_save())

    await bot.change_presence(activity=discord.Game(name="Powered / Made by yulun"))

    try:
        synced = await bot.tree.sync()
        print(f'✅ 已同步 {len(synced)} 個指令')
    except Exception as e:
        print(f'❌ 同步指令時發生錯誤: {e}')


@bot.event
async def on_message(message):
    """當收到訊息時"""
    if message.author == bot.user:
        return

    # 檢查「幹」
    if message.content.strip() == "幹":
        await message.channel.send("幹")
        return

    # 檢查是否 mention 機器人
    if bot.user.mentioned_in(message):
        reply = random.choice(RANDOM_REPLIES)
        await message.reply(reply)

    await bot.process_commands(message)


# ==================== 💸 金錢相關指令 ====================

@bot.tree.command(name="查看金錢", description="查看金錢（可指定對象）")
@app_commands.describe(對象="要查看的對象（預設為自己）")
async def check_money(interaction: discord.Interaction, 對象: discord.User = None):
    """查看金錢"""
    # 如果有指定對象就用該對象，否則使用指令發送者(自己)
    target_user = 對象 or interaction.user

    money = MoneySystem.get_money(target_user.id)

    await interaction.response.send_message(
        f"💰 **{target_user.display_name} 的錢包**\n"
        f"目前金錢：**{money}** 元"
    )


@bot.tree.command(name="轉帳", description="轉帳給其他玩家（手續費 5%）")
@app_commands.describe(
    對象="要轉帳的對象",
    金額="要轉帳的金額"
)
async def transfer(interaction: discord.Interaction, 對象: discord.User, 金額: int):
    """轉帳系統"""
    user_id = interaction.user.id

    # 檢查是否轉給自己
    if 對象.id == user_id:
        await interaction.response.send_message("❌ 不能轉帳給自己！", ephemeral=True)
        return

    # 檢查金額
    if 金額 <= 0:
        await interaction.response.send_message("❌ 金額必須大於 0！", ephemeral=True)
        return

    # 計算手續費
    fee = int(金額 * TRANSFER_FEE_RATE)
    total = 金額 + fee

    # 檢查餘額
    current_money = MoneySystem.get_money(user_id)
    if current_money < total:
        await interaction.response.send_message(
            f"❌ 金錢不足！\n"
            f"需要：**{total}** 元（包含 {fee} 元手續費）\n"
            f"你只有：**{current_money}** 元",
            ephemeral=True
        )
        return

    # 執行轉帳
    success, actual_fee = MoneySystem.transfer_money(user_id, 對象.id, 金額)

    if success:
        await interaction.response.send_message(
            f"✅ **轉帳成功！**\n"
            f"從 {interaction.user.mention} → {對象.mention}\n"
            f"💰 金額：**{金額}** 元\n"
            f"💸 手續費：**{actual_fee}** 元\n"
            f"📊 你的剩餘：**{MoneySystem.get_money(user_id)}** 元"
        )
    else:
        await interaction.response.send_message("❌ 轉帳失敗！", ephemeral=True)


# ==================== 🎮 賺錢小遊戲 ====================

@bot.tree.command(name="賺錢", description="回答數學題賺錢（冷卻時間 5 秒）")
async def earn_money_math(interaction: discord.Interaction):
    if interaction.channel.name != "賺錢":
        await interaction.response.send_message(
            "❌ 此指令只能在 #賺錢 頻道使用！",
            ephemeral=True
        )
        return
    user_id = interaction.user.id

    # 檢查冷卻
    remaining = MoneySystem.check_cooldown(user_id)
    if remaining is not None:
        await interaction.response.send_message(
            f"⏰ 冷卻中！請等待 **{remaining}** 秒",
            ephemeral=True
        )
        return

    # 生成數學題
    num1 = random.randint(1, 50)
    num2 = random.randint(1, 50)
    operation = random.choice(['+', '-', '*'])

    if operation == '+':
        answer = num1 + num2
        question = f"{num1} + {num2}"
    elif operation == '-':
        answer = num1 - num2
        question = f"{num1} - {num2}"
    else:
        answer = num1 * num2
        question = f"{num1} × {num2}"

    await interaction.response.send_message(
        f"🧮 **數學題時間！**\n"
        f"請在 10 秒內回答：\n"
        f"**{question} = ?**"
    )

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', timeout=10.0, check=check)

        try:
            user_answer = int(msg.content.strip())
        except ValueError:
            await interaction.followup.send("❌ 請輸入數字！")
            return

        if user_answer == answer:
            # 設置冷卻
            MoneySystem.set_cooldown(user_id)

            # 獎勵
            if random.random() < 0.4:
                reward = random.randint(20, 300)
            else:
                reward = random.randint(300, 2200)

            MoneySystem.add_money(user_id, reward)
            current_money = MoneySystem.get_money(user_id)
            await AchievementSystem.check_and_unlock(user_id, interaction.channel)
            await interaction.followup.send(
                f"✅ **答對了！**\n"
                f"💰 獲得 **{reward}** 元\n"
                f"目前金錢：**{current_money}** 元"
            )
        else:
            MoneySystem.deduct_money(user_id, 200)
            current_money = MoneySystem.get_money(user_id)
            await AchievementSystem.check_and_unlock(user_id, interaction.channel)
            await interaction.followup.send(
                f"❌ **答錯了！**\n"
                f"正確答案是：**{answer}**\n"
                f"💸 扣除 **200** 元\n"
                f"目前金錢：**{current_money}** 元"
            )

    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ 時間到！沒有回答")


@bot.tree.command(name="猜數字", description="猜數字遊戲（1-5，賭 1000 元，猜對得 4500 元）")
@app_commands.describe(數字="你的猜測（1-5）")
@app_commands.choices(數字=[
    app_commands.Choice(name='1', value=1),
    app_commands.Choice(name='2', value=2),
    app_commands.Choice(name='3', value=3),
    app_commands.Choice(name='4', value=4),
    app_commands.Choice(name='5', value=5),
])
async def guess_number(interaction: discord.Interaction, 數字: app_commands.Choice[int]):
    """猜數字遊戲"""
    user_id = interaction.user.id
    bet = 1000
    reward = 4500

    # 檢查金錢
    if not MoneySystem.deduct_money(user_id, bet):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ 金錢不足！需要 **{bet}** 元，你只有 **{current_money}** 元",
            ephemeral=True
        )
        return

    # 遊戲邏輯
    answer = MiniGames.guess_number_game()
    player_guess = 數字.value

    MoneySystem.get_stats(user_id)['games_played'] += 1

    if player_guess == answer:
        MoneySystem.add_money(user_id, reward)
        MoneySystem.get_stats(user_id)['games_won'] += 1
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🎉 **猜對了！**\n"
            f"答案是：**{answer}**\n"
            f"💰 獲得：**{reward}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    else:
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"❌ **猜錯了！**\n"
            f"答案是：**{answer}**\n"
            f"你猜的是：**{player_guess}**\n"
            f"💸 損失：**{bet}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )


@bot.tree.command(name="剪刀石頭布", description="和機器人對賭剪刀石頭布（賭 2000 元，贏得 3600 元）")
@app_commands.describe(選擇="你的選擇")
@app_commands.choices(選擇=[
    app_commands.Choice(name='✂️ 剪刀', value='剪刀'),
    app_commands.Choice(name='🪨 石頭', value='石頭'),
    app_commands.Choice(name='📄 布', value='布'),
])
async def rps(interaction: discord.Interaction, 選擇: app_commands.Choice[str]):
    """剪刀石頭布對賭"""
    user_id = interaction.user.id
    bet = 2000
    reward = 3600

    # 檢查金錢
    if not MoneySystem.deduct_money(user_id, bet):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ 金錢不足！需要 **{bet}** 元，你只有 **{current_money}** 元",
            ephemeral=True
        )
        return

    # 遊戲邏輯
    bot_choice, result = MiniGames.rock_paper_scissors(選擇.value)

    emoji_map = {
        '剪刀': '✂️',
        '石頭': '🪨',
        '布': '📄'
    }

    MoneySystem.get_stats(user_id)['games_played'] += 1

    if result == 'win':
        MoneySystem.add_money(user_id, reward)
        MoneySystem.get_stats(user_id)['games_won'] += 1
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🎉 **你贏了！**\n"
            f"你出：{emoji_map[選擇.value]} {選擇.value}\n"
            f"機器人出：{emoji_map[bot_choice]} {bot_choice}\n"
            f"💰 獲得：**{reward}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    elif result == 'lose':
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"💀 **你輸了！**\n"
            f"你出：{emoji_map[選擇.value]} {選擇.value}\n"
            f"機器人出：{emoji_map[bot_choice]} {bot_choice}\n"
            f"💸 損失：**{bet}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    else:
        MoneySystem.add_money(user_id, bet)  # 退回賭注
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🤝 **平手！**\n"
            f"你出：{emoji_map[選擇.value]} {選擇.value}\n"
            f"機器人出：{emoji_map[bot_choice]} {bot_choice}\n"
            f"💰 退回賭注：**{bet}** 元"
        )


@bot.tree.command(name="骰子比大小", description="和機器人比骰子大小（賭 2000 元，贏得 4700 元）")
async def dice_game(interaction: discord.Interaction):
    """骰子比大小"""
    user_id = interaction.user.id
    bet = 2000
    reward = 4700

    # 檢查金錢
    if not MoneySystem.deduct_money(user_id, bet):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ 金錢不足！需要 **{bet}** 元，你只有 **{current_money}** 元",
            ephemeral=True
        )
        return

    # 遊戲邏輯
    player_dice, bot_dice, result = MiniGames.dice_game()

    MoneySystem.get_stats(user_id)['games_played'] += 1

    if result == 'win':
        MoneySystem.add_money(user_id, reward)
        MoneySystem.get_stats(user_id)['games_won'] += 1
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🎉 **你贏了！**\n"
            f"🎲 你的骰子：**{player_dice}** 點\n"
            f"🎲 機器人骰子：**{bot_dice}** 點\n"
            f"💰 獲得：**{reward}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    elif result == 'lose':
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"💀 **你輸了！**\n"
            f"🎲 你的骰子：**{player_dice}** 點\n"
            f"🎲 機器人骰子：**{bot_dice}** 點\n"
            f"💸 損失：**{bet}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    else:
        MoneySystem.add_money(user_id, bet)  # 退回賭注
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🤝 **平手！**\n"
            f"🎲 你的骰子：**{player_dice}** 點\n"
            f"🎲 機器人骰子：**{bot_dice}** 點\n"
            f"💰 退回賭注：**{bet}** 元"
        )


# ==================== 🎰 賭博系統 ====================

@bot.tree.command(name="賭博", description="賭博賺大錢！入門門檻 500 元")
@app_commands.describe(金額="要賭的金額")
async def gamble(interaction: discord.Interaction, 金額: int):
    """賭博系統"""
    # 檢查是否在賭博頻道
    if interaction.channel.name != "賭博-法國口音":
        await interaction.response.send_message(
            "❌ 此指令只能在 #賭博-法國口音 頻道使用！",
            ephemeral=True
        )
        return

    user_id = interaction.user.id
    current_money = MoneySystem.get_money(user_id)

    # 檢查門檻
    if current_money < 500:
        await interaction.response.send_message(
            f"❌ 金錢不足！\n"
            f"賭博入門門檻：**500** 元\n"
            f"你目前只有：**{current_money}** 元",
            ephemeral=True
        )
        return

    # 檢查金額
    if 金額 <= 0:
        await interaction.response.send_message("❌ 金額必須大於 0！", ephemeral=True)
        return

    if 金額 > current_money:
        await interaction.response.send_message(
            f"❌ 金錢不足！你只有：**{current_money}** 元",
            ephemeral=True
        )
        return

    # 扣除賭注
    MoneySystem.deduct_money(user_id, 金額)

    # 執行賭博
    is_win, amount, tier = GambleSystem.gamble(user_id, 金額)

    if is_win:
        MoneySystem.add_money(user_id, amount)
        profit = amount - 金額

        await interaction.response.send_message(
            f"🎰 **{tier}**\n"
            f"💰 賭注：**{金額}** 元\n"
            f"🎉 **你贏了！**\n"
            f"💵 獲得：**{amount}** 元（淨賺 **{profit}** 元）\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    else:
        await interaction.response.send_message(
            f"🎰 **{tier}**\n"
            f"💰 賭注：**{金額}** 元\n"
            f"💀 **你輸了！**\n"
            f"💸 損失：**{金額}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )


@bot.tree.command(name="賭博詳情", description="查看賭博系統的賠率和勝率說明")
async def gamble_info(interaction: discord.Interaction):
    """賭博詳情"""
    info_message = """
🎰 **賭博系統詳情**

💰 **入門門檻：500 元**

📊 **賭注等級與賠率：**

**🟢 小賭怡情（1 ~ 500 元）**
├ 賠率：**2 倍**
├ 勝率：**60%**
└ 範例：賭 500 元 → 贏了獲得 1000 元（淨賺 500）

**🟡 中等賭局（501 ~ 2000 元）**
├ 賠率：**3 倍**
├ 勝率：**40%**
└ 範例：賭 2000 元 → 贏了獲得 6000 元（淨賺 4000）

**🟠 高風險賭局（2001 ~ 5000 元）**
├ 賠率：**5 倍**
├ 勝率：**19%**
└ 範例：賭 5000 元 → 贏了獲得 25000 元（淨賺 20000）

**🔴 豪賭（5001 元以上）**
├ 賠率：**10 倍**
├ 勝率：**10%**
└ 範例：賭 10000 元 → 贏了獲得 100000 元（淨賺 90000）

⚠️ **注意事項：**
- 輸了會損失全部賭注
- 賭越大，風險越高，報酬也越高
- 請量力而為，理性賭博
"""
    await interaction.response.send_message(info_message)


# ==================== 🎲 抽卡系統 ====================

@bot.tree.command(name="單抽", description="進行一次單抽（需要 120 元）")
async def single_pull_command(interaction: discord.Interaction):
    """單抽"""
    user_id = interaction.user.id

    if not MoneySystem.deduct_money(user_id, 120):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ 金錢不足！需要 **120** 元，你只有 **{current_money}** 元",
            ephemeral=True
        )
        return

    result = GachaSystem.single_pull(user_id)
    data = GachaSystem.get_user_pity(user_id)

    message_parts = [
        f"🎲 **{interaction.user.display_name} 的單抽結果**",
        f"💸 花費：**120** 元",
        ""
    ]

    if isinstance(result, tuple):
        if result[0] == 'gold_up':
            message_parts.append(f"🟡 **五星！**")
            message_parts.append(f"✨ **恭喜抽中 UP 角色「{GachaSystem.current_up_character}」！** (第{result[1]}抽)")
        elif result[0] == 'gold_off':
            message_parts.append(f"🟠 **五星！**")
            message_parts.append(f"🟠 **歪了 {result[1]} (第{result[2]}抽)...下次大保底**")
    elif result == 'purple':
        message_parts.append(f"🟣 **四星**")
    else:
        message_parts.append(f"🔵 **三星**")

    message_parts.append("")
    message_parts.append(f"📊 距上次五星: {data['pity_count']} 抽")
    message_parts.append(f"🟣 距上次四星: {data['four_star_pity']} 抽")
    message_parts.append(f"💰 剩餘金錢: {MoneySystem.get_money(user_id)} 元")

    if data['guarantee']:
        message_parts.append("🎯 **大保底狀態**（下次五星必定UP）")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="十連抽", description="崩壞星穹鐵道風格十連抽（需要 1200 元）")
async def ten_pull(interaction: discord.Interaction):
    """十連抽"""
    user_id = interaction.user.id

    if not MoneySystem.deduct_money(user_id, 1200):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ 金錢不足！需要 **1200** 元，你只有 **{current_money}** 元",
            ephemeral=True
        )
        return

    results = GachaSystem.ten_pull(user_id)

    gold_up_list = []
    gold_off_list = []

    for r in results:
        if isinstance(r, tuple):
            if r[0] == 'gold_up':
                gold_up_list.append(r[1])
            elif r[0] == 'gold_off':
                gold_off_list.append((r[1], r[2]))

    purple = results.count('purple')
    blue = sum(1 for r in results if r == 'blue')
    gold_count = len(gold_up_list) + len(gold_off_list)

    if gold_count >= 3:
        tracking = AchievementSystem.get_user_tracking(user_id)
        tracking['ten_pull_3_gold'] += 1

    display = GachaSystem.format_results(results)

    message_parts = [
        f"🎲 **{interaction.user.display_name} 的十連結果**",
        f"💸 花費：**1200** 元",
        "",
        display,
        "",
        f"🔵 三星: {blue}  🟣 四星: {purple}  🟡 五星: {gold_count}",
    ]

    if gold_up_list:
        pulls_text = '、'.join([f"第{p}抽" for p in gold_up_list])
        message_parts.append(f"✨ **恭喜抽中 UP 角色「{GachaSystem.current_up_character}」！** ({pulls_text})")

    if gold_off_list:
        off_texts = [f"{char}(第{pull}抽)" for char, pull in gold_off_list]
        off_banner_text = '、'.join(off_texts)
        message_parts.append(f"🟠 **歪了 {off_banner_text}...下次大保底**")

    updated_data = GachaSystem.get_user_pity(user_id)
    message_parts.append(f"\n📊 距上次五星: {updated_data['pity_count']} 抽")
    message_parts.append(f"🟣 距上次四星: {updated_data['four_star_pity']} 抽")
    message_parts.append(f"💰 剩餘金錢: {MoneySystem.get_money(user_id)} 元")

    if updated_data['guarantee']:
        message_parts.append("🎯 **大保底狀態**（下次五星必定UP）")

    await AchievementSystem.check_and_unlock(user_id, interaction.channel)
    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="查詢保底", description="查看你的抽卡保底狀態")
async def check_pity(interaction: discord.Interaction):
    """查詢保底"""
    user_id = interaction.user.id
    data = GachaSystem.get_user_pity(user_id)

    message = [
        f"📊 **{interaction.user.display_name} 的保底狀態**",
        f"",
        f"🎲 距上次五星: **{data['pity_count']}** / 90 抽",
        f"🟣 距上次四星: **{data['four_star_pity']}** / 10 抽",
        f"🎯 大保底: **{'是' if data['guarantee'] else '否'}**",
        f"",
    ]

    if data['guarantee']:
        message.append(f"✨ 下次五星必定是 UP 角色「{GachaSystem.current_up_character}」！")
    else:
        message.append("💫 下次五星有 50% 機率 UP")

    if data['pity_count'] >= 73:
        message.append(f"🔥 已進入軟保底區間！（73抽後概率大幅提升）")

    await interaction.response.send_message('\n'.join(message))


@bot.tree.command(name="歷史抽出", description="查看你的五星抽出歷史記錄")
async def gacha_history(interaction: discord.Interaction):
    """歷史抽出"""
    user_id = interaction.user.id
    data = GachaSystem.get_user_pity(user_id)
    history = data.get('history', [])

    if not history:
        await interaction.response.send_message("📝 你還沒有五星抽出記錄喔！", ephemeral=True)
        return

    message_parts = [
        f"📜 **{interaction.user.display_name} 的五星抽出歷史**",
        ""
    ]

    for idx, (rarity_type, char_name, pull_count) in enumerate(history, 1):
        if rarity_type == '五星UP':
            message_parts.append(f"{idx}. 🟡 {char_name} (第{pull_count}抽)")
        else:
            message_parts.append(f"{idx}. 🟠 {char_name} (第{pull_count}抽)")

    message_parts.append("")
    message_parts.append(f"總計抽出五星: **{len(history)}** 次")

    up_count = sum(1 for r in history if r[0] == '五星UP')
    off_count = len(history) - up_count

    message_parts.append(f"UP角色: {up_count} 次")
    message_parts.append(f"歪了: {off_count} 次")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="機率說明", description="查看抽卡機率提升機制說明")
async def gacha_rates(interaction: discord.Interaction):
    """機率說明"""
    explanation = """
📊 **崩壞星穹鐵道 抽卡機率說明**

**五星機率：**
- 基礎機率：**0.6%**
- 綜合機率（含保底）：**1.6%**
- 硬保底：**90 抽**必出五星

**軟保底機制（機率提升）：**
- 從第 **73 抽**開始，每抽機率提升 **6%**
- 第 73 抽：0.6% + 6% = **6.6%**
- 第 74 抽：0.6% + 12% = **12.6%**
- 第 75 抽：0.6% + 18% = **18.6%**
- ...依此類推，越抽越容易出

**四星機率：**
- 基礎機率：**5.1%**
- 綜合機率（含保底）：**13%**
- 硬保底：**10 抽**必出四星

**UP 機率（小保底 & 大保底）：**
- 小保底：抽中五星有 **50%** 是 UP 角色
- 大保底：如果歪了，下次五星 **100%** 是 UP 角色

**範例：**
假設你已經 72 抽沒出金：
→ 第 73 抽：6.6% 出金機率
→ 第 74 抽：12.6% 出金機率
→ 第 80 抽：48.6% 出金機率
→ 第 90 抽：**100%** 必出（硬保底）
"""
    await interaction.response.send_message(explanation)


@bot.tree.command(name="當前up角色", description="查看當前 UP 池的角色")
async def current_up_character(interaction: discord.Interaction):
    """查看UP角色"""
    await interaction.response.send_message(
        f"🎯 **當前 UP 角色：{GachaSystem.current_up_character}**"
    )


@bot.tree.command(name="重置保底", description="重置你的抽卡記錄（僅自己可用）")
async def reset_pity(interaction: discord.Interaction):
    """重置保底"""
    user_id = interaction.user.id
    if user_id in GachaSystem.user_data:
        del GachaSystem.user_data[user_id]

    await interaction.response.send_message("✅ 已重置抽卡記錄！", ephemeral=True)


# ==================== 🎒 物品管理指令 ====================

@bot.tree.command(name="查看背包", description="查看你的抽卡物品庫存")
async def check_inventory(interaction: discord.Interaction):
    """查看背包"""
    user_id = interaction.user.id
    inventory = InventorySystem.get_inventory(user_id)
    total_value = InventorySystem.get_total_value(user_id)

    message = [
        f"🎒 **{interaction.user.display_name} 的背包**",
        "",
        f"🔵 三星：**{inventory['blue']}** 個（單價 {InventorySystem.ITEM_PRICES['blue']} 元）",
        f"🟣 四星：**{inventory['purple']}** 個（單價 {InventorySystem.ITEM_PRICES['purple']} 元）",
        f"🟡 五星UP：**{inventory['gold_up']}** 個（單價 {InventorySystem.ITEM_PRICES['gold_up']} 元）",
        f"🟠 五星歪：**{inventory['gold_off']}** 個（單價 {InventorySystem.ITEM_PRICES['gold_off']} 元）",
        "",
        f"💰 **總價值：{total_value} 元**"
    ]

    await interaction.response.send_message('\n'.join(message))


@bot.tree.command(name="出售物品", description="出售抽卡物品換取金錢")
@app_commands.describe(
    物品類型="要出售的物品類型",
    數量="要出售的數量"
)
@app_commands.choices(物品類型=[
    app_commands.Choice(name='🔵 三星 (30元)', value='blue'),
    app_commands.Choice(name='🟣 四星 (170元)', value='purple'),
    app_commands.Choice(name='🟡 五星UP (2600元)', value='gold_up'),
    app_commands.Choice(name='🟠 五星歪 (2000元)', value='gold_off'),
])
async def sell_item(interaction: discord.Interaction, 物品類型: app_commands.Choice[str], 數量: int):
    """出售物品"""
    user_id = interaction.user.id
    item_type = 物品類型.value

    if 數量 <= 0:
        await interaction.response.send_message("❌ 數量必須大於 0！", ephemeral=True)
        return

    inventory = InventorySystem.get_inventory(user_id)
    current_count = inventory.get(item_type, 0)

    if current_count < 數量:
        await interaction.response.send_message(
            f"❌ 物品數量不足！\n"
            f"你只有：**{current_count}** 個\n"
            f"需要：**{數量}** 個",
            ephemeral=True
        )
        return

    # 執行出售
    success, total_earned = InventorySystem.sell_item(user_id, item_type, 數量)

    if success:
        item_name_map = {
            'blue': '🔵 三星',
            'purple': '🟣 四星',
            'gold_up': '🟡 五星UP',
            'gold_off': '🟠 五星歪'
        }

        await interaction.response.send_message(
            f"✅ **出售成功！**\n"
            f"物品：{item_name_map[item_type]}\n"
            f"數量：**{數量}** 個\n"
            f"💰 獲得：**{total_earned}** 元\n"
            f"目前金錢：**{MoneySystem.get_money(user_id)}** 元"
        )
    else:
        await interaction.response.send_message("❌ 出售失敗！", ephemeral=True)


@bot.tree.command(name="一鍵出售", description="一鍵出售所有指定稀有度的物品")
@app_commands.describe(稀有度="要出售的稀有度")
@app_commands.choices(稀有度=[
    app_commands.Choice(name='🔵 全部三星', value='blue'),
    app_commands.Choice(name='🟣 全部四星', value='purple'),
    app_commands.Choice(name='🟠 全部五星歪', value='gold_off'),
    app_commands.Choice(name='💎 全部三星+四星', value='blue_purple'),
    app_commands.Choice(name='🗑️ 全部物品', value='all'),
])
async def sell_all(interaction: discord.Interaction, 稀有度: app_commands.Choice[str]):
    """一鍵出售"""
    user_id = interaction.user.id
    inventory = InventorySystem.get_inventory(user_id)

    total_earned = 0
    sold_items = []

    if 稀有度.value == 'all':
        # 出售全部
        for item_type in ['blue', 'purple', 'gold_off', 'gold_up']:
            count = inventory[item_type]
            if count > 0:
                success, earned = InventorySystem.sell_item(user_id, item_type, count)
                if success:
                    total_earned += earned
                    sold_items.append((item_type, count, earned))

    elif 稀有度.value == 'blue_purple':
        # 出售三星+四星
        for item_type in ['blue', 'purple']:
            count = inventory[item_type]
            if count > 0:
                success, earned = InventorySystem.sell_item(user_id, item_type, count)
                if success:
                    total_earned += earned
                    sold_items.append((item_type, count, earned))

    else:
        # 出售單一稀有度
        item_type = 稀有度.value
        count = inventory[item_type]
        if count > 0:
            success, earned = InventorySystem.sell_item(user_id, item_type, count)
            if success:
                total_earned += earned
                sold_items.append((item_type, count, earned))

    if not sold_items:
        await interaction.response.send_message("❌ 沒有可以出售的物品！", ephemeral=True)
        return

    item_name_map = {
        'blue': '🔵 三星',
        'purple': '🟣 四星',
        'gold_up': '🟡 五星UP',
        'gold_off': '🟠 五星歪'
    }

    message = [
        "✅ **一鍵出售完成！**",
        ""
    ]

    for item_type, count, earned in sold_items:
        message.append(f"{item_name_map[item_type]}：**{count}** 個 → **{earned}** 元")

    message.append("")
    message.append(f"💰 總獲得：**{total_earned}** 元")
    message.append(f"目前金錢：**{MoneySystem.get_money(user_id)}** 元")

    await interaction.response.send_message('\n'.join(message))

# ==================== 📊 統計與排行榜 ====================

@bot.tree.command(name="個人統計", description="查看你的個人統計面板")
async def personal_stats(interaction: discord.Interaction):
    """個人統計面板"""
    user_id = interaction.user.id
    stats = MoneySystem.get_stats(user_id)
    gacha_stats = GachaSystem.get_gacha_stats(user_id)

    # 計算賭博勝率
    total_gambles = stats['gamble_wins'] + stats['gamble_losses']
    gamble_win_rate = (stats['gamble_wins'] / total_gambles * 100) if total_gambles > 0 else 0

    # 計算遊戲勝率
    games_win_rate = (stats['games_won'] / stats['games_played'] * 100) if stats['games_played'] > 0 else 0

    # 計算淨收益
    net_profit = stats['total_earned'] - stats['total_spent']

    message = f"""
📊 **{interaction.user.display_name} 的統計面板**

💰 **金錢統計：**
├ 目前金錢：**{MoneySystem.get_money(user_id)}** 元
├ 總賺取：**{stats['total_earned']}** 元
├ 總消費：**{stats['total_spent']}** 元
└ 淨收益：**{net_profit}** 元

🎰 **賭博統計：**
├ 總場數：**{total_gambles}** 場
├ 勝場：**{stats['gamble_wins']}** 場
├ 敗場：**{stats['gamble_losses']}** 場
├ 勝率：**{gamble_win_rate:.1f}%**
├ 總贏得：**{stats['gamble_total_won']}** 元
└ 總損失：**{stats['gamble_total_lost']}** 元

🎮 **小遊戲統計：**
├ 遊玩次數：**{stats['games_played']}** 次
├ 勝利次數：**{stats['games_won']}** 次
└ 勝率：**{games_win_rate:.1f}%**

🎲 **抽卡統計：**
├ 總抽數：**{gacha_stats['total_pulls']}** 抽
├ 五星數：**{gacha_stats['five_star_count']}** 個
├ 出金率：**{gacha_stats['five_star_rate']:.2f}%**
├ UP角色：**{gacha_stats['up_count']}** 個
└ UP率：**{gacha_stats['up_rate']:.1f}%**

💸 **轉帳統計：**
├ 轉出金額：**{stats['transfer_sent']}** 元
└ 收到金額：**{stats['transfer_received']}** 元
"""

    await interaction.response.send_message(message)


@bot.tree.command(name="金錢排行榜", description="查看金錢排行榜前 10 名")
async def money_leaderboard(interaction: discord.Interaction):
    """金錢排行榜"""
    leaderboard = LeaderboardSystem.get_money_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 目前還沒有排行榜資料！", ephemeral=True)
        return

    message_parts = [
        "🏆 **金錢排行榜 Top 10**",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, money) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        message_parts.append(f"{medal} **{name}**: {money:,} 元")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="抽卡排行榜", description="查看抽卡次數排行榜前 10 名")
async def gacha_leaderboard(interaction: discord.Interaction):
    """抽卡排行榜"""
    leaderboard = LeaderboardSystem.get_gacha_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 目前還沒有排行榜資料！", ephemeral=True)
        return

    message_parts = [
        "🎲 **抽卡次數排行榜 Top 10**",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, pulls) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        message_parts.append(f"{medal} **{name}**: {pulls} 抽")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="賭神排行榜", description="查看賭博贏最多排行榜前 10 名")
async def gamble_leaderboard(interaction: discord.Interaction):
    """賭神排行榜"""
    leaderboard = LeaderboardSystem.get_gamble_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 目前還沒有排行榜資料！", ephemeral=True)
        return

    message_parts = [
        "🎰 **賭神排行榜 Top 10**",
        "（總贏得 - 總損失）",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, profit) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        sign = "+" if profit >= 0 else ""
        message_parts.append(f"{medal} **{name}**: {sign}{profit:,} 元")

    await interaction.response.send_message('\n'.join(message_parts))


# ==================== 🎉 其他娛樂功能 ====================

@bot.tree.command(name="抽獎", description="測試你的運氣")
async def lottery(interaction: discord.Interaction):
    """抽獎"""
    results = [
        ("💀", "你完了 (50%)", ["skill issue", "loser", "L", "笑死", "可憐哪", "就這？", "廢物", "爛", "菜雞", "弱爆了"]),
        ("🗿", "普通爛 (30%)", ["還好吧", "普普", "mid", "沒什麼", "就那樣", "一般般", "無聊", "無感"]),
        ("😑", "勉強及格 (10%)", ["可以啦", "還行", "不錯喔（才怪）", "繼續加油", "差不多", "湊合"]),
        ("👌", "不錯 (5%)", ["可以", "還行啦", "及格了", "有點東西", "尚可", "OK"]),
        ("✨", "小贏 (3%)", ["恭喜啦", "運氣不錯", "可以可以", "有料", "讚啦"]),
        ("🎉", "贏了 (1.5%)", ["恭喜！", "歐洲人", "運氣好欸", "中大獎", "不錯喔真的", "厲害"]),
        ("💎", "大獎 (0.4%)", ["大獎！！", "歐皇", "太神啦", "運氣爆棚", "贏麻了", "歐到爆"]),
        ("👑", "超級大獎 (0.08%)", ["超級歐皇！", "運氣逆天", "開掛了吧", "太扯了", "神", "這什麼運氣"]),
        ("🌟", "傳說級 (0.02%)", ["傳說降臨！！！", "這不可能", "開掛", "買樂透吧", "去簽大樂透", "WTF"]),
    ]

    weights = [50, 30, 10, 5, 3, 1.5, 0.4, 0.08, 0.02]
    chosen = random.choices(results, weights=weights)[0]

    emoji, title, messages = chosen
    message = random.choice(messages)

    extra_flame = ""
    if title in ["你完了 (50%)", "普通爛 (30%)", "勉強及格 (10%)"]:
        if random.random() < 0.3:
            flames = ["cope", "L", "💀", "🤡", "skill issue", "笑死"]
            extra_flame = f" {random.choice(flames)}"

    result_text = f"{emoji} **{title}**\n{message}{extra_flame}"

    await interaction.response.send_message(result_text)


# ==================== 🔥 火焰特效系統 ====================

@bot.tree.command(name="fire", description="為使用者頭像加上火焰特效")
@app_commands.describe(
    user="選擇要加上火焰特效的使用者（預設為自己）",
    format="輸出格式（預設為 GIF）",
    low_quality="是否使用超低品質（檔案更小）"
)
@app_commands.choices(format=[
    app_commands.Choice(name='GIF', value='gif'),
    app_commands.Choice(name='MP4', value='mp4')
])
async def fire(
        interaction: discord.Interaction,
        user: discord.User = None,
        format: app_commands.Choice[str] = None,
        low_quality: bool = False
):
    """火焰特效"""
    await interaction.response.defer()

    target_user = user or interaction.user
    output_format = format.value if format else 'gif'
    ext = '.gif' if output_format == 'gif' else '.mp4'

    avatar_path = FFmpegComposer.create_temp_path('.png')
    output_path = FFmpegComposer.create_temp_path(ext)

    try:
        if not os.path.exists(FOREGROUND_VIDEO):
            await interaction.followup.send(
                f"❌ 找不到火焰影片檔案：`{FOREGROUND_VIDEO}`\n"
                f"請確認檔案存在於 bot 目錄中。"
            )
            return

        avatar_url = target_user.display_avatar.with_size(1024).with_format('png').url
        await FFmpegComposer.download_file(avatar_url, avatar_path)

        await FFmpegComposer.compose(
            background_path=avatar_path,
            foreground_path=FOREGROUND_VIDEO,
            output_path=output_path,
            output_format=output_format,
            low_quality=low_quality
        )

        file_size = os.path.getsize(output_path)
        if file_size > 25 * 1024 * 1024:
            await interaction.followup.send(
                f"❌ 檔案太大 ({file_size / (1024 * 1024):.1f}MB)！\n"
                f"建議嘗試：\n"
                f"• 使用 `low_quality=True` 參數\n"
                f"• 縮短火焰影片長度\n"
                f"• 選擇 MP4 格式（通常比 GIF 小）"
            )
            return

        # ===== 🆕 追蹤火焰特效使用次數 =====
        tracking = AchievementSystem.get_user_tracking(interaction.user.id)
        tracking['fire_usage'] += 1

        # 檢查成就
        await AchievementSystem.check_and_unlock(interaction.user.id, interaction.channel)
        # ======================================

        quality_text = "（超低品質）" if low_quality else ""
        file = discord.File(output_path, filename=f'fire{ext}')
        await interaction.followup.send(
            f"🔥 **{target_user.mention} Done！**{quality_text}\n",
            file=file
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        await interaction.followup.send(
            f"❌ FFmpeg 處理錯誤：\n```\n{error_msg[:1000]}\n```\n"
            f"請確認 FFmpeg 已正確安裝。"
        )
        print(f"FFmpeg 錯誤詳情：{error_msg}")

    except Exception as e:
        await interaction.followup.send(f"❌ 發生錯誤：{str(e)}")
        print(f"錯誤詳情：{e}")
        import traceback
        traceback.print_exc()

    finally:
        cleanup_files(avatar_path, output_path)


import yt_dlp
from discord import FFmpegPCMAudio
# ==================== 🎵 音樂播放系統 ====================
class MusicPlayer:
    """音樂播放系統"""
    guilds_state: Dict[int, dict] = {}

    # yt-dlp 設定
    YDL_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0',
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'extract_flat': False,
    }

    # 搜尋專用設定 (速度快，只抓標題)
    YDL_SEARCH_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,  # 關鍵：只抓資訊不分析串流，速度快 10 倍
        'nocheckcertificate': True,
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -sn -dn -loglevel error'
    }

    @classmethod
    def get_guild_state(cls, guild_id: int) -> dict:
        if guild_id not in cls.guilds_state:
            cls.guilds_state[guild_id] = {
                'queue': [],
                'current': None,
                'loop': False,
                'auto_play': False,
                'text_channel': None,
                'inactivity_task': None,
                'play_history': [],
                'next_suggestion': None,
            }
        return cls.guilds_state[guild_id]

    @classmethod
    async def get_video_info(cls, query: str) -> Optional[dict]:
        """獲取完整影片資訊（用於播放）"""
        try:
            with yt_dlp.YoutubeDL(cls.YDL_OPTIONS) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(query, download=False)
                )
                if 'entries' in info:
                    info = info['entries'][0]
                return info
        except Exception as e:
            print(f"❌ 獲取影片失敗: {e}")
            return None

    @classmethod
    async def search_candidates(cls, query: str, amount: int = 5) -> list:
        """🆕 搜尋候選影片（互動式選單用）"""
        try:
            with yt_dlp.YoutubeDL(cls.YDL_SEARCH_OPTIONS) as ydl:
                results = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch{amount}:{query}", download=False)
                )
            if not results or 'entries' not in results:
                return []
            return [e for e in results['entries'] if e]
        except Exception as e:
            print(f"❌ 搜尋候選失敗: {e}")
            return []

    @classmethod
    async def search_next_recommendation(cls, guild_id: int):
        """演算法更新：根據「頻道名稱 (Uploader)」搜尋下一首歌曲"""
        state = cls.get_guild_state(guild_id)
        current = state.get('current')
        if not current: return

        # === 核心修改：改用頻道名稱作為主要搜尋依據 ===
        uploader = current.get('uploader', '')
        title = current.get('title', '')

        # 如果有頻道名稱，搜尋 "{頻道名稱} music"
        # 如果沒有頻道名稱，才退回去用標題搜尋
        if uploader:
            query = f"{uploader} music"
        else:
            # 備案：如果抓不到 uploader，嘗試移除標題中的括號內容來搜尋
            import re
            clean_title = re.sub(r'[\(\[].*?[\)\]]', '', title).strip()
            query = f"{clean_title} music"

        print(f"🔍 自動播放搜尋 (基於頻道): {query}")

        try:
            # 使用 extract_flat=True 加快搜尋速度
            with yt_dlp.YoutubeDL(cls.YDL_SEARCH_OPTIONS) as ydl:
                results = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch10:{query}", download=False)
                )

            if not results or 'entries' not in results: return

            candidates = []
            # 取得播放歷史與當前歌曲 ID，避免重複播放
            played_ids = set(state['play_history'])
            if current.get('id'):
                played_ids.add(current.get('id'))

            import difflib
            for entry in results['entries']:
                if not entry: continue
                video_id = entry.get('id')
                video_title = entry.get('title')

                # 過濾 1: 已經播過的
                if video_id in played_ids: continue

                # 過濾 2: 標題太像的 (避免一直是同一首歌的不同版本)
                if difflib.SequenceMatcher(None, title, video_title).ratio() > 0.85: continue

                candidates.append(entry)

                # 🆕 過濾 3: 時長超過 10 分鐘 (600秒) 就跳過
                if entry.get('duration', 0) > 600: continue

                candidates.append(entry)

            if candidates:
                # 從候選名單中隨機挑一首，增加隨機性
                suggestion = random.choice(candidates)
                state['next_suggestion'] = suggestion

                if state['text_channel']:
                    embed = discord.Embed(
                        description=f" **自動推薦：** 下一首將播放 **{suggestion['title']}**",
                        color=discord.Color.teal()
                    )
                    await state['text_channel'].send(embed=embed)
            else:
                print("⚠️ 找不到適合的推薦歌曲")

        except Exception as e:
            print(f"❌ 推薦失敗: {e}")

    @classmethod
    async def play_next(cls, guild_id: int, voice_client, text_channel=None):
        """播放下一首邏輯"""
        state = cls.get_guild_state(guild_id)

        # 1. 記錄歷史
        if state['current']:
            state['play_history'].append(state['current']['id'])
            if len(state['play_history']) > 50: state['play_history'].pop(0)

        # 2. 單曲循環
        if state['loop'] and state['current']:
            info = await cls.get_video_info(state['current']['webpage_url'])
            if info: cls._play_audio(guild_id, voice_client, info)
            return

        # 3. 佇列播放
        if state['queue']:
            next_song = state['queue'].pop(0)
            state['current'] = next_song
            state['next_suggestion'] = None
            cls._play_audio(guild_id, voice_client, next_song)

            if not state['queue'] and state['auto_play']:
                asyncio.create_task(cls.search_next_recommendation(guild_id))
            return

        # 4. 自動播放
        if state['auto_play']:
            if state['next_suggestion']:
                # 取得完整資訊 (因為 flat info 不能播放)
                full_info = await cls.get_video_info(state['next_suggestion']['url'])
                if full_info:
                    state['current'] = full_info
                    state['next_suggestion'] = None
                    cls._play_audio(guild_id, voice_client, full_info)
                    asyncio.create_task(cls.search_next_recommendation(guild_id))
                    return

            # 現場算
            await cls.search_next_recommendation(guild_id)
            if state['next_suggestion']:
                await cls.play_next(guild_id, voice_client, text_channel)
            else:
                state['current'] = None
        else:
            state['current'] = None

    @classmethod
    def _play_audio(cls, guild_id, voice_client, info):
        """底層播放 + 修復 Emoji 狀態顯示"""
        state = cls.get_guild_state(guild_id)
        try:
            source = FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS)
            voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    cls.play_next(guild_id, voice_client, state['text_channel']),
                    voice_client.loop
                )
            )

            # 🆕 優化提示 UI
            if state['text_channel']:
                # 處理時間顯示
                duration_seconds = info.get('duration', 0)
                m, s = divmod(duration_seconds, 60)
                duration_str = f"{m:02d}:{s:02d}"

                embed = discord.Embed(
                    title="🎵 正在播放",
                    description=f"**[{info['title']}]({info['webpage_url']})**",
                    color=discord.Color.from_rgb(255, 105, 180)  # 粉色系
                )

                if info.get('thumbnail'):
                    embed.set_thumbnail(url=info['thumbnail'])

                embed.add_field(name="🎤 頻道/歌手", value=info.get('uploader', '未知'), inline=True)
                embed.add_field(name="⏱️ 時間", value=duration_str, inline=True)

                # === 核心修改：狀態 Emoji 顯示 ===
                status_parts = []

                # 檢查單曲循環
                if state['loop']:
                    status_parts.append("🔂 單曲循環中")

                # 檢查自動播放
                if state['auto_play']:
                    status_parts.append("🤖 自動播放開啟")

                # 檢查佇列
                queue_len = len(state['queue'])
                if queue_len > 0:
                    status_parts.append(f"📝 還有 {queue_len} 首")

                # 組合 Footer 文字
                footer_text = " | ".join(status_parts) if status_parts else "▶️ 正常播放"

                # 設定 Footer icon (可選，這裡用機器人頭像或空白)
                embed.set_footer(text=footer_text, icon_url="https://i.imgur.com/5Nal4Iq.png")

                asyncio.run_coroutine_threadsafe(
                    state['text_channel'].send(embed=embed),
                    voice_client.loop
                )
        except Exception as e:
            print(f"播放錯誤: {e}")
            asyncio.run_coroutine_threadsafe(
                cls.play_next(guild_id, voice_client, state['text_channel']),
                voice_client.loop
            )

    @classmethod
    async def check_voice_channel_empty(cls, guild_id: int, voice_client) -> None:
        while True:
            await asyncio.sleep(60)
            if not voice_client or not voice_client.is_connected(): break
            if len([m for m in voice_client.channel.members if not m.bot]) == 0:
                await voice_client.disconnect()
                MusicPlayer.guilds_state[guild_id]['current'] = None
                break


class StockSystem:
    """
    炒股系統
    - 多支股票可選
    - 價格每分鐘波動
    - 支援買入/賣出
    - 持倉管理
    - 股票走勢圖
    """

    # 股票池 - 可以自由新增
    STOCKS = {
        'AAPL': {'name': '知道幣(5%)', 'base_price': 1000, 'volatility': 0.05},  # 波動率5%
        'TSLA': {'name': '17幣(8%)', 'base_price': 800, 'volatility': 0.08},  # 波動率8%
        'NVDA': {'name': '沙包幣(7%)', 'base_price': 1200, 'volatility': 0.07},
        'GOOG': {'name': '猛攻幣(4%)', 'base_price': 900, 'volatility': 0.04},
        'MSFT': {'name': '夜露幣(5%)', 'base_price': 1100, 'volatility': 0.05},
        'MEME': {'name': '瑪麗幣(15%)', 'base_price': 100, 'volatility': 0.15},  # 高風險高報酬
    }

    # 當前股票價格 {股票代號: 當前價格}
    current_prices: Dict[str, float] = {}

    # 價格歷史記錄 {股票代號: [價格列表]}
    price_history: Dict[str, List[float]] = {}

    # 用戶持倉 {user_id: {股票代號: 數量}}
    user_holdings: Dict[int, Dict[str, int]] = {}

    # 用戶交易記錄 {user_id: [交易記錄]}
    trade_history: Dict[int, List[dict]] = {}

    # 價格更新任務
    price_update_task = None

    @classmethod
    def initialize(cls):
        """初始化股票價格"""
        for symbol, data in cls.STOCKS.items():
            cls.current_prices[symbol] = data['base_price']
            cls.price_history[symbol] = [data['base_price']]
        print("✅ 股票系統已初始化")

    @classmethod
    def update_prices(cls):
        """更新所有股票價格"""
        for symbol, data in cls.STOCKS.items():
            current = cls.current_prices[symbol]
            volatility = data['volatility']

            # 隨機波動 (-volatility% ~ +volatility%)
            change_percent = random.uniform(-volatility, volatility)
            new_price = current * (1 + change_percent)

            # 設置價格下限（不能低於基礎價格的20%）
            min_price = data['base_price'] * 0.2
            new_price = max(new_price, min_price)

            # 更新價格
            cls.current_prices[symbol] = round(new_price, 2)

            # 記錄歷史（最多保留60條）
            cls.price_history[symbol].append(new_price)
            if len(cls.price_history[symbol]) > 60:
                cls.price_history[symbol].pop(0)

    @classmethod
    def get_user_holdings(cls, user_id: int) -> Dict[str, int]:
        """獲取用戶持倉"""
        if user_id not in cls.user_holdings:
            cls.user_holdings[user_id] = {}
        return cls.user_holdings[user_id]

    @classmethod
    def buy_stock(cls, user_id: int, symbol: str, quantity: int) -> Tuple[bool, str, int]:
        """
        買入股票
        返回：(是否成功, 訊息, 花費金額)
        """
        if symbol not in cls.STOCKS:
            return False, "❌ 股票代號不存在！", 0

        if quantity <= 0:
            return False, "❌ 購買數量必須大於 0！", 0

        # 計算成本（包含 1% 手續費）
        price = cls.current_prices[symbol]
        cost = int(price * quantity * 1.01)

        # 檢查金錢
        if not MoneySystem.deduct_money(user_id, cost):
            return False, f"❌ 金錢不足！需要 {cost} 元", 0

        # 增加持倉
        holdings = cls.get_user_holdings(user_id)
        holdings[symbol] = holdings.get(symbol, 0) + quantity

        # 記錄交易
        if user_id not in cls.trade_history:
            cls.trade_history[user_id] = []

        cls.trade_history[user_id].append({
            'type': 'buy',
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'time': datetime.now(),
            'cost': cost
        })

        return True, f"✅ 成功買入 {cls.STOCKS[symbol]['name']}({symbol}) x{quantity}", cost

    @classmethod
    def sell_stock(cls, user_id: int, symbol: str, quantity: int) -> Tuple[bool, str, int]:
        """賣出股票"""
        if symbol not in cls.STOCKS:
            return False, "❌ 股票代號不存在！", 0

        if quantity <= 0:
            return False, "❌ 賣出數量必須大於 0！", 0

        # 檢查持倉
        holdings = cls.get_user_holdings(user_id)
        if holdings.get(symbol, 0) < quantity:
            return False, f"❌ 持倉不足！你只有 {holdings.get(symbol, 0)} 股", 0

        # 計算收益（扣除 1% 手續費）
        price = cls.current_prices[symbol]
        revenue = int(price * quantity * 0.99)

        # ===== 🆕 計算獲利（賣價 - 買價）=====
        # 從交易記錄中找到最早的買入價
        buy_price = None
        if user_id in cls.trade_history:
            for trade in cls.trade_history[user_id]:
                if trade['type'] == 'buy' and trade['symbol'] == symbol:
                    buy_price = trade['price']
                    break

        if buy_price:
            profit = int((price - buy_price) * quantity)
            if profit > 0:
                tracking = AchievementSystem.get_user_tracking(user_id)
                tracking['stock_profit'] += profit
        # =======================================

        # 減少持倉
        holdings[symbol] -= quantity
        if holdings[symbol] == 0:
            del holdings[symbol]

        # 增加金錢
        MoneySystem.add_money(user_id, revenue)

        # 記錄交易
        if user_id not in cls.trade_history:
            cls.trade_history[user_id] = []

        cls.trade_history[user_id].append({
            'type': 'sell',
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'time': datetime.now(),
            'revenue': revenue
        })

        return True, f"✅ 成功賣出 {cls.STOCKS[symbol]['name']}({symbol}) x{quantity}", revenue

    @classmethod
    def get_portfolio_value(cls, user_id: int) -> Tuple[int, Dict[str, dict]]:
        """
        計算用戶持倉總價值
        返回：(總價值, {股票代號: {數量, 當前價, 總值}})
        """
        holdings = cls.get_user_holdings(user_id)
        total_value = 0
        details = {}

        for symbol, quantity in holdings.items():
            current_price = cls.current_prices[symbol]
            stock_value = int(current_price * quantity)
            total_value += stock_value

            details[symbol] = {
                'quantity': quantity,
                'price': current_price,
                'value': stock_value,
                'name': cls.STOCKS[symbol]['name']
            }

        return total_value, details

    @classmethod
    def get_price_trend(cls, symbol: str, periods: int = 10) -> str:
        """
        獲取價格走勢圖（ASCII）
        """
        if symbol not in cls.price_history:
            return ""

        history = cls.price_history[symbol][-periods:]
        if len(history) < 2:
            return ""

        # 計算最大最小值
        max_price = max(history)
        min_price = min(history)
        price_range = max_price - min_price

        if price_range == 0:
            return "價格無變化"

        # 生成 ASCII 圖表（5行高度）
        lines = []
        for i in range(5, 0, -1):
            line = ""
            threshold = min_price + (price_range * i / 5)

            for price in history:
                if price >= threshold:
                    line += "█"
                else:
                    line += " "

            lines.append(line)

        return "\n".join(lines)

    @classmethod
    def get_stock_list(cls) -> str:
        """獲取股票列表"""
        lines = ["📊 **可交易股票列表**\n"]

        for symbol, data in cls.STOCKS.items():
            current_price = cls.current_prices[symbol]
            base_price = data['base_price']

            # 計算漲跌
            change = current_price - base_price
            change_percent = (change / base_price) * 100

            if change > 0:
                # 漲 = 紅色
                trend = f"🔴 +{change:.2f} (+{change_percent:.2f}%)"
            elif change < 0:
                # 跌 = 綠色
                trend = f"🟢 {change:.2f} ({change_percent:.2f}%)"
            else:
                trend = "⚪ 0.00 (0.00%)"

            lines.append(
                f"**{symbol}** - {data['name']}\n"
                f"├ 當前價格：**{current_price:.2f}** 元\n"
                f"└ {trend}\n"
            )

        return "\n".join(lines)


# ==================== 📈 炒股指令 ====================
@bot.tree.command(name="全部股票", description="快速查看所有股票總覽")
async def all_stocks(interaction: discord.Interaction):
    """全部股票總覽"""
    message_parts = [
        "📊 **全部股票總覽**\n"
    ]

    for sym, data in StockSystem.STOCKS.items():
        current_price = StockSystem.current_prices[sym]
        base_price = data['base_price']

        # 計算漲跌
        change = current_price - base_price
        change_percent = (change / base_price) * 100

        # 決定顏色和符號
        if change > 0:
            trend_emoji = "🔴"
            trend_text = f"+{change_percent:.2f}%"
        elif change < 0:
            trend_emoji = "🟢"
            trend_text = f"{change_percent:.2f}%"
        else:
            trend_emoji = "⚪"
            trend_text = "0.00%"

        message_parts.append(
            f"**{sym}** - {data['name']}\n"
            f"├ 價格：**{current_price:.2f}** 元\n"
            f"└ {trend_emoji} {trend_text}\n"
        )

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="股票列表", description="查看所有可交易的股票")
async def stock_list(interaction: discord.Interaction):
    """股票列表"""
    message = StockSystem.get_stock_list()
    await interaction.response.send_message(message)


@bot.tree.command(name="股票詳情", description="查看特定股票的詳細資訊")
@app_commands.describe(股票代號="股票代號（例如：AAPL）")
@app_commands.choices(股票代號=[
    app_commands.Choice(name='AAPL - 知道幣', value='AAPL'),
    app_commands.Choice(name='TSLA - 17幣', value='TSLA'),
    app_commands.Choice(name='NVDA - 沙包幣', value='NVDA'),
    app_commands.Choice(name='GOOG - 猛攻幣', value='GOOG'),
    app_commands.Choice(name='MSFT - 夜露幣', value='MSFT'),
    app_commands.Choice(name='MEME - 瑪麗幣', value='MEME'),
])
async def stock_detail(interaction: discord.Interaction, 股票代號: app_commands.Choice[str]):
    """股票詳情"""
    symbol = 股票代號.value

    if symbol not in StockSystem.STOCKS:
        await interaction.response.send_message("❌ 股票代號不存在！", ephemeral=True)
        return

    stock_data = StockSystem.STOCKS[symbol]
    current_price = StockSystem.current_prices[symbol]
    base_price = stock_data['base_price']

    # 計算漲跌
    change = current_price - base_price
    change_percent = (change / base_price) * 100

    if change > 0:
        # 漲 = 紅色
        trend_emoji = "🔴"
        trend_text = f"+{change:.2f} (+{change_percent:.2f}%)"
    elif change < 0:
        # 跌 = 綠色
        trend_emoji = "🟢"
        trend_text = f"{change:.2f} ({change_percent:.2f}%)"
    else:
        trend_emoji = "⚪"
        trend_text = "0.00 (0.00%)"

    # 獲取走勢圖
    trend_chart = StockSystem.get_price_trend(symbol, 20)

    message = f"""
📊 **{stock_data['name']} ({symbol})**

💰 **當前價格：{current_price:.2f} 元**
📍 基準價格：{base_price:.2f} 元
{trend_emoji} 漲跌：{trend_text}
⚡ 波動率：{stock_data['volatility'] * 100:.0f}%

📈 **近期走勢：**
```
{trend_chart}
```

💡 **交易費用：**
├ 買入手續費：1%
└ 賣出手續費：1%
"""

    await interaction.response.send_message(message)


@bot.tree.command(name="買入股票", description="買入股票")
@app_commands.describe(
    股票代號="股票代號",
    數量="購買數量"
)
@app_commands.choices(股票代號=[
    app_commands.Choice(name='AAPL - 知道幣', value='AAPL'),
    app_commands.Choice(name='TSLA - 17幣', value='TSLA'),
    app_commands.Choice(name='NVDA - 沙包幣', value='NVDA'),
    app_commands.Choice(name='GOOG - 猛攻幣', value='GOOG'),
    app_commands.Choice(name='MSFT - 夜露幣', value='MSFT'),
    app_commands.Choice(name='MEME - 瑪麗幣', value='MEME'),
])
async def buy_stock(interaction: discord.Interaction, 股票代號: app_commands.Choice[str], 數量: int):
    """買入股票"""
    user_id = interaction.user.id
    symbol = 股票代號.value

    success, message, cost = StockSystem.buy_stock(user_id, symbol, 數量)

    if success:
        current_price = StockSystem.current_prices[symbol]
        current_money = MoneySystem.get_money(user_id)

        await interaction.response.send_message(
            f"{message}\n"
            f"💰 單價：**{current_price:.2f}** 元\n"
            f"💸 總花費：**{cost}** 元（含1%手續費）\n"
            f"💵 剩餘金錢：**{current_money}** 元"
        )
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="賣出股票", description="賣出股票")
@app_commands.describe(
    股票代號="股票代號",
    數量="賣出數量"
)
@app_commands.choices(股票代號=[
    app_commands.Choice(name='AAPL - 知道幣', value='AAPL'),
    app_commands.Choice(name='TSLA - 17幣', value='TSLA'),
    app_commands.Choice(name='NVDA - 沙包幣', value='NVDA'),
    app_commands.Choice(name='GOOG - 猛攻幣', value='GOOG'),
    app_commands.Choice(name='MSFT - 夜露幣', value='MSFT'),
    app_commands.Choice(name='MEME - 瑪麗幣', value='MEME'),
])
async def sell_stock(interaction: discord.Interaction, 股票代號: app_commands.Choice[str], 數量: int):
    """賣出股票"""
    user_id = interaction.user.id
    symbol = 股票代號.value

    success, message, revenue = StockSystem.sell_stock(user_id, symbol, 數量)

    if success:
        current_price = StockSystem.current_prices[symbol]
        current_money = MoneySystem.get_money(user_id)

        await interaction.response.send_message(
            f"{message}\n"
            f"💰 單價：**{current_price:.2f}** 元\n"
            f"💵 獲得金額：**{revenue}** 元（扣除1%手續費）\n"
            f"💰 目前金錢：**{current_money}** 元"
        )
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="我的持倉", description="查看你的股票持倉")
async def my_portfolio(interaction: discord.Interaction):
    """我的持倉"""
    user_id = interaction.user.id

    total_value, details = StockSystem.get_portfolio_value(user_id)
    current_money = MoneySystem.get_money(user_id)

    if not details:
        await interaction.response.send_message(
            "📊 **你的股票持倉**\n\n"
            "目前沒有任何持倉\n"
            f"💰 現金：**{current_money}** 元\n"
            f"💎 總資產：**{current_money}** 元",
            ephemeral=True
        )
        return

    message_parts = [
        f"📊 **{interaction.user.display_name} 的股票持倉**\n"
    ]

    for symbol, info in details.items():
        message_parts.append(
            f"**{symbol}** - {info['name']}\n"
            f"├ 持有數量：**{info['quantity']}** 股\n"
            f"├ 當前價格：**{info['price']:.2f}** 元\n"
            f"└ 持倉價值：**{info['value']}** 元\n"
        )

    total_assets = current_money + total_value

    message_parts.append(
        f"\n💰 現金：**{current_money}** 元\n"
        f"📈 股票總值：**{total_value}** 元\n"
        f"💎 總資產：**{total_assets}** 元"
    )

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="交易記錄", description="查看你的股票交易記錄")
async def trade_history(interaction: discord.Interaction):
    """交易記錄"""
    user_id = interaction.user.id

    if user_id not in StockSystem.trade_history or not StockSystem.trade_history[user_id]:
        await interaction.response.send_message("📝 你還沒有任何交易記錄", ephemeral=True)
        return

    history = StockSystem.trade_history[user_id][-10:]  # 最近10筆

    message_parts = [
        f"📝 **{interaction.user.display_name} 的交易記錄**",
        "（最近10筆）\n"
    ]

    for idx, trade in enumerate(reversed(history), 1):
        stock_name = StockSystem.STOCKS[trade['symbol']]['name']
        time_str = trade['time'].strftime('%m/%d %H:%M')

        if trade['type'] == 'buy':
            message_parts.append(
                f"{idx}. 📥 **買入** {stock_name}({trade['symbol']})\n"
                f"   ├ 數量：{trade['quantity']} 股\n"
                f"   ├ 單價：{trade['price']:.2f} 元\n"
                f"   ├ 花費：{trade['cost']} 元\n"
                f"   └ 時間：{time_str}\n"
            )
        else:
            message_parts.append(
                f"{idx}. 📤 **賣出** {stock_name}({trade['symbol']})\n"
                f"   ├ 數量：{trade['quantity']} 股\n"
                f"   ├ 單價：{trade['price']:.2f} 元\n"
                f"   ├ 收入：{trade['revenue']} 元\n"
                f"   └ 時間：{time_str}\n"
            )

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="股票排行榜", description="查看股票大亨排行榜")
async def stock_leaderboard(interaction: discord.Interaction):
    """股票排行榜"""
    # 計算所有用戶的總資產
    rankings = []

    for user_id in StockSystem.user_holdings.keys():
        portfolio_value, _ = StockSystem.get_portfolio_value(user_id)
        cash = MoneySystem.get_money(user_id)
        total_assets = portfolio_value + cash

        rankings.append((user_id, total_assets, portfolio_value, cash))

    # 排序
    rankings.sort(key=lambda x: x[1], reverse=True)
    rankings = rankings[:10]  # 前10名

    if not rankings:
        await interaction.response.send_message("📊 目前還沒有股票交易記錄！", ephemeral=True)
        return

    message_parts = [
        "🏆 **股票大亨排行榜 Top 10**",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, total, stocks, cash) in enumerate(rankings, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."

        message_parts.append(
            f"{medal} **{name}**\n"
            f"   💎 總資產：{total:,} 元\n"
            f"   📈 股票：{stocks:,} 元\n"
            f"   💰 現金：{cash:,} 元\n"
        )

    await interaction.response.send_message('\n'.join(message_parts))


# ==================== 📈 股票價格更新系統 ====================

async def update_stock_prices():
    """每分鐘更新股票價格"""
    await bot.wait_until_ready()

    while not bot.is_closed():
        StockSystem.update_prices()
        print("📊 股票價格已更新")
        await asyncio.sleep(60)  # 每60秒更新一次


# ==================== 🎵 音樂指令（更新版）====================

@bot.tree.command(name="加入", description="讓機器人加入你所在的語音頻道")
async def join_voice(interaction: discord.Interaction):
    """加入語音頻道"""
    # 檢查用戶是否在語音頻道
    if not interaction.user.voice:
        await interaction.response.send_message("❌ 你必須先加入語音頻道！", ephemeral=True)
        return

    # 檢查機器人是否已經在語音頻道
    voice_client = interaction.guild.voice_client

    # 如果機器人已經在其他頻道
    if voice_client and voice_client.is_connected():
        # 檢查是否在同一個頻道
        if voice_client.channel == interaction.user.voice.channel:
            await interaction.response.send_message(
                "✅ 機器人已經在這個語音頻道了！",
                ephemeral=True
            )
            return
        else:
            # 移動到新頻道
            await voice_client.move_to(interaction.user.voice.channel)
            await interaction.response.send_message(
                f"🔄 已移動到 **{interaction.user.voice.channel.name}**"
            )
            return

    # 加入語音頻道
    try:
        voice_client = await interaction.user.voice.channel.connect()

        guild_id = interaction.guild_id
        state = MusicPlayer.get_guild_state(guild_id)

        # 記錄文字頻道
        state['text_channel'] = interaction.channel

        # 🆕 啟動閒置檢查任務
        if state['inactivity_task']:
            state['inactivity_task'].cancel()
        state['inactivity_task'] = bot.loop.create_task(
            MusicPlayer.check_voice_channel_empty(guild_id, voice_client)
        )

        await interaction.response.send_message(
            f"✅ 已加入 **{interaction.user.voice.channel.name}**\n"
            f"💡 使用 `/播放 <網址>` 開始播放音樂"
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ 加入語音頻道時發生錯誤：{str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="清除音樂歷史", description="清除播放歷史記錄")
async def clear_history(interaction: discord.Interaction):
    state = MusicPlayer.get_guild_state(interaction.guild_id)
    count = len(state['play_history'])
    state['play_history'].clear()
    await interaction.response.send_message(f"✅ 已清除 {count} 首播放記錄")


@bot.tree.command(name="播放歷史", description="查看最近播放的歌曲")
async def view_history(interaction: discord.Interaction):
    state = MusicPlayer.get_guild_state(interaction.guild_id)
    history = state['play_history'][-10:]  # 最近 10 首

    if not history:
        await interaction.response.send_message("📝 還沒有播放記錄", ephemeral=True)
        return

    message = "📜 **最近播放記錄**\n\n"
    for idx, song in enumerate(reversed(history), 1):
        message += f"{idx}. {song['title']}\n"

    await interaction.response.send_message(message)


@bot.tree.command(name="重新整理", description="重新獲取當前歌曲的播放連結")
async def refresh_url(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ 目前沒有播放音樂", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    if state['current']:
        voice_client.stop()  # 會自動觸發 play_next
        await interaction.response.send_message("🔄 正在重新整理播放連結...")


# ==================== 🎵 優化後的播放指令 ====================

@bot.tree.command(name="播放", description="貼網址直接播，或輸入關鍵字搜尋選歌")
@app_commands.describe(搜尋="YouTube 網址或關鍵字")
async def play_music(interaction: discord.Interaction, 搜尋: str):
    """播放指令 (支援選單)"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ 請先加入語音頻道！", ephemeral=True)
        return

    await interaction.response.defer()

    guild_id = interaction.guild_id
    state = MusicPlayer.get_guild_state(guild_id)
    state['text_channel'] = interaction.channel

    # 連接語音
    voice_client = interaction.guild.voice_client
    if not voice_client:
        try:
            voice_client = await interaction.user.voice.channel.connect()
            if not state['inactivity_task']:
                state['inactivity_task'] = bot.loop.create_task(
                    MusicPlayer.check_voice_channel_empty(guild_id, voice_client)
                )
        except Exception as e:
            await interaction.followup.send(f"❌ 無法加入語音頻道: {e}")
            return
    else:
        if voice_client.channel != interaction.user.voice.channel:
            await voice_client.move_to(interaction.user.voice.channel)

    # 判斷是否為網址
    target_url = ""
    is_url = 搜尋.startswith("http")

    if is_url:
        target_url = 搜尋
    else:
        # ========== 關鍵字搜尋模式 ==========
        candidates = await MusicPlayer.search_candidates(搜尋, amount=5)

        if not candidates:
            await interaction.followup.send("❌ 找不到相關歌曲。")
            return

        # --- 🛠️ 修復 1: 時間格式化工具 ---
        def format_duration(seconds):
            if not seconds: return "??:??"
            m, s = divmod(int(seconds), 60)
            return f"{m:02d}:{s:02d}"

        # 製作選單
        options_text = ""
        for i, video in enumerate(candidates):
            # 優先抓取秒數來轉換，解決 extract_flat 沒有 duration_string 的問題
            duration_sec = video.get('duration')
            time_str = format_duration(duration_sec)

            options_text += f"**{i + 1}.** {video['title']} `[{time_str}]`\n"

        embed = discord.Embed(
            title=f"🔎 搜尋結果：{搜尋}",
            description=f"{options_text}\n👇 **請在 30 秒內輸入數字 1-{len(candidates)} 選擇**",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)

        # --- 🛠️ 修復 2: 優化輸入檢查 (使用 ID 比對) ---
        def check(m):
            return (
                    m.author.id == interaction.user.id and  # 比對 ID 較安全
                    m.channel.id == interaction.channel_id and  # 比對 ID 較安全
                    m.content.strip().isdigit() and  # 去除空白後檢查是否為數字
                    1 <= int(m.content.strip()) <= len(candidates)
            )

        try:
            # 使用 interaction.client.wait_for 確保使用正確的 bot 實例
            msg = await interaction.client.wait_for('message', timeout=30.0, check=check)

            choice_index = int(msg.content.strip()) - 1
            target_url = candidates[choice_index]['url']

            # 嘗試刪除使用者的數字訊息 (如果機器人有權限)
            try:
                await msg.delete()
            except:
                pass

            await interaction.channel.send(f"✅ 已選擇：**{candidates[choice_index]['title']}**", delete_after=5)

        except asyncio.TimeoutError:
            await interaction.channel.send("⏰ 選擇超時，已取消。")
            return

    # ========== 正式處理播放 (取得完整資訊) ==========
    # 如果原本就是網址，這裡直接用。如果是選出來的，這裡用選到的網址。
    info = await MusicPlayer.get_video_info(target_url)

    if not info:
        await interaction.channel.send("❌ 無法播放此影片 (可能受限或無法讀取)。")
        return

    # 加入播放邏輯
    if voice_client.is_playing():
        state['queue'].append(info)
        embed = discord.Embed(
            description=f"➕ **{info['title']}** 已加入佇列 (第 {len(state['queue'])} 首)",
            color=discord.Color.blue()
        )
        # 如果不是透過選單(是直接貼網址)，用 followup，否則用 channel.send
        if is_url:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.channel.send(embed=embed)
    else:
        state['current'] = info
        MusicPlayer._play_audio(guild_id, voice_client, info)

        # 如果是直接貼網址，因為前面 defer 過，要回覆一下
        if is_url:
            await interaction.followup.send("▶️ 準備播放...")

        # 啟動自動播放演算
        if state['auto_play']:
            asyncio.create_task(MusicPlayer.search_next_recommendation(guild_id))


@bot.tree.command(name="暫停", description="暫停音樂")
async def pause_music(interaction: discord.Interaction):
    """暫停音樂"""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ 目前沒有正在播放的音樂", ephemeral=True)
        return

    voice_client.pause()
    await interaction.response.send_message("⏸️ 已暫停播放")


@bot.tree.command(name="繼續", description="繼續播放音樂")
async def resume_music(interaction: discord.Interaction):
    """繼續播放"""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_paused():
        await interaction.response.send_message("❌ 音樂沒有暫停", ephemeral=True)
        return

    voice_client.resume()
    await interaction.response.send_message("▶️ 繼續播放")


@bot.tree.command(name="跳過", description="跳過當前歌曲")
async def skip_music(interaction: discord.Interaction):
    """跳過歌曲"""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ 目前沒有正在播放的音樂", ephemeral=True)
        return

    voice_client.stop()
    await interaction.response.send_message("⏭️ 已跳過當前歌曲")


@bot.tree.command(name="停止", description="停止播放並清空佇列")
async def stop_music(interaction: discord.Interaction):
    """停止播放"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ 機器人不在語音頻道", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    state['queue'].clear()
    state['current'] = None
    state['loop'] = False
    state['auto_play'] = False  # 🆕 關鍵修復：停止時也要關閉自動播放
    state['next_suggestion'] = None  # 🆕 清除推薦

    voice_client.stop()
    await interaction.response.send_message("⏹️ 已停止播放並清空佇列")


@bot.tree.command(name="循環", description="開啟/關閉單曲循環")
async def loop_music(interaction: discord.Interaction):
    """單曲循環"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ 機器人不在語音頻道", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    state['loop'] = not state['loop']

    status = "開啟" if state['loop'] else "關閉"
    await interaction.response.send_message(f"🔁 單曲循環已{status}")


# 🆕 新增：自動播放指令
@bot.tree.command(name="自動播放", description="開啟/關閉自動播放相關歌曲")
async def auto_play(interaction: discord.Interaction):
    """自動播放"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ 機器人不在語音頻道", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    state['auto_play'] = not state['auto_play']

    status = "開啟" if state['auto_play'] else "關閉"

    message = f"🤖 自動播放已{status}"
    if state['auto_play']:
        message += "\n當播放佇列為空時，將自動搜尋並播放相關歌曲"

    await interaction.response.send_message(message)


@bot.tree.command(name="播放清單", description="查看當前播放佇列")
async def queue_music(interaction: discord.Interaction):
    """查看佇列"""
    state = MusicPlayer.get_guild_state(interaction.guild_id)

    if not state['current'] and not state['queue']:
        await interaction.response.send_message("📝 播放佇列是空的", ephemeral=True)
        return

    message_parts = ["🎵 **當前播放佇列**\n"]

    if state['current']:
        loop_indicator = " 🔁" if state['loop'] else ""
        auto_play_indicator = " 🤖" if state['auto_play'] else ""
        message_parts.append(f"▶️ **正在播放：** {state['current']['title']}{loop_indicator}{auto_play_indicator}\n")

    if state['queue']:
        message_parts.append("**接下來：**")
        for idx, song in enumerate(state['queue'][:10], 1):
            message_parts.append(f"{idx}. {song['title']}")

        if len(state['queue']) > 10:
            message_parts.append(f"\n...還有 {len(state['queue']) - 10} 首")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="離開", description="讓機器人離開語音頻道")
async def leave_voice(interaction: discord.Interaction):
    """離開語音"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ 機器人不在語音頻道", ephemeral=True)
        return

    # 取消閒置檢查任務
    state = MusicPlayer.get_guild_state(interaction.guild_id)
    if state['inactivity_task']:
        state['inactivity_task'].cancel()
        state['inactivity_task'] = None

    await voice_client.disconnect()

    # 清空狀態
    state['queue'].clear()
    state['current'] = None
    state['loop'] = False
    state['auto_play'] = False

    await interaction.response.send_message("👋 已離開語音頻道")


@bot.tree.command(name="正在播放", description="顯示當前播放的歌曲資訊")
async def now_playing(interaction: discord.Interaction):
    """正在播放"""
    state = MusicPlayer.get_guild_state(interaction.guild_id)

    if not state['current']:
        await interaction.response.send_message("❌ 目前沒有正在播放的音樂", ephemeral=True)
        return

    info = state['current']
    duration_text = f"{info['duration'] // 60}:{info['duration'] % 60:02d}" if info['duration'] else "未知"

    embed = discord.Embed(
        title="🎵 正在播放",
        description=f"**{info['title']}**",
        color=discord.Color.green(),
        url=info['webpage_url']
    )

    embed.add_field(name="⏱️ 長度", value=duration_text, inline=True)
    embed.add_field(name="🔁 循環", value="開啟" if state['loop'] else "關閉", inline=True)
    embed.add_field(name="🤖 自動播放", value="開啟" if state['auto_play'] else "關閉", inline=True)
    embed.add_field(name="📝 佇列中", value=f"{len(state['queue'])} 首", inline=True)

    if info['thumbnail']:
        embed.set_thumbnail(url=info['thumbnail'])

    await interaction.response.send_message(embed=embed)


# ==================== 🛠️ 管理員指令 ====================

@bot.tree.command(name="設定金錢", description="設定指定用戶的金錢（管理員限定）")
@app_commands.describe(
    用戶="要設定金錢的用戶",
    金額="要設定的金額"
)
async def set_money(interaction: discord.Interaction, 用戶: discord.User, 金額: int):
    """管理員設定金錢"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 只有管理員可以設定金錢！", ephemeral=True)
        return

    if 金額 < 0:
        await interaction.response.send_message("❌ 金額不能為負數！", ephemeral=True)
        return

    old_money = MoneySystem.get_money(用戶.id)
    MoneySystem.user_money[用戶.id] = 金額

    await interaction.response.send_message(
        f"✅ **金錢已設定！**\n"
        f"用戶：{用戶.mention}\n"
        f"原金錢：**{old_money}** 元\n"
        f"新金錢：**{金額}** 元"
    )


@bot.tree.command(name="調整金錢", description="增加或扣除指定用戶的金錢（管理員限定）")
@app_commands.describe(
    用戶="要調整金錢的用戶",
    金額="要調整的金額（正數為增加，負數為扣除）"
)
async def adjust_money(interaction: discord.Interaction, 用戶: discord.User, 金額: int):
    """管理員調整金錢"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 只有管理員可以調整金錢！", ephemeral=True)
        return

    old_money = MoneySystem.get_money(用戶.id)
    MoneySystem.add_money(用戶.id, 金額)
    new_money = MoneySystem.get_money(用戶.id)

    action = "增加" if 金額 > 0 else "扣除"

    await interaction.response.send_message(
        f"✅ **金錢已{action}！**\n"
        f"用戶：{用戶.mention}\n"
        f"原金錢：**{old_money}** 元\n"
        f"{action}：**{abs(金額)}** 元\n"
        f"新金錢：**{new_money}** 元"
    )


@bot.tree.command(name="設定up角色", description="更改當前 UP 池的角色名稱（管理員限定）")
@app_commands.describe(角色名稱="要設定為 UP 的角色名稱")
async def set_up_character(interaction: discord.Interaction, 角色名稱: str):
    """設定UP角色"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 只有管理員可以更改 UP 角色！", ephemeral=True)
        return

    old_character = GachaSystem.current_up_character
    GachaSystem.current_up_character = 角色名稱

    await interaction.response.send_message(
        f"✅ **UP 角色已更改！**\n"
        f"從「{old_character}」→「{角色名稱}」"
    )

# ==================== 🔫 進階搶劫系統 ====================

class RobberySystem:
    """
    搶劫系統 (包含冷卻、機率計算)
    """
    cooldowns: Dict[int, datetime] = {}
    ROB_COOLDOWN = 180  # 冷卻時間 3 分鐘 (180秒)

    @classmethod
    def check_cooldown(cls, user_id: int) -> Optional[int]:
        """檢查冷卻時間，返回剩餘秒數"""
        if user_id not in cls.cooldowns:
            return None
        elapsed = (datetime.now() - cls.cooldowns[user_id]).total_seconds()
        remaining = cls.ROB_COOLDOWN - elapsed
        if remaining <= 0:
            return None
        return int(remaining)

    @classmethod
    def set_cooldown(cls, user_id: int):
        """設置冷卻時間"""
        cls.cooldowns[user_id] = datetime.now()

    @staticmethod
    def calculate_odds(amount: int) -> Tuple[float, float]:
        """
        計算搶劫機率
        返回：(成功率, 被抓率)
        """
        base_success = 40.0
        base_caught = 50.0

        # 難度係數：金額越大越難
        difficulty = amount / 2000

        success_rate = base_success - difficulty
        caught_rate = base_caught + difficulty

        # 限制機率範圍
        success_rate = max(5.0, min(90.0, success_rate))  # 最低 5%，最高 90%
        caught_rate = max(10.0, min(95.0, caught_rate))  # 最低 10%，最高 95%

        return success_rate, caught_rate


class RobberyView(discord.ui.View):
    """搶劫確認按鈕介面"""

    def __init__(self, interaction: discord.Interaction, target: discord.User, amount: int, success_rate: float,
                 caught_rate: float):
        super().__init__(timeout=30)  # 30秒內要決定
        self.original_interaction = interaction
        self.robber = interaction.user
        self.target = target
        self.amount = amount
        self.success_rate = success_rate
        self.caught_rate = caught_rate
        self.value = None

    async def on_timeout(self):
        # 超時自動取消
        for item in self.children:
            item.disabled = True
        try:
            await self.original_interaction.edit_original_response(content="⏰ 猶豫太久，目標已經走遠了...", view=self)
        except:
            pass

    @discord.ui.button(label="🔥 動手 (確認)", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """確認搶劫按鈕"""
        # 檢查是否為發起人
        if interaction.user.id != self.robber.id:
            await interaction.response.send_message("這不是你的犯罪計畫！", ephemeral=True)
            return

        await interaction.response.defer()  # 防止按鈕轉圈圈

        # 二次檢查金錢（防止確認期間錢被花掉）
        target_money = MoneySystem.get_money(self.target.id)
        robber_money = MoneySystem.get_money(self.robber.id)

        if target_money < self.amount:
            await interaction.followup.send("❌ 目標把錢花掉了！行動取消。", ephemeral=True)
            return

        # ===== 🆕 檢查目標是否有保護道具 =====
        if ShopSystem.has_active_item(self.target.id, 'anti_robbery'):
            embed = discord.Embed(
                title="🛡️ 防禦系統啟動！",
                description=f"{self.target.mention} 的駭客電腦偵測到入侵，你被反制了！",
                color=discord.Color.blue()
            )
            await self.original_interaction.edit_original_response(content=None, embed=embed, view=None)
            self.stop()
            return

        # 開始執行搶劫邏輯
        RobberySystem.set_cooldown(self.robber.id)

        rng = random.uniform(0, 100)

        # === 成功 ===
        if rng < self.success_rate:
            # 🆕 檢查目標是否有保險
            actual_loss = self.amount
            if ShopSystem.has_active_item(self.target.id, 'insurance'):
                actual_loss = int(self.amount * 0.3)  # 保險：只損失 30%
                refund = self.amount - actual_loss
                MoneySystem.add_money(self.target.id, refund)

            # 扣除目標金錢
            MoneySystem.deduct_money(self.target.id, actual_loss)
            # 搶匪獲得金錢
            MoneySystem.add_money(self.robber.id, actual_loss)

            # 🆕 追蹤搶劫成功次數 (成就用)
            tracking = AchievementSystem.get_user_tracking(self.robber.id)
            tracking['robbery_success'] += 1

            embed = discord.Embed(title="🔫 搶劫成功！", color=discord.Color.green())
            embed.description = (
                f"你成功從 {self.target.mention} 身上搶走了 **{actual_loss:,}** 元！\n"
                f"快逃啊！\n\n"
                f"📊 機率檢定：{rng:.1f}% (需 < {self.success_rate:.1f}%)"
            )

            # 如果有保險，顯示賠付資訊
            if actual_loss < self.amount:
                refund_amount = self.amount - actual_loss
                embed.add_field(
                    name="🛡️ 保險生效",
                    value=f"{self.target.mention} 的保險賠付了 {refund_amount:,} 元",
                    inline=False
                )

            # 私訊受害者
            try:
                victim_embed = discord.Embed(
                    title="⚠️ 你被搶劫了！",
                    description=f"**{self.robber.display_name}** 搶走了你 **{actual_loss:,}** 元！",
                    color=discord.Color.red()
                )
                if actual_loss < self.amount:
                    victim_embed.add_field(
                        name="🛡️ 保險理賠",
                        value=f"你的保險幫你減輕了損失，實際只損失 {actual_loss:,} 元",
                        inline=False
                    )
                await self.target.send(embed=victim_embed)
            except:
                pass

        # === 失敗 ===
        else:
            caught_rng = random.uniform(0, 100)

            # --- 被抓到 ---
            if caught_rng < self.caught_rate:
                # 罰款金額為搶劫金額的 30% ~ 50%
                fine_ratio = random.uniform(0.3, 0.5)
                fine = int(self.amount * fine_ratio)

                # 確保罰款不超過搶匪身上的錢
                actual_fine = min(robber_money, fine)

                # 精神賠償金 (罰款的一半給受害者)
                compensation = actual_fine // 2

                MoneySystem.deduct_money(self.robber.id, actual_fine)
                MoneySystem.add_money(self.target.id, compensation)

                embed = discord.Embed(title="🚓 被警察抓到了！", color=discord.Color.red())
                embed.description = (
                    f"你在逃跑時跌倒了，被警察當場壓制！\n"
                    f"💸 支付罰款：**{actual_fine:,}** 元\n"
                    f"🤝 其中 **{compensation:,}** 元賠給了受害者\n\n"
                    f"📊 被抓檢定：{caught_rng:.1f}% (需 < {self.caught_rate:.1f}%)"
                )

            # --- 失敗但逃掉 ---
            else:
                embed = discord.Embed(title="💨 行動失敗 (逃脫)", color=discord.Color.light_grey())
                embed.description = (
                    f"對方警覺性太高，你沒能下手...\n"
                    f"好消息是你跑得夠快，沒被警察抓到。\n\n"
                    f"📊 運氣檢定：搶劫失敗，但未觸發被抓判定。"
                )

        # 🆕 檢查成就
        await AchievementSystem.check_and_unlock(self.robber.id, self.original_interaction.channel)

        # 更新原本的訊息，移除按鈕並顯示結果
        await self.original_interaction.edit_original_response(content=None, embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="🏳️ 算了 (取消)", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """取消按鈕"""
        if interaction.user.id != self.robber.id:
            await interaction.response.send_message("這不是你的犯罪計畫！", ephemeral=True)
            return

        await interaction.response.edit_message(content="❌ 已取消犯罪計畫，當個好公民吧。", view=None, embed=None)
        self.stop()


# ==================== 🔫 搶劫指令 ====================

@bot.tree.command(name="搶劫", description="高風險高報酬！搶劫前會先顯示機率")
@app_commands.describe(
    對象="要搶劫的目標",
    金額="嘗試搶劫的金額"
)
async def rob_player(interaction: discord.Interaction, 對象: discord.User, 金額: int):
    """搶劫指令"""
    user_id = interaction.user.id
    target_id = 對象.id

    # 1. 基本檢查
    if user_id == target_id:
        await interaction.response.send_message("❌ 你不能搶自己！", ephemeral=True)
        return

    if 對象.bot:
        await interaction.response.send_message("❌ 你不能搶機器人！", ephemeral=True)
        return

    if 金額 <= 0:
        await interaction.response.send_message("❌ 金額必須大於 0！", ephemeral=True)
        return

    # 2. 冷卻檢查
    remaining = RobberySystem.check_cooldown(user_id)
    if remaining:
        minutes = remaining // 60
        seconds = remaining % 60
        await interaction.response.send_message(
            f"🚓 警察正在巡邏中！你需要避風頭。\n"
            f"剩餘時間：**{minutes}分 {seconds}秒**",
            ephemeral=True
        )
        return

    # 3. 財力檢查
    target_money = MoneySystem.get_money(target_id)
    if target_money < 金額:
        await interaction.response.send_message(
            f"❌ 目標太窮了！他只有 **{target_money:,}** 元。",
            ephemeral=True
        )
        return

    robber_money = MoneySystem.get_money(user_id)
    min_fine = int(金額 * 0.1)  # 至少要有搶劫金額 10% 的錢才能搶
    if robber_money < min_fine:
        await interaction.response.send_message(
            f"❌ 你的存款太少！\n"
            f"為了支付可能發生的罰款，你身上至少要有 **{min_fine:,}** 元 (搶劫金額的10%)",
            ephemeral=True
        )
        return

    # 4. 計算機率與顯示面板
    success_rate, caught_rate = RobberySystem.calculate_odds(金額)

    embed = discord.Embed(title="📋 犯罪計畫書", color=discord.Color.dark_grey())
    embed.add_field(name="🔪 目標", value=對象.mention, inline=True)
    embed.add_field(name="💰 預計搶劫", value=f"{金額:,} 元", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)  # 空行

    # 根據機率顯示顏色
    s_emoji = "🟢" if success_rate > 50 else "🔴"
    c_emoji = "🟢" if caught_rate < 30 else "🔴"

    embed.add_field(name=f"{s_emoji} 成功率", value=f"**{success_rate:.1f}%**", inline=True)
    embed.add_field(name=f"{c_emoji} 若失敗被抓率", value=f"**{caught_rate:.1f}%**", inline=True)

    max_fine = int(金額 * 0.5)

    # 🆕 檢查目標是否有保護
    if ShopSystem.has_active_item(target_id, 'anti_robbery'):
        embed.add_field(
            name="🛡️ 目標狀態",
            value="⚠️ 目標開啟了駭客電腦保護！",
            inline=False
        )

    if ShopSystem.has_active_item(target_id, 'insurance'):
        embed.add_field(
            name="📋 目標狀態",
            value="ℹ️ 目標購買了保險 (你只能搶走 30%)",
            inline=False
        )

    embed.set_footer(text=f"⚠️ 若被抓，最高罰款約 {max_fine:,} 元")

    view = RobberyView(interaction, 對象, 金額, success_rate, caught_rate)
    await interaction.response.send_message(embed=embed, view=view)


# ==================== ⚔️ 單挑系統 ====================
# ==================== ⚔️ 單挑系統（修復版 + 超多創意文字）====================
class DuelSystem:
    """
    單挑系統
    包含：攻擊、防禦、爆擊、神級外掛
    特色：大量隨機創意文本
    """

    # ==================== 創意文本庫 ====================

    # 1. 神級外掛 (1%) - 傷害 9999
    GOD_TEXTS = [
        "🌌 **{attacker}** 突然頓悟了宇宙真理，對 **{defender}** 降下了「天罰」！(系統判定：直接處決)",
        "💻 **{attacker}** 開啟了開發者控制台，輸入了 `/kill {defender}`...",
        "⚡ **{attacker}** 變身成超級賽亞人藍，一發龜派氣功把 **{defender}** 轟到了外太空！",
        "😈 **{attacker}** 拿出了無限手套，彈了一下手指... **{defender}** 化為了灰燼。",
        "🛑 **{attacker}** 使用了「砸瓦魯多」暫停了時間，並丟出了壓路機！ **{defender}** 毫無還手之力！",
        "🔧 **{attacker}** 發現了這個遊戲的 Bug，直接把 **{defender}** 的血條刪除了。",
        "🗡️ **{attacker}** 召喚了「王之財寶」，無數寶具從天而降！ **{defender}** 被秒殺！",
        "💀 **{attacker}** 使用了死神筆記本，寫下了 **{defender}** 的名字...",
        "🔥 **{attacker}** 發動了「炎炎烈日」，**{defender}** 直接蒸發了！",
        "❄️ **{attacker}** 使用了「絕對零度」，**{defender}** 被凍成冰雕後碎裂！",
        "⚡ **{attacker}** 釋放了千鳥，直接穿透了 **{defender}** 的心臟！",
        "🌊 **{attacker}** 召喚了海嘯，**{defender}** 被捲入深海再也沒有浮上來...",
        "💥 **{attacker}** 使用了大爆炸，**{defender}** 連屍骨都不剩！",
        "🎯 **{attacker}** 開啟了自瞄外掛，爆頭一擊必殺！",
        "🚀 **{attacker}** 發射了核彈，**{defender}** 所在的城市都消失了...",
    ]

    # 2. 爆擊 (15%) - 傷害 30~50
    CRIT_TEXTS = [
        "🔥 **{attacker}** 抓住了 **{defender}** 的破綻，使出了「認真一拳」！ (爆擊)",
        "💢 **{attacker}** 突然想起了前任，把怒氣全部發洩在 **{defender}** 身上！ (情緒傷害爆擊)",
        "🗡️ **{attacker}** 拔出了石中劍，一刀砍向 **{defender}** 的大動脈！ (致命一擊)",
        "💣 **{attacker}** 趁 **{defender}** 不注意，在他褲檔裡塞了一顆手榴彈！ (弱點爆擊)",
        "🚗 **{attacker}** 召喚了一輛異世界卡車，高速衝撞了 **{defender}**！ (轉生爆擊)",
        "🐉 **{attacker}** 召喚了青眼白龍，發動了毀滅的噴射白光！ (粉碎玉碎大喝采)",
        "🧠 **{attacker}** 揭露了 **{defender}** 的黑歷史，造成了巨大的精神傷害！ (真實傷害)",
        "⚔️ **{attacker}** 使用了「拔刀術」，**{defender}** 連反應都來不及！ (先制攻擊)",
        "🦵 **{attacker}** 踢出了「無影腳」，**{defender}** 被踢飛十公尺！",
        "👊 **{attacker}** 使用了「北斗百裂拳」，**{defender}** 已經死了！",
        "🎸 **{attacker}** 彈奏了魔音，**{defender}** 的耳膜破裂！ (音波攻擊)",
        "🔨 **{attacker}** 拿起雷神之錘，一擊把 **{defender}** 砸進地底！",
        "🏹 **{attacker}** 射出了穿心箭，正中 **{defender}** 的要害！",
        "💎 **{attacker}** 使用了「鑽石拳」，**{defender}** 的護甲碎裂！",
        "🌪️ **{attacker}** 召喚了龍捲風，**{defender}** 被捲上天空！",
        "☄️ **{attacker}** 召喚了隕石，**{defender}** 被砸中腦袋！",
        "🦈 **{attacker}** 召喚了鯊魚，**{defender}** 的腿被咬斷了！",
        "🕷️ **{attacker}** 放出了劇毒蜘蛛，**{defender}** 中毒了！",
        "🔪 **{attacker}** 使用了「背刺」，造成了 300% 傷害！",
        "💀 **{attacker}** 使用了「死亡宣告」，**{defender}** 被詛咒了！",
        "⚡ **{attacker}** 釋放了「雷霆萬鈞」，**{defender}** 被電成焦炭！",
        "🧨 **{attacker}** 丟出了 C4 炸藥，**{defender}** 被炸飛了！",
        "🎭 **{attacker}** 使用了「幻術」，**{defender}** 攻擊了自己！",
        "🌙 **{attacker}** 發動了「月讀」，**{defender}** 在幻境中被折磨了 72 小時！",
        "🔥 **{attacker}** 使用了「天照」，黑色火焰燒盡了 **{defender}**！",
    ]

    # 3. 防禦/回復 (15%) - 回復 15~30
    HEAL_TEXTS = [
        "🛡️ **{attacker}** 拿出了一杯珍珠奶茶，邊喝邊看戲。(HP +{heal})",
        "💊 **{attacker}** 覺得苗頭不對，吞了一顆仙豆。(HP +{heal})",
        "🧘 **{attacker}** 原地打坐，開始修煉法輪大法。(HP +{heal})",
        "🍕 **{attacker}** 叫了外送披薩，吃飽了才有力氣打架。(HP +{heal})",
        "💉 **{attacker}** 拿出了急救包，幫自己貼了個 OK 繃。(HP +{heal})",
        "🛡️ **{attacker}** 發動了「絕對防禦」，順便睡了個午覺。(HP +{heal})",
        "✨ **{attacker}** 受到女神的眷顧，聖光治癒了他的傷口。(HP +{heal})",
        "🍖 **{attacker}** 啃了一口烤肉，體力恢復了！(HP +{heal})",
        "☕ **{attacker}** 喝了一杯咖啡，精神抖擻！(HP +{heal})",
        "🍜 **{attacker}** 吃了一碗拉麵，血條瞬間回滿！(HP +{heal})",
        "🧃 **{attacker}** 喝了一瓶能量飲料，活力四射！(HP +{heal})",
        "🍎 **{attacker}** 吃了一顆蘋果，醫生遠離我。(HP +{heal})",
        "🌟 **{attacker}** 撿到了回血包，運氣真好！(HP +{heal})",
        "💤 **{attacker}** 小睡了一下，傷口癒合了。(HP +{heal})",
        "🔮 **{attacker}** 使用了治療術，傷口發光癒合。(HP +{heal})",
        "🎵 **{attacker}** 聽了一首療癒的音樂，心情變好了。(HP +{heal})",
        "🌿 **{attacker}** 使用了草系技能「光合作用」。(HP +{heal})",
        "💧 **{attacker}** 喝了一口聖水，傷勢好轉。(HP +{heal})",
        "🕊️ **{attacker}** 召喚了和平鴿，帶來了治癒之力。(HP +{heal})",
        "🌈 **{attacker}** 看到了彩虹，心情變好，傷勢減輕。(HP +{heal})",
    ]

    # 4. 普通攻擊 (50%) - 傷害 10~25
    NORMAL_TEXTS = [
        "⚔️ **{attacker}** 撿起地上的拖鞋，狠狠抽了 **{defender}** 的臉！",
        "👊 **{attacker}** 對 **{defender}** 使用了普通拳。",
        "⌨️ **{attacker}** 拔起鍵盤，對著 **{defender}** 的頭一頓猛敲！",
        "🦵 **{attacker}** 踢了 **{defender}** 的小拇指！(看著都痛)",
        "🌊 **{attacker}** 潑了 **{defender}** 一身熱水。",
        "🎤 **{attacker}** 開始唱胖虎的歌，**{defender}** 耳朵流血了。",
        "📦 **{attacker}** 丟出一塊樂高，**{defender}** 一腳踩了上去！",
        "📱 **{attacker}** 拿 Nokia 3310 砸向 **{defender}** 的腦門。",
        "📢 **{attacker}** 在 **{defender}** 耳邊大喊「還錢」！",
        "🏀 **{attacker}** 使用了運球過人，順便肘擊了 **{defender}**。",
        "🪑 **{attacker}** 拿起椅子，WWE 摔角手附體！",
        "🥄 **{attacker}** 用湯匙挖了 **{defender}** 一勺！",
        "🧹 **{attacker}** 拿起掃把，把 **{defender}** 當垃圾掃！",
        "🔔 **{attacker}** 拿鈴鐺在 **{defender}** 耳邊搖，吵死了！",
        "📚 **{attacker}** 用厚重的字典砸 **{defender}** 的頭！",
        "🥊 **{attacker}** 使用了直拳，打中了 **{defender}** 的鼻子！",
        "🦶 **{attacker}** 踩了 **{defender}** 的腳，疼！",
        "👋 **{attacker}** 巴了 **{defender}** 一巴掌！",
        "🪛 **{attacker}** 拿螺絲起子戳了 **{defender}** 一下！",
        "🔨 **{attacker}** 拿鐵鎚敲了 **{defender}** 的膝蓋！",
        "🎯 **{attacker}** 丟飛鏢，插在 **{defender}** 的屁股上！",
        "🪃 **{attacker}** 丟出回力鏢，打到 **{defender}** 的後腦勺！",
        "🎱 **{attacker}** 拿撞球砸向 **{defender}**！",
        "🏓 **{attacker}** 用球拍抽了 **{defender}** 的臉！",
        "🥍 **{attacker}** 用球棒敲了 **{defender}** 的頭！",
        "🎾 **{attacker}** 發球，直接打中 **{defender}** 的要害！",
        "⛳ **{attacker}** 揮出高爾夫球桿，打中了 **{defender}**！",
        "🏏 **{attacker}** 用板球拍擊中 **{defender}**！",
        "🏑 **{attacker}** 用曲棍球桿掃向 **{defender}** 的腳！",
        "🥌 **{attacker}** 推出冰壺，砸中 **{defender}** 的腳趾！",
        "🎿 **{attacker}** 用滑雪杖戳了 **{defender}**！",
        "🛹 **{attacker}** 用滑板砸向 **{defender}** 的臉！",
        "🛼 **{attacker}** 穿著直排輪撞向 **{defender}**！",
        "🚴 **{attacker}** 騎腳踏車撞飛了 **{defender}**！",
        "🛴 **{attacker}** 用滑板車的把手戳 **{defender}** 的肚子！",
        "🏍️ **{attacker}** 騎摩托車從 **{defender}** 身上輾過去！",
        "🚙 **{attacker}** 開車撞飛了 **{defender}**！",
        "✈️ **{attacker}** 用紙飛機射中 **{defender}** 的眼睛！",
        "🪁 **{attacker}** 用風箏纏住 **{defender}** 的脖子！",
        "🎈 **{attacker}** 用氣球打 **{defender}** 的頭，很輕但很煩！",
        "🎀 **{attacker}** 用緞帶勒住 **{defender}** 的脖子！",
        "🧵 **{attacker}** 用線纏住 **{defender}** 的手腳！",
        "🪡 **{attacker}** 用針扎了 **{defender}** 一下！",
        "✂️ **{attacker}** 用剪刀剪了 **{defender}** 的頭髮！",
        "📌 **{attacker}** 用圖釘刺 **{defender}** 的屁股！",
        "📍 **{attacker}** 用大頭針扎 **{defender}**！",
        "🔗 **{attacker}** 用鐵鍊抽打 **{defender}**！",
        "🪝 **{attacker}** 用掛鉤勾住 **{defender}** 的衣服！",
        "🧲 **{attacker}** 用磁鐵吸走 **{defender}** 的假牙！",
        "🔋 **{attacker}** 用電池電擊 **{defender}**！",
        "💡 **{attacker}** 用燈泡砸 **{defender}** 的頭！",
    ]

    # 5. 失誤 (19%) - 沒傷害
    MISS_TEXTS = [
        "💨 **{attacker}** 想要攻擊，結果自己左腳絆右腳摔倒了...",
        "📶 **{attacker}** 網路延遲 (Ping: 999ms)，攻擊無效！",
        "👀 **{attacker}** 被路邊的野貓吸引了注意力，忘記攻擊。",
        "💤 **{attacker}** 突然覺得很累，決定休息一回合。",
        "🚫 **{attacker}** 的攻擊被 **{defender}** 用臉接住了！(但是 **{defender}** 臉皮太厚，沒受傷)",
        "🐛 **{attacker}** 遇到 Bug，技能冷卻中...",
        "💃 **{attacker}** 突然開始跳起街舞，錯過了攻擊機會。",
        "🎮 **{attacker}** 手把斷線了，連不上伺服器！",
        "📞 **{attacker}** 的媽媽打電話來，要他回家吃飯。",
        "🦟 **{attacker}** 被蚊子咬了，在那邊抓癢。",
        "🌞 **{attacker}** 被太陽閃到眼睛，看不見了。",
        "💩 **{attacker}** 踩到狗屎滑倒了，攻擊失敗。",
        "🍌 **{attacker}** 踩到香蕉皮，華麗地滑倒了。",
        "🕳️ **{attacker}** 掉進了陷阱，爬不出來。",
        "🌧️ **{attacker}** 被雨淋濕了，凍僵無法動彈。",
        "❄️ **{attacker}** 手凍僵了，握不住武器。",
        "🔥 **{attacker}** 被火燙到，丟掉了武器。",
        "💧 **{attacker}** 滑倒在水灘上，摔了個狗吃屎。",
        "🌪️ **{attacker}** 被風吹歪了，攻擊偏離目標。",
        "⚡ **{attacker}** 被靜電電到，手麻了。",
        "🦅 **{attacker}** 被老鷹叼走了假髮，嚇到無法攻擊。",
        "🐝 **{attacker}** 被蜜蜂螫了，痛到跳起來。",
        "🦂 **{attacker}** 被蠍子螫到，中毒麻痺了。",
        "🐍 **{attacker}** 被蛇嚇到，嚇得動不了。",
        "🦎 **{attacker}** 被蜥蜴爬過，癢得要命。",
        "🐸 **{attacker}** 被青蛙跳到臉上，視線被擋住。",
        "🦗 **{attacker}** 被蟋蟀的叫聲吵到分心。",
        "🪰 **{attacker}** 被蒼蠅煩死了，一直趕蒼蠅。",
        "🕸️ **{attacker}** 被蜘蛛網纏住，動彈不得。",
        "🦇 **{attacker}** 被蝙蝠撞到頭，暈了。",
        "🐁 **{attacker}** 被老鼠嚇到，跳起來尖叫。",
    ]

    @staticmethod
    def draw_hp_bar(current: int, max_hp: int, length: int = 12) -> str:
        """繪製精美血條"""
        current = max(0, current)
        percentage = current / max_hp
        fill = int(percentage * length)
        empty = length - fill

        # 根據血量變色
        status_icon = "💚"
        if percentage < 0.5: status_icon = "💛"
        if percentage < 0.2: status_icon = "❤️"
        if current == 0: status_icon = "💀"

        bar = "█" * fill + "░" * empty
        return f"{status_icon} `[{bar}]` {current}/{max_hp}"

    @staticmethod
    async def run_duel(interaction: discord.Interaction, player: discord.User, target: discord.User):
        # 初始設定
        p1_name = player.display_name
        p2_name = target.display_name

        max_hp = 100
        hp = {player.id: max_hp, target.id: max_hp}

        # 🆕 追蹤是否已使用復活裝置
        used_revive = {player.id: False, target.id: False}

        # 建立初始訊息
        embed = discord.Embed(
            title="⚔️ 世紀對決開始！",
            description=f"**{p1_name}** ⚡ **{p2_name}**\n雙方準備就緒，比賽開始！",
            color=discord.Color.red()
        )
        embed.add_field(name=f"🥊 {p1_name}", value=DuelSystem.draw_hp_bar(max_hp, max_hp), inline=True)
        embed.add_field(name=f"🥊 {p2_name}", value=DuelSystem.draw_hp_bar(max_hp, max_hp), inline=True)

        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        # 戰鬥變數
        turn_count = 0

        # 決定先手
        attacker = player if random.choice([True, False]) else target
        defender = target if attacker == player else player

        # 當雙方都還有血時
        while True:
            turn_count += 1
            await asyncio.sleep(3.5)

            # ===== 機率與數值判定 =====
            rand = random.uniform(0, 100)
            damage = 0
            heal = 0
            action_text = ""
            current_color = discord.Color.light_grey()

            # 1. 神級外掛 (1%)
            if rand <= 1:
                damage = 9999
                template = random.choice(DuelSystem.GOD_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                current_color = discord.Color.purple()

            # 2. 爆擊 (15%)
            elif rand < 16:
                damage = random.randint(30, 50)
                template = random.choice(DuelSystem.CRIT_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                action_text += f"\n💥 **造成了 {damage} 點爆擊傷害！**"
                current_color = discord.Color.dark_red()

            # 3. 防禦/回復 (15%)
            elif rand < 31:
                heal = random.randint(15, 30)
                hp[attacker.id] = min(max_hp, hp[attacker.id] + heal)
                template = random.choice(DuelSystem.HEAL_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name, heal=heal)
                current_color = discord.Color.green()

            # 4. 普通攻擊 (50%)
            elif rand < 81:
                damage = random.randint(10, 25)
                template = random.choice(DuelSystem.NORMAL_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                action_text += f"\n💢 造成了 **{damage}** 點傷害。"
                current_color = discord.Color.orange()

            # 5. 失誤 (19%)
            else:
                template = random.choice(DuelSystem.MISS_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                current_color = discord.Color.blue()

            # ===== 結算血量 =====
            if damage > 0:
                hp[defender.id] -= damage

            log_str = f"第 {turn_count} 回合：\n{action_text}"

            # 更新 Embed
            embed = discord.Embed(description=log_str, color=current_color)

            # 更新雙方血條
            hp1_bar = DuelSystem.draw_hp_bar(hp[player.id], max_hp)
            hp2_bar = DuelSystem.draw_hp_bar(hp[target.id], max_hp)

            embed.add_field(name=f"🥊 {p1_name}", value=hp1_bar, inline=False)
            embed.add_field(name=f"🥊 {p2_name}", value=hp2_bar, inline=False)
            embed.set_footer(text="戰鬥進行中...請稍候")

            await message.edit(embed=embed)

            # 🆕 ===== 修復：復活裝置檢查邏輯 =====
            # 只有在血量 <= 0 且尚未使用過復活時才觸發
            if hp[player.id] <= 0 and not used_revive[player.id]:
                if ShopSystem.has_active_item(player.id, 'revive_device'):
                    ShopSystem.use_consumable(player.id, 'revive_device')
                    hp[player.id] = 50  # 復活 50 HP
                    used_revive[player.id] = True  # 標記已使用

                    revive_embed = discord.Embed(
                        title="⚡ 復活裝置啟動！",
                        description=f"**{player.display_name}** 使用了復活裝置，恢復 50 HP！",
                        color=discord.Color.blue()
                    )
                    await message.edit(embed=revive_embed)
                    await asyncio.sleep(2)

            if hp[target.id] <= 0 and not used_revive[target.id]:
                if ShopSystem.has_active_item(target.id, 'revive_device'):
                    ShopSystem.use_consumable(target.id, 'revive_device')
                    hp[target.id] = 50
                    used_revive[target.id] = True

                    revive_embed = discord.Embed(
                        title="⚡ 復活裝置啟動！",
                        description=f"**{target.display_name}** 使用了復活裝置，恢復 50 HP！",
                        color=discord.Color.blue()
                    )
                    await message.edit(embed=revive_embed)
                    await asyncio.sleep(2)

            # 檢查是否真的戰鬥結束（雙方都已復活過或真的死亡）
            if hp[player.id] <= 0 and used_revive[player.id]:
                break  # 玩家 1 真的死了
            if hp[target.id] <= 0 and used_revive[target.id]:
                break  # 玩家 2 真的死了
            if hp[player.id] <= 0 and not ShopSystem.has_active_item(player.id, 'revive_device'):
                break  # 玩家 1 沒有復活裝置
            if hp[target.id] <= 0 and not ShopSystem.has_active_item(target.id, 'revive_device'):
                break  # 玩家 2 沒有復活裝置

            # 交換攻守
            attacker, defender = defender, attacker

        # ===== 戰鬥結束 =====
        await asyncio.sleep(1.5)

        # 判定勝者
        winner = player if hp[player.id] > 0 else target
        loser = target if winner == player else player

        winner_change, loser_change = await RankingSystem.record_match(
            winner.id,
            loser.id,
            interaction.channel
        )

        # 更新決鬥結束訊息
        end_embed = discord.Embed(title="🏆 決鬥結束！", color=discord.Color.gold())
        end_embed.description = (
            f"👑 **勝者：{winner.mention}**\n"
            f"💀 **敗者：{loser.mention}**\n\n"
            f"這是一場 {turn_count} 回合的激戰！"
        )

        # 顯示最終血量
        end_embed.add_field(
            name="最終狀態",
            value=f"{winner.display_name}: {max(0, hp[winner.id])} HP\n{loser.display_name}: 0 HP",
            inline=False
        )

        # 顯示積分變化
        winner_rank_info = RankingSystem.get_rank_info(winner_change['new_rank'])
        loser_rank_info = RankingSystem.get_rank_info(loser_change['new_rank'])

        points_text = (
            f"**{winner.display_name}**\n"
            f"{winner_rank_info['emoji']} {winner_rank_info['name']} | "
            f"{'+' if winner_change['points_change'] > 0 else ''}{winner_change['points_change']} 積分\n\n"
            f"**{loser.display_name}**\n"
            f"{loser_rank_info['emoji']} {loser_rank_info['name']} | "
            f"{loser_change['points_change']} 積分"
        )

        end_embed.add_field(name="📊 積分變化", value=points_text, inline=False)

        # 隨機結束語
        win_quotes = ["贏家通吃！", "實力差距懸殊。", "險勝！", "運氣也是實力的一部分。"]
        end_embed.set_footer(text=random.choice(win_quotes))

        # 更新成就追蹤
        tracking = AchievementSystem.get_user_tracking(winner.id)
        tracking['duel_wins'] += 1

        await message.edit(embed=end_embed)

@bot.tree.command(name="單挑", description="與朋友進行一場隨機的回合制決鬥")
@app_commands.describe(對象="要挑戰的對象")
async def duel(interaction: discord.Interaction, 對象: discord.User):
    """單挑指令"""
    # 檢查是否挑戰自己
    if 對象.id == interaction.user.id:
        await interaction.response.send_message("❌ 你不能跟自己打架！(會變成精神分裂)", ephemeral=True)
        return

    # 檢查是否挑戰機器人
    if 對象.bot:
        await interaction.response.send_message("❌ 機器人開啟了無敵模式，你打不贏的。", ephemeral=True)
        return

    # 執行決鬥
    await DuelSystem.run_duel(interaction, interaction.user, 對象)


# ==================== 🏆 成就系統 ====================
class AchievementSystem:
    """
    成就系統
    - 自動追蹤玩家行為
    - 達成條件自動解鎖
    - 發放獎勵
    """

    # 成就定義
    ACHIEVEMENTS = {
        'starter': {
            'name': '💼 白手起家',
            'description': '累計賺取 10,000 元',
            'condition': 'total_earned',
            'target': 10000,
            'reward': 2000,
            'category': 'money'
        },
        'gacha_addict': {
            'name': '🎰 抽卡上癮',
            'description': '執行 100 抽',
            'condition': 'total_pulls',
            'target': 100,
            'reward': 10000,
            'category': 'gacha'
        },
        'social_expert': {
            'name': '💬 社交專家',
            'description': '轉帳花費 50,000 元',
            'condition': 'transfer_sent',
            'target': 50000,
            'reward': 10000,
            'category': 'social'
        },
        'billionaire': {
            'name': '💎 億萬富翁',
            'description': '持有 1,000,000 元',
            'condition': 'current_money',
            'target': 1000000,
            'reward': 50000,
            'category': 'money'
        },
        'gacha_maniac': {
            'name': '🎲 抽卡狂人',
            'description': '累計抽卡 1,000 次',
            'condition': 'total_pulls',
            'target': 1000,
            'reward': 30000,
            'category': 'gacha'
        },
        'gamble_god': {
            'name': '🎰 賭神',
            'description': '賭博連勝 10 次',
            'condition': 'gamble_streak',
            'target': 10,
            'reward': 100000,
            'category': 'gamble'
        },

        # ===== 新增成就 =====
        'lucky_draw': {
            'name': '🍀 歐皇降臨',
            'description': '單次十連抽出 3 個五星',
            'condition': 'ten_pull_3_gold',
            'target': 1,
            'reward': 50000,
            'category': 'gacha'
        },
        'poor_guy': {
            'name': '💸 破產專家',
            'description': '金錢歸零 5 次',
            'condition': 'bankruptcy_count',
            'target': 5,
            'reward': 20000,
            'category': 'money'
        },
        'stock_master': {
            'name': '📈 股市大亨',
            'description': '股票總獲利達 500,000 元',
            'condition': 'stock_profit',
            'target': 500000,
            'reward': 80000,
            'category': 'stock'
        },
        'robber_king': {
            'name': '🔫 搶劫之王',
            'description': '成功搶劫 50 次',
            'condition': 'robbery_success',
            'target': 50,
            'reward': 150000,
            'category': 'combat'
        },
        'duel_master': {
            'name': '⚔️ 決鬥冠軍',
            'description': '單挑勝利 30 場',
            'condition': 'duel_wins',
            'target': 30,
            'reward': 60000,
            'category': 'combat'
        },
        'daily_login_7': {
            'name': '📅 簽到達人',
            'description': '連續簽到 7 天',
            'condition': 'checkin_streak',
            'target': 7,
            'reward': 15000,
            'category': 'daily'
        },
        'daily_login_30': {
            'name': '🔥 簽到狂魔',
            'description': '連續簽到 30 天',
            'condition': 'checkin_streak',
            'target': 30,
            'reward': 100000,
            'category': 'daily'
        },
        'generous': {
            'name': '🎁 慈善家',
            'description': '累計轉帳給其他人 1,000,000 元',
            'condition': 'transfer_sent',
            'target': 1000000,
            'reward': 200000,
            'category': 'social'
        },
        'collector': {
            'name': '🗂️ 收藏家',
            'description': '背包中持有 100 個五星角色',
            'condition': 'gold_inventory',
            'target': 100,
            'reward': 120000,
            'category': 'gacha'
        },
        'fire_master': {
            'name': '🔥 火焰大師',
            'description': '使用 /fire 指令 50 次',
            'condition': 'fire_usage',
            'target': 50,
            'reward': 25000,
            'category': 'fun'
        },
    }

    # 玩家成就進度 {user_id: {achievement_id: unlocked(bool)}}
    user_achievements: Dict[int, Dict[str, bool]] = {}

    # 玩家追蹤數據 {user_id: {stat_name: value}}
    user_tracking: Dict[int, Dict[str, int]] = {}

    @classmethod
    def get_user_achievements(cls, user_id: int) -> Dict[str, bool]:
        """獲取玩家成就狀態"""
        if user_id not in cls.user_achievements:
            cls.user_achievements[user_id] = {ach_id: False for ach_id in cls.ACHIEVEMENTS.keys()}
        return cls.user_achievements[user_id]

    @classmethod
    def get_user_tracking(cls, user_id: int) -> Dict[str, int]:
        """獲取玩家追蹤數據"""
        if user_id not in cls.user_tracking:
            cls.user_tracking[user_id] = {
                'gamble_streak': 0,  # 賭博連勝
                'ten_pull_3_gold': 0,  # 十連三金
                'bankruptcy_count': 0,  # 破產次數
                'stock_profit': 0,  # 股票獲利
                'robbery_success': 0,  # 搶劫成功次數
                'duel_wins': 0,  # 決鬥勝利
                'fire_usage': 0,  # 火焰特效使用次數
            }
        return cls.user_tracking[user_id]

    @classmethod
    async def check_and_unlock(cls, user_id: int, text_channel=None) -> List[dict]:
        """
        檢查並解鎖成就
        返回：新解鎖的成就列表
        """
        achievements = cls.get_user_achievements(user_id)
        tracking = cls.get_user_tracking(user_id)
        stats = MoneySystem.get_stats(user_id)
        gacha_data = GachaSystem.get_user_pity(user_id)
        inventory = InventorySystem.get_inventory(user_id)
        checkin_data = DailyCheckIn.get_user_data(user_id)

        newly_unlocked = []

        for ach_id, ach_data in cls.ACHIEVEMENTS.items():
            # 已解鎖就跳過
            if achievements[ach_id]:
                continue

            condition = ach_data['condition']
            target = ach_data['target']
            current_value = 0

            # 根據條件取得當前進度
            if condition == 'total_earned':
                current_value = stats['total_earned']
            elif condition == 'total_pulls':
                current_value = gacha_data['total_pulls']
            elif condition == 'transfer_sent':
                current_value = stats['transfer_sent']
            elif condition == 'current_money':
                current_value = MoneySystem.get_money(user_id)
            elif condition == 'gamble_streak':
                current_value = tracking['gamble_streak']
            elif condition == 'checkin_streak':
                current_value = checkin_data['streak'] + 1
            elif condition == 'gold_inventory':
                current_value = inventory['gold_up'] + inventory['gold_off']
            elif condition in tracking:
                current_value = tracking[condition]

            # 達成條件
            if current_value >= target:
                achievements[ach_id] = True
                reward = ach_data['reward']
                MoneySystem.add_money(user_id, reward)

                newly_unlocked.append({
                    'name': ach_data['name'],
                    'description': ach_data['description'],
                    'reward': reward
                })

                # 發送通知
                if text_channel:
                    embed = discord.Embed(
                        title="🎉 成就解鎖！",
                        description=f"**{ach_data['name']}**\n{ach_data['description']}",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="💰 獎勵", value=f"{reward:,} 元", inline=False)

                    try:
                        user = await bot.fetch_user(user_id)
                        embed.set_thumbnail(url=user.display_avatar.url)
                        await text_channel.send(f"{user.mention}", embed=embed)
                    except:
                        await text_channel.send(embed=embed)

        return newly_unlocked

    @classmethod
    def get_progress(cls, user_id: int, achievement_id: str) -> Tuple[int, int]:
        """
        獲取成就進度
        返回：(當前進度, 目標)
        """
        if achievement_id not in cls.ACHIEVEMENTS:
            return 0, 0

        ach_data = cls.ACHIEVEMENTS[achievement_id]
        condition = ach_data['condition']
        target = ach_data['target']

        tracking = cls.get_user_tracking(user_id)
        stats = MoneySystem.get_stats(user_id)
        gacha_data = GachaSystem.get_user_pity(user_id)
        inventory = InventorySystem.get_inventory(user_id)
        checkin_data = DailyCheckIn.get_user_data(user_id)

        current_value = 0

        if condition == 'total_earned':
            current_value = stats['total_earned']
        elif condition == 'total_pulls':
            current_value = gacha_data['total_pulls']
        elif condition == 'transfer_sent':
            current_value = stats['transfer_sent']
        elif condition == 'current_money':
            current_value = MoneySystem.get_money(user_id)
        elif condition == 'gamble_streak':
            current_value = tracking['gamble_streak']
        elif condition == 'checkin_streak':
            current_value = checkin_data['streak'] + 1
        elif condition == 'gold_inventory':
            current_value = inventory['gold_up'] + inventory['gold_off']
        elif condition in tracking:
            current_value = tracking[condition]

        return min(current_value, target), target

    @classmethod
    def get_unlocked_count(cls, user_id: int) -> int:
        """獲取已解鎖成就數量"""
        achievements = cls.get_user_achievements(user_id)
        return sum(1 for unlocked in achievements.values() if unlocked)


# ==================== 🏪 商城系統 ====================
class ShopSystem:
    """
    商城系統
    - 購買道具
    - Buff 效果管理
    - 道具庫存
    """

    # 商品定義
    SHOP_ITEMS = {
        'gamble_boost': {
            'name': '🎰 賭神的遺產吊飾',
            'price': 130000,
            'description': '賭博勝率 +15% (持續 1 小時)',
            'duration': 3600,  # 秒
            'type': 'buff',
            'effect': 'gamble_boost',
            'stackable': False  # 不可疊加
        },
        'anti_robbery': {
            'name': '💻 駭客電腦',
            'price': 100000,
            'description': '24 小時內無法被搶劫',
            'duration': 86400,
            'type': 'protection',
            'effect': 'robbery_immune',
            'stackable': False
        },
        'revive_device': {
            'name': '⚡ 復活裝置',
            'price': 100000,
            'description': '單挑失敗時自動復活 (一次性消耗)',
            'duration': None,  # 永久有效直到使用
            'type': 'consumable',
            'effect': 'auto_revive',
            'stackable': True  # 可以買多個
        },
        'gacha_luck': {
            'name': '🍀 幸運四葉草',
            'price': 80000,
            'description': '抽卡五星機率 +3% (持續 30 分鐘)',
            'duration': 1800,
            'type': 'buff',
            'effect': 'gacha_luck',
            'stackable': False
        },
        'double_money': {
            'name': '💰 發財符',
            'price': 50000,
            'description': '所有賺錢收益翻倍 (持續 1 小時)',
            'duration': 3600,
            'type': 'buff',
            'effect': 'double_income',
            'stackable': False
        },
        'stock_insider': {
            'name': '📊 內線消息',
            'price': 120000,
            'description': '查看未來 10 分鐘股票走勢 (一次性)',
            'duration': None,
            'type': 'consumable',
            'effect': 'stock_preview',
            'stackable': True
        },
        'vip_pass': {
            'name': '👑 VIP 通行證',
            'price': 500000,
            'description': '轉帳免手續費 + 簽到獎勵 +50% (持續 7 天)',
            'duration': 604800,
            'type': 'vip',
            'effect': 'vip_status',
            'stackable': False
        },
        'insurance': {
            'name': '🛡️ 保險契約',
            'price': 150000,
            'description': '被搶劫時只損失 30% 金額 (持續 3 天)',
            'duration': 259200,
            'type': 'protection',
            'effect': 'damage_reduction',
            'stackable': False
        },
        'exp_boost': {
            'name': '📈 經驗加速器(暫時沒用)',
            'price': 60000,
            'description': '所有活動經驗值 +100% (持續 2 小時)',
            'duration': 7200,
            'type': 'buff',
            'effect': 'exp_boost',
            'stackable': False
        },
        'teleport': {
            'name': '🌀 緊急傳送',
            'price': 30000,
            'description': '立即清除所有冷卻時間 (一次性)',
            'duration': None,
            'type': 'consumable',
            'effect': 'reset_cooldown',
            'stackable': True
        },
    }

    # 玩家道具庫存 {user_id: {item_id: {'quantity': int, 'expires': datetime}}}
    user_inventory: Dict[int, Dict[str, dict]] = {}

    @classmethod
    def get_user_inventory(cls, user_id: int) -> Dict[str, dict]:
        """獲取玩家商城道具"""
        if user_id not in cls.user_inventory:
            cls.user_inventory[user_id] = {}
        return cls.user_inventory[user_id]

    @classmethod
    def buy_item(cls, user_id: int, item_id: str) -> Tuple[bool, str]:
        """
        購買道具
        返回：(是否成功, 訊息)
        """
        if item_id not in cls.SHOP_ITEMS:
            return False, "❌ 商品不存在！"

        item = cls.SHOP_ITEMS[item_id]
        price = item['price']

        # 檢查金錢
        if not MoneySystem.deduct_money(user_id, price):
            current_money = MoneySystem.get_money(user_id)
            return False, f"❌ 金錢不足！需要 {price:,} 元，你只有 {current_money:,} 元"

        # 檢查是否可疊加
        inventory = cls.get_user_inventory(user_id)

        if item_id in inventory and not item['stackable']:
            # 檢查是否過期
            if inventory[item_id]['expires'] and datetime.now() < inventory[item_id]['expires']:
                MoneySystem.add_money(user_id, price)  # 退款
                remaining = (inventory[item_id]['expires'] - datetime.now()).total_seconds()
                minutes = int(remaining // 60)
                return False, f"❌ 你已經擁有此道具！\n剩餘時效：{minutes} 分鐘"

        # 添加道具
        expires = None
        if item['duration']:
            expires = datetime.now() + timedelta(seconds=item['duration'])

        if item_id in inventory and item['stackable']:
            inventory[item_id]['quantity'] += 1
        else:
            inventory[item_id] = {
                'quantity': 1,
                'expires': expires,
                'purchased_at': datetime.now()
            }

        return True, f"✅ 成功購買 **{item['name']}**！"

    @classmethod
    def has_active_item(cls, user_id: int, item_id: str) -> bool:
        """檢查道具是否有效"""
        inventory = cls.get_user_inventory(user_id)

        if item_id not in inventory:
            return False

        item_data = inventory[item_id]

        # 檢查是否過期
        if item_data['expires'] and datetime.now() > item_data['expires']:
            del inventory[item_id]  # 清除過期道具
            return False

        return item_data['quantity'] > 0

    @classmethod
    def use_consumable(cls, user_id: int, item_id: str) -> bool:
        """使用消耗品"""
        inventory = cls.get_user_inventory(user_id)

        if item_id not in inventory:
            return False

        item = cls.SHOP_ITEMS[item_id]
        if item['type'] != 'consumable':
            return False

        inventory[item_id]['quantity'] -= 1
        if inventory[item_id]['quantity'] <= 0:
            del inventory[item_id]

        return True

    @classmethod
    def get_active_buffs(cls, user_id: int) -> List[dict]:
        """獲取所有有效 Buff"""
        inventory = cls.get_user_inventory(user_id)
        active_buffs = []

        for item_id, item_data in list(inventory.items()):
            # 檢查過期
            if item_data['expires'] and datetime.now() > item_data['expires']:
                del inventory[item_id]
                continue

            item = cls.SHOP_ITEMS[item_id]

            if item_data['expires']:
                remaining = (item_data['expires'] - datetime.now()).total_seconds()
                active_buffs.append({
                    'name': item['name'],
                    'effect': item['effect'],
                    'remaining': remaining
                })
            else:
                active_buffs.append({
                    'name': item['name'],
                    'effect': item['effect'],
                    'quantity': item_data['quantity']
                })

        return active_buffs


# ==================== 🏆 成就指令 ====================

@bot.tree.command(name="我的成就", description="查看你的成就進度")
async def my_achievements(interaction: discord.Interaction):
    """查看成就"""
    user_id = interaction.user.id
    achievements = AchievementSystem.get_user_achievements(user_id)

    unlocked_count = AchievementSystem.get_unlocked_count(user_id)
    total_count = len(AchievementSystem.ACHIEVEMENTS)

    # 按分類整理
    categories = {}
    for ach_id, ach_data in AchievementSystem.ACHIEVEMENTS.items():
        cat = ach_data['category']
        if cat not in categories:
            categories[cat] = []

        is_unlocked = achievements[ach_id]
        current, target = AchievementSystem.get_progress(user_id, ach_id)

        categories[cat].append({
            'id': ach_id,
            'data': ach_data,
            'unlocked': is_unlocked,
            'progress': (current, target)
        })

    # 分類名稱
    cat_names = {
        'money': '💰 金錢',
        'gacha': '🎲 抽卡',
        'gamble': '🎰 賭博',
        'social': '💬 社交',
        'stock': '📈 股票',
        'combat': '⚔️ 戰鬥',
        'daily': '📅 簽到',
        'fun': '🎉 娛樂'
    }

    embed = discord.Embed(
        title=f"🏆 {interaction.user.display_name} 的成就",
        description=f"已解鎖：**{unlocked_count}/{total_count}** ({unlocked_count / total_count * 100:.1f}%)",
        color=discord.Color.gold()
    )

    for cat, achs in categories.items():
        lines = []
        for ach in achs:
            if ach['unlocked']:
                lines.append(f"✅ {ach['data']['name']}")
            else:
                current, target = ach['progress']
                percentage = min(100, int(current / target * 100))
                lines.append(f"⬜ {ach['data']['name']} ({current}/{target} - {percentage}%)")

        if lines:
            embed.add_field(
                name=cat_names.get(cat, cat),
                value='\n'.join(lines[:5]),  # 最多顯示 5 個
                inline=False
            )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="成就詳情", description="查看特定成就的詳細資訊")
@app_commands.describe(成就名稱="成就的完整名稱")
async def achievement_detail(interaction: discord.Interaction, 成就名稱: str):
    """成就詳情"""
    user_id = interaction.user.id

    # 搜尋成就
    target_ach = None
    target_id = None

    for ach_id, ach_data in AchievementSystem.ACHIEVEMENTS.items():
        if 成就名稱.lower() in ach_data['name'].lower():
            target_ach = ach_data
            target_id = ach_id
            break

    if not target_ach:
        await interaction.response.send_message(f"❌ 找不到成就「{成就名稱}」", ephemeral=True)
        return

    achievements = AchievementSystem.get_user_achievements(user_id)
    is_unlocked = achievements[target_id]
    current, target = AchievementSystem.get_progress(user_id, target_id)

    embed = discord.Embed(
        title=target_ach['name'],
        description=target_ach['description'],
        color=discord.Color.gold() if is_unlocked else discord.Color.grey()
    )

    if is_unlocked:
        embed.add_field(name="狀態", value="✅ 已解鎖", inline=True)
    else:
        percentage = min(100, int(current / target * 100))
        embed.add_field(name="進度", value=f"{current}/{target} ({percentage}%)", inline=True)

    embed.add_field(name="💰 獎勵", value=f"{target_ach['reward']:,} 元", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="成就排行榜", description="查看成就解鎖排行榜")
async def achievement_leaderboard(interaction: discord.Interaction):
    """成就排行榜"""
    rankings = []

    for user_id in AchievementSystem.user_achievements.keys():
        count = AchievementSystem.get_unlocked_count(user_id)
        if count > 0:
            rankings.append((user_id, count))

    rankings.sort(key=lambda x: x[1], reverse=True)
    rankings = rankings[:10]

    if not rankings:
        await interaction.response.send_message("📊 目前還沒有成就記錄！", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏆 成就大師排行榜 Top 10",
        description="解鎖成就數量排名",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, count) in enumerate(rankings, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        total = len(AchievementSystem.ACHIEVEMENTS)
        percentage = count / total * 100

        embed.add_field(
            name=f"{medal} {name}",
            value=f"**{count}/{total}** 個成就 ({percentage:.1f}%)",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# ==================== 🏪 商城指令 ====================

@bot.tree.command(name="商店", description="查看商城中的所有商品")
async def shop(interaction: discord.Interaction):
    """商店"""
    embed = discord.Embed(
        title="🏪 神秘商店",
        description="歡迎光臨！這裡販售各種強力道具",
        color=discord.Color.blue()
    )

    # 按類型分組
    buffs = []
    protections = []
    consumables = []
    vips = []

    for item_id, item in ShopSystem.SHOP_ITEMS.items():
        price_str = f"{item['price']:,} 元"

        if item['type'] == 'buff':
            buffs.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")
        elif item['type'] == 'protection':
            protections.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")
        elif item['type'] == 'consumable':
            consumables.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")
        elif item['type'] == 'vip':
            vips.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")

    if buffs:
        embed.add_field(name="⚡ Buff 道具", value='\n\n'.join(buffs), inline=False)
    if protections:
        embed.add_field(name="🛡️ 保護道具", value='\n\n'.join(protections), inline=False)
    if consumables:
        embed.add_field(name="💊 消耗品", value='\n\n'.join(consumables), inline=False)
    if vips:
        embed.add_field(name="👑 VIP 特權", value='\n\n'.join(vips), inline=False)

    embed.set_footer(text="使用 /購買 <商品名稱> 來購買道具")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="購買", description="購買商城道具")
@app_commands.describe(商品名稱="要購買的商品名稱")
async def buy_shop_item(interaction: discord.Interaction, 商品名稱: str):
    """購買道具"""
    user_id = interaction.user.id

    # 搜尋商品
    target_item = None
    target_id = None

    for item_id, item in ShopSystem.SHOP_ITEMS.items():
        if 商品名稱.lower() in item['name'].lower():
            target_item = item
            target_id = item_id
            break

    if not target_item:
        await interaction.response.send_message(f"❌ 找不到商品「{商品名稱}」", ephemeral=True)
        return

    # 購買
    success, message = ShopSystem.buy_item(user_id, target_id)

    if success:
        current_money = MoneySystem.get_money(user_id)

        embed = discord.Embed(
            title="✅ 購買成功！",
            description=f"**{target_item['name']}**\n{target_item['description']}",
            color=discord.Color.green()
        )
        embed.add_field(name="💰 花費", value=f"{target_item['price']:,} 元", inline=True)
        embed.add_field(name="💵 剩餘", value=f"{current_money:,} 元", inline=True)

        if target_item['duration']:
            minutes = target_item['duration'] // 60
            embed.add_field(name="⏱️ 持續時間", value=f"{minutes} 分鐘", inline=True)

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="我的道具", description="查看你擁有的商城道具")
async def my_items(interaction: discord.Interaction):
    """我的道具"""
    user_id = interaction.user.id
    active_buffs = ShopSystem.get_active_buffs(user_id)

    if not active_buffs:
        await interaction.response.send_message("🎒 你目前沒有任何道具", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🎒 {interaction.user.display_name} 的道具",
        color=discord.Color.blue()
    )

    for buff in active_buffs:
        if 'remaining' in buff:
            remaining = buff['remaining']
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            time_str = f"{hours}小時{minutes}分鐘" if hours > 0 else f"{minutes}分鐘"

            embed.add_field(
                name=buff['name'],
                value=f"⏱️ 剩餘：{time_str}",
                inline=False
            )
        else:
            embed.add_field(
                name=buff['name'],
                value=f"📦 數量：{buff['quantity']}",
                inline=False
            )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="使用道具", description="使用消耗品道具")
@app_commands.describe(道具名稱="要使用的道具名稱")
async def use_item(interaction: discord.Interaction, 道具名稱: str):
    """使用道具"""
    user_id = interaction.user.id

    # 搜尋道具
    target_item = None
    target_id = None

    for item_id, item in ShopSystem.SHOP_ITEMS.items():
        if 道具名稱.lower() in item['name'].lower():
            target_item = item
            target_id = item_id
            break

    if not target_item:
        await interaction.response.send_message(f"❌ 找不到道具「{道具名稱}」", ephemeral=True)
        return

    # 特殊道具效果
    if target_id == 'reset_cooldown':
        # 清除冷卻
        if ShopSystem.use_consumable(user_id, target_id):
            MoneySystem.earn_cooldowns.pop(user_id, None)
            RobberySystem.cooldowns.pop(user_id, None)

            await interaction.response.send_message("✅ 所有冷卻時間已清除！")
        else:
            await interaction.response.send_message("❌ 你沒有這個道具！", ephemeral=True)

    elif target_id == 'stock_preview':
        # 股票預測
        if ShopSystem.use_consumable(user_id, target_id):
            embed = discord.Embed(title="📊 內線消息", color=discord.Color.green())

            for symbol in StockSystem.STOCKS.keys():
                current = StockSystem.current_prices[symbol]
                # 模擬未來價格
                future = current * random.uniform(0.95, 1.05)
                change = ((future - current) / current) * 100

                trend = "📈 看漲" if change > 0 else "📉 看跌"
                embed.add_field(
                    name=f"{symbol} - {StockSystem.STOCKS[symbol]['name']}",
                    value=f"{trend} 預估變動：{change:+.2f}%",
                    inline=False
                )

            embed.set_footer(text="⚠️ 此為預測，不保證準確")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ 你沒有這個道具！", ephemeral=True)

    else:
        await interaction.response.send_message("❌ 此道具為被動效果，無需手動使用", ephemeral=True)


class RankingSystem:
    """牌位系統"""

    # 用戶段位數據 {user_id: {'wins': int, 'losses': int, 'rank': str, 'points': int}}
    user_rankings: Dict[int, dict] = {}

    # 段位定義（從低到高）
    RANKS = [
        {
            'id': 'bronze',
            'name': '🥉 青銅',
            'emoji': '🥉',
            'min_points': 0,
            'max_points': 999,
            'color': 0xCD7F32,
            'promotion_reward': 5000
        },
        {
            'id': 'silver',
            'name': '🥈 白銀',
            'emoji': '🥈',
            'min_points': 1000,
            'max_points': 1999,
            'color': 0xC0C0C0,
            'promotion_reward': 10000
        },
        {
            'id': 'gold',
            'name': '🥇 黃金',
            'emoji': '🥇',
            'min_points': 2000,
            'max_points': 2999,
            'color': 0xFFD700,
            'promotion_reward': 20000
        },
        {
            'id': 'platinum',
            'name': '💎 鉑金',
            'emoji': '💎',
            'min_points': 3000,
            'max_points': 3999,
            'color': 0xE5E4E2,
            'promotion_reward': 35000
        },
        {
            'id': 'diamond',
            'name': '💠 鑽石',
            'emoji': '💠',
            'min_points': 4000,
            'max_points': 4999,
            'color': 0xB9F2FF,
            'promotion_reward': 50000
        },
        {
            'id': 'master',
            'name': '👑 大師',
            'emoji': '👑',
            'min_points': 5000,
            'max_points': 5999,
            'color': 0xFF1493,
            'promotion_reward': 80000
        },
        {
            'id': 'grandmaster',
            'name': '🌟 宗師',
            'emoji': '🌟',
            'min_points': 6000,
            'max_points': 7499,
            'color': 0xFF6347,
            'promotion_reward': 120000
        },
        {
            'id': 'challenger',
            'name': '⚡ 王者',
            'emoji': '⚡',
            'min_points': 7500,
            'max_points': 999999,
            'color': 0xFF0000,
            'promotion_reward': 200000
        }
    ]

    @classmethod
    def get_user_data(cls, user_id: int) -> dict:
        """獲取用戶牌位數據"""
        if user_id not in cls.user_rankings:
            cls.user_rankings[user_id] = {
                'wins': 0,
                'losses': 0,
                'points': 0,  # 積分
                'rank': 'bronze',
                'current_streak': 0,  # 連勝
                'best_streak': 0,  # 最高連勝
                'total_matches': 0,
                'last_match': None,
                'promotion_count': 0  # 晉升次數
            }
        return cls.user_rankings[user_id]

    @classmethod
    def get_rank_info(cls, rank_id: str) -> dict:
        """根據段位 ID 獲取段位資訊"""
        for rank in cls.RANKS:
            if rank['id'] == rank_id:
                return rank
        return cls.RANKS[0]  # 預設青銅

    @classmethod
    def get_rank_by_points(cls, points: int) -> dict:
        """根據積分獲取對應段位"""
        for rank in reversed(cls.RANKS):
            if points >= rank['min_points']:
                return rank
        return cls.RANKS[0]

    @classmethod
    def calculate_points_change(cls, winner_points: int, loser_points: int, is_winner: bool) -> int:
        """計算積分變化（動態 K 值）"""

        # ===== 🆕 根據段位動態調整 K 值 =====
        def get_dynamic_k(points: int) -> int:
            if points < 1000:  # 青銅
                return 80  # 新手快速上分
            elif points < 2000:  # 白銀
                return 64
            elif points < 3000:  # 黃金
                return 48
            elif points < 4000:  # 鉑金
                return 40
            elif points < 5000:  # 鑽石
                return 32
            else:  # 大師以上
                return 24  # 高段位變化慢，更穩定

        # 使用贏家的 K 值
        K = get_dynamic_k(winner_points if is_winner else loser_points)

        expected_winner = 1 / (1 + 10 ** ((loser_points - winner_points) / 400))
        expected_loser = 1 - expected_winner

        if is_winner:
            points_change = int(K * (1 - expected_winner))

            # ===== 🆕 連勝加成 =====
            winner_data = cls.get_user_data(winner_points)  # 需要傳入 user_id
            if winner_data['current_streak'] >= 3:
                bonus = min(20, winner_data['current_streak'] * 2)  # 連勝 3+ 額外加分
                points_change += bonus

            return max(25, min(100, points_change))
        else:
            points_change = int(K * (0 - expected_loser))

            # ===== 🆕 段位保護（避免快速掉段）=====
            loser_data = cls.get_user_data(loser_points)
            loser_rank_info = cls.get_rank_by_points(loser_data['points'])

            # 如果即將掉段，減少扣分
            if loser_data['points'] - abs(points_change) < loser_rank_info['min_points']:
                points_change = int(points_change * 0.7)  # 減少 30% 扣分

            return max(-80, min(-15, points_change))

    @classmethod
    async def record_match(cls, winner_id: int, loser_id: int, channel) -> Tuple[dict, dict]:
        """
        記錄對戰結果並更新牌位
        返回：(贏家變化, 輸家變化)
        """
        winner_data = cls.get_user_data(winner_id)
        loser_data = cls.get_user_data(loser_id)

        # 記錄原始段位
        old_winner_rank = winner_data['rank']
        old_loser_rank = loser_data['rank']
        old_winner_points = winner_data['points']
        old_loser_points = loser_data['points']

        # 計算積分變化
        winner_points_change = cls.calculate_points_change(
            winner_data['points'],
            loser_data['points'],
            True
        )
        loser_points_change = cls.calculate_points_change(
            winner_data['points'],
            loser_data['points'],
            False
        )

        # 更新積分
        winner_data['points'] = max(0, winner_data['points'] + winner_points_change)
        loser_data['points'] = max(0, loser_data['points'] + loser_points_change)

        # 更新勝負場次
        winner_data['wins'] += 1
        loser_data['losses'] += 1
        winner_data['total_matches'] += 1
        loser_data['total_matches'] += 1

        # 更新連勝
        winner_data['current_streak'] += 1
        winner_data['best_streak'] = max(winner_data['best_streak'], winner_data['current_streak'])
        loser_data['current_streak'] = 0

        # 記錄時間
        winner_data['last_match'] = datetime.now()
        loser_data['last_match'] = datetime.now()

        # 更新段位
        new_winner_rank_info = cls.get_rank_by_points(winner_data['points'])
        new_loser_rank_info = cls.get_rank_by_points(loser_data['points'])

        winner_data['rank'] = new_winner_rank_info['id']
        loser_data['rank'] = new_loser_rank_info['id']

        # 檢查晉升/掉落
        winner_change = {
            'points_change': winner_points_change,
            'old_rank': old_winner_rank,
            'new_rank': winner_data['rank'],
            'promoted': False,
            'demoted': False,
            'reward': 0
        }

        loser_change = {
            'points_change': loser_points_change,
            'old_rank': old_loser_rank,
            'new_rank': loser_data['rank'],
            'promoted': False,
            'demoted': False,
            'reward': 0
        }

        # 贏家晉升檢查
        if old_winner_rank != winner_data['rank']:
            old_rank_info = cls.get_rank_info(old_winner_rank)
            new_rank_info = cls.get_rank_info(winner_data['rank'])

            if new_rank_info['min_points'] > old_rank_info['min_points']:
                winner_change['promoted'] = True
                winner_change['reward'] = new_rank_info['promotion_reward']
                winner_data['promotion_count'] += 1

                MoneySystem.add_money(winner_id, winner_change['reward'])

                # 發送晉升通知
                await cls.send_promotion_notification(channel, winner_id, new_rank_info, winner_change['reward'])

        # 輸家掉段檢查
        if old_loser_rank != loser_data['rank']:
            old_rank_info = cls.get_rank_info(old_loser_rank)
            new_rank_info = cls.get_rank_info(loser_data['rank'])

            if new_rank_info['min_points'] < old_rank_info['min_points']:
                loser_change['demoted'] = True

                # 發送掉段通知
                await cls.send_demotion_notification(channel, loser_id, old_rank_info, new_rank_info)

        return winner_change, loser_change

    @classmethod
    async def send_promotion_notification(cls, channel, user_id: int, rank_info: dict, reward: int):
        """發送晉升通知"""
        try:
            user = await channel.guild.get_member(user_id) or await channel.guild.fetch_member(user_id)

            embed = discord.Embed(
                title="🎊 段位晉升！",
                description=f"**{user.mention}** 成功晉升至 **{rank_info['name']}**！",
                color=rank_info['color']
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="💰 晉升獎勵", value=f"{reward:,} 元", inline=True)
            embed.add_field(name="🏆 新段位", value=rank_info['emoji'], inline=True)
            embed.set_footer(text="繼續加油，向更高段位邁進！")

            await channel.send(embed=embed)
        except Exception as e:
            print(f"發送晉升通知失敗: {e}")

    @classmethod
    async def send_demotion_notification(cls, channel, user_id: int, old_rank: dict, new_rank: dict):
        """發送掉段通知"""
        try:
            user = await channel.guild.get_member(user_id) or await channel.guild.fetch_member(user_id)

            embed = discord.Embed(
                title="📉 段位降級",
                description=f"**{user.mention}** 從 **{old_rank['name']}** 降至 **{new_rank['name']}**",
                color=0x808080
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="不要氣餒，繼續努力！")

            await channel.send(embed=embed)
        except Exception as e:
            print(f"發送掉段通知失敗: {e}")

    @classmethod
    def get_rank_progress(cls, user_id: int) -> Tuple[int, int, int]:
        """
        獲取段位進度
        返回：(當前積分, 當前段位最低分, 下一段位最低分)
        """
        data = cls.get_user_data(user_id)
        current_rank = cls.get_rank_info(data['rank'])

        # 找下一個段位
        current_index = next((i for i, r in enumerate(cls.RANKS) if r['id'] == data['rank']), 0)

        if current_index < len(cls.RANKS) - 1:
            next_rank = cls.RANKS[current_index + 1]
            return data['points'], current_rank['min_points'], next_rank['min_points']
        else:
            # 已經是最高段位
            return data['points'], current_rank['min_points'], current_rank['max_points']

    @classmethod
    def get_winrate(cls, user_id: int) -> float:
        """計算勝率"""
        data = cls.get_user_data(user_id)
        total = data['total_matches']
        if total == 0:
            return 0.0
        return (data['wins'] / total) * 100

    @classmethod
    def get_leaderboard(cls, limit: int = 10) -> list:
        """獲取排行榜"""
        rankings = [
            (user_id, data['points'], data['rank'], data['wins'], data['losses'])
            for user_id, data in cls.user_rankings.items()
        ]
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings[:limit]


@bot.tree.command(name="我的牌位", description="查看你的牌位資訊")
async def my_rank(interaction: discord.Interaction):
    """查看自己的牌位"""
    user_id = interaction.user.id
    data = RankingSystem.get_user_data(user_id)
    rank_info = RankingSystem.get_rank_info(data['rank'])

    # 計算勝率
    winrate = RankingSystem.get_winrate(user_id)

    # 計算進度
    current_points, min_points, next_points = RankingSystem.get_rank_progress(user_id)
    progress = current_points - min_points
    needed = next_points - min_points
    percentage = (progress / needed * 100) if needed > 0 else 100

    # 進度條
    bar_length = 10
    filled = int(bar_length * (progress / needed)) if needed > 0 else bar_length
    bar = "█" * filled + "░" * (bar_length - filled)

    embed = discord.Embed(
        title=f"🎖️ {interaction.user.display_name} 的牌位",
        color=rank_info['color']
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    # 段位資訊
    embed.add_field(
        name="📊 當前段位",
        value=f"{rank_info['emoji']} **{rank_info['name']}**\n積分：**{data['points']}** 分",
        inline=False
    )

    # 進度條
    if data['rank'] != 'challenger':  # 非最高段位
        embed.add_field(
            name="📈 晉升進度",
            value=f"`[{bar}]` {percentage:.1f}%\n需要 **{next_points - current_points}** 分晉升",
            inline=False
        )
    else:
        embed.add_field(
            name="👑 已達最高段位",
            value="你已經是王者了！",
            inline=False
        )

    # 戰績
    embed.add_field(
        name="⚔️ 戰績",
        value=(
            f"總場次：**{data['total_matches']}** 場\n"
            f"勝場：**{data['wins']}** 場\n"
            f"敗場：**{data['losses']}** 場\n"
            f"勝率：**{winrate:.1f}%**"
        ),
        inline=True
    )

    # 連勝
    embed.add_field(
        name="🔥 連勝記錄",
        value=(
            f"目前連勝：**{data['current_streak']}** 場\n"
            f"最高連勝：**{data['best_streak']}** 場"
        ),
        inline=True
    )

    # 統計
    embed.add_field(
        name="📜 其他",
        value=f"晉升次數：**{data['promotion_count']}** 次",
        inline=True
    )

    embed.set_footer(text="使用 /單挑 來提升你的段位！")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="查看牌位", description="查看其他玩家的牌位")
@app_commands.describe(玩家="要查看的玩家")
async def check_rank(interaction: discord.Interaction, 玩家: discord.User):
    """查看別人的牌位"""
    user_id = 玩家.id
    data = RankingSystem.get_user_data(user_id)
    rank_info = RankingSystem.get_rank_info(data['rank'])

    winrate = RankingSystem.get_winrate(user_id)

    embed = discord.Embed(
        title=f"🎖️ {玩家.display_name} 的牌位",
        color=rank_info['color']
    )
    embed.set_thumbnail(url=玩家.display_avatar.url)

    embed.add_field(
        name="📊 段位",
        value=f"{rank_info['emoji']} **{rank_info['name']}**\n積分：**{data['points']}** 分",
        inline=False
    )

    embed.add_field(
        name="⚔️ 戰績",
        value=(
            f"{data['wins']}勝 {data['losses']}敗\n"
            f"勝率：**{winrate:.1f}%**"
        ),
        inline=True
    )

    embed.add_field(
        name="🔥 連勝",
        value=f"目前：{data['current_streak']} 場\n最高：{data['best_streak']} 場",
        inline=True
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="段位排行榜", description="查看段位排行榜 Top 10")
async def rank_leaderboard(interaction: discord.Interaction):
    """段位排行榜"""
    leaderboard = RankingSystem.get_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 目前還沒有排行榜資料！", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏆 段位排行榜 Top 10",
        description="（按積分排序）",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, points, rank_id, wins, losses) in enumerate(leaderboard, 1):
        try:
            user = await interaction.client.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        rank_info = RankingSystem.get_rank_info(rank_id)
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."

        total_matches = wins + losses
        winrate = (wins / total_matches * 100) if total_matches > 0 else 0

        embed.add_field(
            name=f"{medal} {name}",
            value=(
                f"{rank_info['emoji']} **{rank_info['name']}** | {points} 分\n"
                f"戰績：{wins}勝 {losses}敗 ({winrate:.1f}%)"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="段位說明", description="查看所有段位的詳細說明")
async def rank_info(interaction: discord.Interaction):
    """段位說明"""
    embed = discord.Embed(
        title="🎖️ 段位系統說明",
        description="透過單挑累積積分，提升你的段位！",
        color=discord.Color.blue()
    )

    for rank in RankingSystem.RANKS:
        points_range = f"{rank['min_points']} ~ {rank['max_points']}" if rank[
                                                                             'max_points'] < 999999 else f"{rank['min_points']}+"

        embed.add_field(
            name=f"{rank['emoji']} {rank['name']}",
            value=(
                f"積分範圍：**{points_range}**\n"
                f"晉升獎勵：**{rank['promotion_reward']:,}** 元"
            ),
            inline=True
        )

    embed.add_field(
        name="\n📌 積分規則",
        value=(
            "• 勝利獲得 15~50 積分\n"
            "• 失敗失去 10~50 積分\n"
            "• 積分變化根據對手實力調整\n"
            "• 擊敗強者獲得更多積分"
        ),
        inline=False
    )

    embed.set_footer(text="使用 /單挑 開始你的排位之旅！")

    await interaction.response.send_message(embed=embed)


# ==================== 占卜系統 ====================
class FortuneSystem:
    """占卜系統"""

    # 用戶占卜數據
    user_fortunes: Dict[int, dict] = {}

    # 🔧 ===== 冷卻時間設定（改這裡）===== 🔧
    FORTUNE_COOLDOWN = 1  # 預設 12 小時（43200 秒）

    # 快速參考：
    # 0 秒 = 無冷卻
    # 60 秒 = 1 分鐘
    # 300 秒 = 5 分鐘
    # 600 秒 = 10 分鐘
    # 1800 秒 = 30 分鐘
    # 3600 秒 = 1 小時
    # 7200 秒 = 2 小時
    # 21600 秒 = 6 小時
    # 43200 秒 = 12 小時
    # 86400 秒 = 24 小時

    # 運勢等級定義（保持原樣）
    FORTUNE_LEVELS = [
        {
            'id': 'catastrophe',
            'name': '💀 大凶',
            'probability': 2,
            'color': 0x000000,
            'emoji': '💀',
            'title': '末日預兆',
            'messages': [
                "今天建議你別出門，真的。",
                "連呼吸都可能嗆到，建議待在被窩裡。",
                "出門會踩到香蕉皮，待在家會被天花板砸到。",
                "你的厄運值已經突破天際，建議重開遊戲人生。",
                "今天的你就像是行走的災難現場。",
                "建議你今天裝死，什麼都不要做。",
                "你今天出門可能會遇到詐騙、搶劫、還有前任。",
                "運勢差到連幸運餅乾裡都是壞消息。",
                "今天最好的選擇就是睡覺睡到明天。"
            ],
            'advice': [
                "🚫 不要賭博，你會把內褲都輸掉",
                "🚫 不要抽卡，你只會抽到武器",
                "🚫 不要單挑，你會被打到懷疑人生",
                "🚫 不要炒股，股市會讓你破產",
                "✅ 建議：關機睡覺"
            ]
        },
        {
            'id': 'very_bad',
            'name': '😱 凶',
            'probability': 8,
            'color': 0x8B0000,
            'emoji': '😱',
            'title': '水逆預警',
            'messages': [
                "今天出門小心踩到狗屎。",
                "你的倒楣指數已經達到警戒值。",
                "建議今天只做一件事：躺平。",
                "你今天的運氣大概和你的存款一樣少。",
                "今天不適合做任何需要運氣的事情。",
                "建議你今天假裝生病請假。",
                "你今天可能會遇到所有你不想遇到的人。",
                "運勢差到連機器人都同情你。"
            ],
            'advice': [
                "🚫 遠離賭場，你會輸到脫褲",
                "🚫 不要抽卡，保底都不會來救你",
                "🚫 避免PK，你會輸得很難看",
                "⚠️ 可以簽到，但別期待太多",
                "💡 建議：追劇、睡覺、發呆"
            ]
        },
        {
            'id': 'bad',
            'name': '😰 小凶',
            'probability': 15,
            'color': 0xCD5C5C,
            'emoji': '😰',
            'title': '陰雨綿綿',
            'messages': [
                "今天運氣不太好，但也不至於太慘。",
                "你今天可能會遇到一些小麻煩。",
                "建議降低期望值，以免失望。",
                "今天的你就像沒睡醒的樹懶。",
                "運勢略差，但還不至於世界末日。",
                "今天適合做一些不需要運氣的事情。",
                "你的幸運值今天請假了。",
                "建議保守行事，別想著一夜暴富。"
            ],
            'advice': [
                "⚠️ 賭博要小心，小賭就好",
                "⚠️ 抽卡可能歪，做好心理準備",
                "⚠️ 單挑謹慎，別太浪",
                "💰 可以賺點小錢維持生活",
                "💡 建議：做點輕鬆的事就好"
            ]
        },
        {
            'id': 'normal',
            'name': '😐 平',
            'probability': 35,
            'color': 0x808080,
            'emoji': '😐',
            'title': '平淡如水',
            'messages': [
                "今天就是普通的一天，沒什麼特別的。",
                "你的運勢就像白開水一樣平淡無奇。",
                "今天是普通上班族的日常。",
                "運勢平穩，不好不壞，就是普通。",
                "你今天大概就是個路人甲。",
                "今天的你就像沒有調味的白飯。",
                "運勢普普通通，就是個平凡的一天。",
                "今天適合做些日常的例行公事。"
            ],
            'advice': [
                "💰 正常賺錢，正常花錢",
                "🎲 想抽就抽，隨緣",
                "⚔️ 想打就打，看實力",
                "📈 股票隨意，反正也不會暴富",
                "💡 建議：該幹嘛就幹嘛"
            ]
        },
        {
            'id': 'slightly_good',
            'name': '😊 小吉',
            'probability': 20,
            'color': 0x90EE90,
            'emoji': '😊',
            'title': '微風拂面',
            'messages': [
                "今天運氣還不錯喔！",
                "你今天可能會有一些小驚喜。",
                "運勢上揚，把握機會！",
                "今天的你自帶主角光環（低配版）。",
                "運氣不錯，可以試試手氣。",
                "今天出門可能會撿到錢（小錢）。",
                "你的幸運值今天有在正常上班。",
                "今天適合做一些需要運氣的事情。"
            ],
            'advice': [
                "💰 可以賺點小錢，試試手氣",
                "🎲 抽卡有機會出貨",
                "⚔️ 單挑勝算不錯",
                "📈 股市可以小試身手",
                "💡 建議：積極一點，把握機會"
            ]
        },
        {
            'id': 'good',
            'name': '😄 吉',
            'probability': 15,
            'color': 0x32CD32,
            'emoji': '😄',
            'title': '春風得意',
            'messages': [
                "今天運勢大好！去做你想做的事吧！",
                "你今天自帶幸運光環！",
                "今天是個適合冒險的好日子。",
                "幸運女神今天在你身邊徘徊。",
                "今天的你就像開了外掛一樣順利。",
                "運勢爆棚，可以大膽一點！",
                "今天出門可能會遇到貴人。",
                "你的幸運值今天超時加班中！"
            ],
            'advice': [
                "💰 賺錢機會多，把握住！",
                "🎲 抽卡出貨率高，可以多抽幾發",
                "⚔️ 單挑必勝，去制裁別人吧",
                "📈 股市看好，可以大膽投資",
                "💡 建議：今天就是要浪！"
            ]
        },
        {
            'id': 'great',
            'name': '🎉 大吉',
            'probability': 4,
            'color': 0xFFD700,
            'emoji': '🎉',
            'title': '鴻運當頭',
            'messages': [
                "恭喜！今天是你的幸運日！",
                "今天的你就像是歐皇轉世！",
                "幸運女神今天直接住在你家了！",
                "今天走在路上都可能撿到錢包！",
                "你今天的運勢已經爆表了！",
                "建議今天去買樂透，真的。",
                "今天的你無往不利，所向披靡！",
                "運勢好到讓其他人羨慕嫉妒恨！"
            ],
            'advice': [
                "💰 今天就是要賺大錢！",
                "🎲 抽卡必出金，多抽沒問題",
                "⚔️ 單挑無敵，去當霸主吧",
                "📈 股市暴漲，All in 沒問題",
                "🎰 賭博必贏，梭哈就對了",
                "💡 建議：想幹嘛就幹嘛！"
            ]
        },
        {
            'id': 'supreme',
            'name': '✨ 極吉',
            'probability': 1,
            'color': 0xFF1493,
            'emoji': '✨',
            'title': '天選之子',
            'messages': [
                "🎊 恭喜你抽到極吉！這是萬中無一的運勢！",
                "✨ 今天的你就是天選之子！",
                "🌟 幸運女神直接把你當親兒子養！",
                "💫 你今天的運氣已經超越人類極限！",
                "🔥 今天的你自帶主角光環 MAX 版！",
                "⚡ 建議你今天去買所有的樂透！",
                "🎯 今天你做什麼都會成功！",
                "👑 你今天就是整個伺服器的王者！",
                "🌈 今天可能會發生奇蹟！"
            ],
            'advice': [
                "💎 今天你就是傳說中的歐皇！",
                "🎲 抽卡十連必出雙金，不出算我輸",
                "⚔️ 單挑無敵，血量鎖定在 1 滴",
                "📈 股市隨便買隨便賺",
                "🎰 賭場就是你的提款機",
                "🔫 搶劫必成功，警察看到你都會讓路",
                "💡 建議：梭哈！All in！一把梭！"
            ]
        }
    ]

    # 特殊事件
    SPECIAL_EVENTS = [
        "🌠 流星劃過天際，你許了個願",
        "🐱 路上遇到一隻黑貓，牠對你喵了一聲",
        "🍀 你在路邊發現了一株四葉草",
        "🎪 馬戲團路過，小丑朝你揮手",
        "🦅 老鷹從你頭上飛過，留下了「禮物」",
        "👻 你看到了奇怪的影子，但轉頭就消失了",
        "🎭 街頭藝人說你面相不凡",
        "🔮 神秘的吉普賽人看了你一眼",
        "🌙 月亮今天特別圓",
        "☄️ 天空出現了奇怪的雲",
        "🦊 狐狸精在你夢中出現",
        "🐉 你夢到自己騎著龍",
        "💀 你踩到了不明物體",
        "🎰 路過賭場時聽到有人中大獎",
        "💰 你發現錢包裡多了一張發票",
        "📱 手機電量正好是 69%",
        "🚪 出門時左腳先踏出去",
        "☕ 咖啡灑在你最喜歡的衣服上",
        "🌈 下雨後看到了彩虹",
        "⚡ 打雷時你正好在想前任"
    ]

    @classmethod
    def get_today_fortune(cls, user_id: int) -> dict:
        """獲取今日運勢"""
        # 抽取運勢
        fortune = cls._roll_fortune()
        special_event = random.choice(cls.SPECIAL_EVENTS) if random.random() < 0.3 else None

        # 記錄占卜（簡化版，不記錄日期）
        cls.user_fortunes[user_id] = {
            'fortune_id': fortune['id'],
            'special_event': special_event
        }

        # 記錄歷史（簡化版）
        if user_id not in cls.fortune_history:
            cls.fortune_history[user_id] = []

        cls.fortune_history[user_id].append({
            'fortune': fortune['name'],
            'fortune_id': fortune['id']
        })

        # 只保留最近 30 次
        if len(cls.fortune_history[user_id]) > 30:
            cls.fortune_history[user_id] = cls.fortune_history[user_id][-30:]

        return cls._get_fortune_data(fortune['id'], special_event)

    @classmethod
    def _roll_fortune(cls) -> dict:
        """抽取運勢"""
        total = sum(f['probability'] for f in cls.FORTUNE_LEVELS)
        rand = random.uniform(0, total)

        current = 0
        for fortune in cls.FORTUNE_LEVELS:
            current += fortune['probability']
            if rand <= current:
                return fortune

        return cls.FORTUNE_LEVELS[3]

    @classmethod
    def _get_fortune_data(cls, fortune_id: str, special_event: Optional[str] = None) -> dict:
        """獲取運勢詳細數據"""
        fortune = next((f for f in cls.FORTUNE_LEVELS if f['id'] == fortune_id), cls.FORTUNE_LEVELS[3])

        return {
            'fortune': fortune,
            'message': random.choice(fortune['messages']),
            'advice': fortune['advice'],
            'special_event': special_event
        }

    @classmethod
    def get_fortune_stats(cls, user_id: int) -> dict:
        """獲取占卜統計"""
        if user_id not in cls.fortune_history:
            return None

        history = cls.fortune_history[user_id]

        stats = {}
        for record in history:
            fortune_name = record['fortune']
            stats[fortune_name] = stats.get(fortune_name, 0) + 1

        most_common = max(stats.items(), key=lambda x: x[1]) if stats else None

        good_days = sum(1 for r in history if r['fortune_id'] in ['slightly_good', 'good', 'great', 'supreme'])
        bad_days = sum(1 for r in history if r['fortune_id'] in ['catastrophe', 'very_bad', 'bad'])

        return {
            'total_days': len(history),
            'stats': stats,
            'most_common': most_common,
            'good_days': good_days,
            'bad_days': bad_days,
            'normal_days': len(history) - good_days - bad_days
        }


# ==================== 占卜指令 ====================

@bot.tree.command(name="占卜", description="🔮 每日運勢占卜（純娛樂）")
async def daily_fortune(interaction: discord.Interaction):
    """每日占卜"""
    user_id = interaction.user.id

    # 🆕 直接獲取運勢，無冷卻
    fortune_data = FortuneSystem.get_today_fortune(user_id)
    fortune = fortune_data['fortune']
    message = fortune_data['message']
    advice = fortune_data['advice']
    special_event = fortune_data['special_event']

    # 創建華麗的 Embed
    embed = discord.Embed(
        title=f"🔮 {interaction.user.display_name} 的占卜結果",
        description=f"**{fortune['emoji']} {fortune['title']} {fortune['emoji']}**",
        color=fortune['color']
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    embed.add_field(
        name="📊 運勢",
        value=f"# {fortune['name']}",
        inline=False
    )

    embed.add_field(
        name="💬 運勢解析",
        value=f"*{message}*",
        inline=False
    )

    if special_event:
        embed.add_field(
            name="✨ 特殊徵兆",
            value=special_event,
            inline=False
        )

    advice_text = "\n".join(advice)
    embed.add_field(
        name="📝 今日建議",
        value=advice_text,
        inline=False
    )

    if fortune['id'] == 'supreme':
        embed.add_field(
            name="🎊 恭喜！",
            value="你抽到了萬中無一的「極吉」！這是 1% 的機率！",
            inline=False
        )
    elif fortune['id'] == 'catastrophe':
        embed.add_field(
            name="⚠️ 警告",
            value="運勢極差，建議今天什麼都不要做...",
            inline=False
        )

    # 🆕 改成無冷卻提示
    embed.set_footer(text="💡 純娛樂性質，不影響遊戲數值 | 可隨時占卜")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="占卜統計", description="📊 查看你的占卜歷史統計")
async def fortune_stats(interaction: discord.Interaction):
    """占卜統計"""
    user_id = interaction.user.id

    stats = FortuneSystem.get_fortune_stats(user_id)

    if not stats:
        await interaction.response.send_message(
            "📊 你還沒有占卜記錄喔！\n使用 `/占卜` 開始你的每日占卜吧！",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"📊 {interaction.user.display_name} 的占卜統計",
        color=discord.Color.purple()
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    embed.add_field(
        name="📅 占卜天數",
        value=f"**{stats['total_days']}** 天",
        inline=True
    )

    good_rate = (stats['good_days'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
    embed.add_field(
        name="🍀 好運天數",
        value=f"**{stats['good_days']}** 天 ({good_rate:.1f}%)",
        inline=True
    )

    bad_rate = (stats['bad_days'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
    embed.add_field(
        name="💀 壞運天數",
        value=f"**{stats['bad_days']}** 天 ({bad_rate:.1f}%)",
        inline=True
    )

    if stats['stats']:
        stats_text = "\n".join([f"{name}: **{count}** 次" for name, count in
                                sorted(stats['stats'].items(), key=lambda x: x[1], reverse=True)])
        embed.add_field(
            name="📈 運勢分佈",
            value=stats_text,
            inline=False
        )

    if stats['most_common']:
        embed.add_field(
            name="🎯 最常運勢",
            value=f"{stats['most_common'][0]} (**{stats['most_common'][1]}** 次)",
            inline=False
        )

    if good_rate > 50:
        comment = "你的運氣還不錯喔！繼續保持！✨"
    elif bad_rate > 50:
        comment = "你最近運氣不太好...要不要去拜拜？🙏"
    else:
        comment = "你的運勢很平穩，就是個普通人。😐"

    embed.add_field(
        name="💬 綜合評價",
        value=comment,
        inline=False
    )

    embed.set_footer(text="持續占卜可以累積更多統計數據")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="占卜排行榜", description="🏆 查看幸運排行榜")
async def fortune_leaderboard(interaction: discord.Interaction):
    """占卜排行榜"""

    rankings = []

    for user_id in FortuneSystem.fortune_history.keys():
        stats = FortuneSystem.get_fortune_stats(user_id)
        if stats and stats['total_days'] >= 3:
            lucky_score = (stats['good_days'] - stats['bad_days']) / stats['total_days'] * 100
            rankings.append((user_id, lucky_score, stats['total_days'], stats['good_days']))

    if not rankings:
        await interaction.response.send_message(
            "🏆 目前還沒有足夠的占卜數據！\n至少需要 3 次的占卜記錄才能上榜。",
            ephemeral=True
        )
        return

    rankings.sort(key=lambda x: x[1], reverse=True)
    rankings = rankings[:10]

    embed = discord.Embed(
        title="🏆 幸運排行榜 Top 10",
        description="（根據好運天數佔比排名）",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, score, total, good) in enumerate(rankings, 1):
        try:
            user = await interaction.client.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"用戶 {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."

        if score > 30:
            status = "✨ 歐皇"
        elif score > 10:
            status = "🍀 幸運兒"
        elif score > -10:
            status = "😐 普通人"
        elif score > -30:
            status = "💀 非洲人"
        else:
            status = "😱 厄運纏身"

        embed.add_field(
            name=f"{medal} {name}",
            value=f"{status} | 幸運值：**{score:.1f}**\n占卜 {total} 天，好運 {good} 天",
            inline=False
        )

    embed.set_footer(text="💡 連續占卜可以提升排名準確度")

    await interaction.response.send_message(embed=embed)


# ==================== 📖 幫助指令 ====================

@bot.tree.command(name="幫助", description="查看所有可用指令")
async def help_command(interaction: discord.Interaction):
    """幫助指令"""

    embed = discord.Embed(
        title="📖 指令說明書",
        description="以下是所有可用的指令，點擊分類查看詳細說明",
        color=discord.Color.blue()
    )

    # 💰 金錢系統
    embed.add_field(
        name="💰 金錢系統",
        value=(
            "`/查看金錢` - 查看金錢（可指定對象）\n"
            "`/轉帳` - 轉帳給其他玩家（手續費 5%）\n"
            "`/個人統計` - 查看個人統計面板\n"
            "`/金錢排行榜` - 查看金錢排行榜"
        ),
        inline=False
    )

    # 🎮 小遊戲
    embed.add_field(
        name="🎮 小遊戲",
        value=(
            "`/賺錢` - 答數學題賺錢（冷卻 5 秒）\n"
            "`/猜數字` - 猜數字遊戲（賭 1000 元）\n"
            "`/剪刀石頭布` - 剪刀石頭布對賭（賭 2000 元）\n"
            "`/骰子比大小` - 骰子比大小（賭 2000 元）\n"
            "`/抽獎` - 測試你的運氣"
        ),
        inline=False
    )

    # 🎰 賭博系統
    embed.add_field(
        name="🎰 賭博系統",
        value=(
            "`/賭博` - 賭博賺大錢（門檻 500 元）\n"
            "`/賭博詳情` - 查看賠率和勝率\n"
            "`/賭神排行榜` - 查看賭博贏最多排行榜"
        ),
        inline=False
    )

    # 🎲 抽卡系統
    embed.add_field(
        name="🎲 抽卡系統",
        value=(
            "`/單抽` - 單次抽卡（120 元）\n"
            "`/十連抽` - 十連抽（1200 元）\n"
            "`/查詢保底` - 查看保底狀態\n"
            "`/歷史抽出` - 查看五星歷史\n"
            "`/機率說明` - 查看抽卡機率\n"
            "`/當前up角色` - 查看 UP 角色\n"
            "`/抽卡排行榜` - 抽卡次數排行榜\n"
            "`/重置保底` - 重置抽卡記錄"
        ),
        inline=False
    )

    # 🎒 物品系統
    embed.add_field(
        name="🎒 物品系統",
        value=(
            "`/查看背包` - 查看抽卡物品庫存\n"
            "`/出售物品` - 出售物品換金錢\n"
            "`/一鍵出售` - 批量出售物品"
        ),
        inline=False
    )

    # 📅 簽到系統
    embed.add_field(
        name="📅 簽到系統",
        value=(
            "`/簽到` - 每日簽到領獎勵\n"
            "`/簽到資訊` - 查看簽到統計\n"
            "`/簽到排行榜` - 簽到排行榜"
        ),
        inline=False
    )

    # 📈 股票系統
    embed.add_field(
        name="📈 股票系統",
        value=(
            "`/全部股票` - 快速查看股票總覽\n"
            "`/股票列表` - 查看可交易股票\n"
            "`/股票詳情` - 查看股票詳細資訊\n"
            "`/買入股票` - 買入股票\n"
            "`/賣出股票` - 賣出股票\n"
            "`/我的持倉` - 查看股票持倉\n"
            "`/交易記錄` - 查看交易記錄\n"
            "`/股票排行榜` - 股票大亨排行榜"
        ),
        inline=False
    )

    # ⚔️ 戰鬥系統
    embed.add_field(
        name="⚔️ 戰鬥系統",
        value=(
            "`/單挑` - 與朋友決鬥\n"
            "`/搶劫` - 搶劫其他玩家（冷卻 3 分鐘）"
        ),
        inline=False
    )

    # 🎖️ 牌位系統
    embed.add_field(
        name="🎖️ 牌位系統",
        value=(
            "`/我的牌位` - 查看你的牌位\n"
            "`/查看牌位` - 查看其他玩家牌位\n"
            "`/段位排行榜` - 段位排行榜 Top 10\n"
            "`/段位說明` - 查看段位詳細說明"
        ),
        inline=False
    )

    # 🏆 成就系統
    embed.add_field(
        name="🏆 成就系統",
        value=(
            "`/我的成就` - 查看成就進度\n"
            "`/成就詳情` - 查看特定成就\n"
            "`/成就排行榜` - 成就解鎖排行榜"
        ),
        inline=False
    )

    # 🏪 商城系統
    embed.add_field(
        name="🏪 商城系統",
        value=(
            "`/商店` - 查看商城商品\n"
            "`/購買` - 購買商城道具\n"
            "`/我的道具` - 查看擁有道具\n"
            "`/使用道具` - 使用消耗品"
        ),
        inline=False
    )

    # 🔮 占卜系統
    embed.add_field(
        name="🔮 占卜系統",
        value=(
            "`/占卜` - 每日運勢占卜\n"
            "`/占卜統計` - 查看占卜歷史\n"
            "`/占卜排行榜` - 幸運排行榜"
        ),
        inline=False
    )

    # 🎵 音樂系統
    embed.add_field(
        name="🎵 音樂系統",
        value=(
            "`/加入` - 加入語音頻道\n"
            "`/播放` - 播放音樂（網址或關鍵字）\n"
            "`/暫停` - 暫停音樂\n"
            "`/繼續` - 繼續播放\n"
            "`/跳過` - 跳過當前歌曲\n"
            "`/停止` - 停止播放並清空佇列\n"
            "`/循環` - 開啟/關閉單曲循環\n"
            "`/自動播放` - 開啟/關閉自動播放\n"
            "`/播放清單` - 查看播放佇列\n"
            "`/正在播放` - 顯示當前歌曲\n"
            "`/離開` - 離開語音頻道\n"
            "`/播放歷史` - 查看最近播放\n"
            "`/清除音樂歷史` - 清除播放記錄\n"
            "`/重新整理` - 重新獲取播放連結"
        ),
        inline=False
    )

    # 🔥 特效系統
    embed.add_field(
        name="🔥 特效系統",
        value=(
            "`/fire` - 為頭像加上火焰特效(SHIT)"
        ),
        inline=False
    )

    # 🛠️ 管理員指令
    embed.add_field(
        name="🛠️ 管理員指令",
        value=(
            "`/設定金錢` - 設定指定用戶金錢\n"
            "`/調整金錢` - 增加/扣除用戶金錢\n"
            "`/設定up角色` - 更改 UP 角色\n"
            "`/頭像` - 獲得使用者頭像\n"
            "`/banner` - 獲得使用者橫幅\n"
        ),
        inline=False
    )

    embed.set_footer(text="💡 部分指令需要特定權限或在特定頻道使用")
    embed.timestamp = datetime.now()

    await interaction.response.send_message(embed=embed)

# ==================== 📸 頭像/Banner 系統 ====================

@bot.tree.command(name="頭像", description="獲取用戶的頭像")
@app_commands.describe(用戶="要查看的用戶（預設為自己）", 大小="圖片大小")
@app_commands.choices(大小=[
    app_commands.Choice(name='小 (128px)', value=128),
    app_commands.Choice(name='中 (256px)', value=256),
    app_commands.Choice(name='大 (512px)', value=512),
    app_commands.Choice(name='特大 (1024px)', value=1024),
    app_commands.Choice(name='超大 (2048px)', value=2048),
    app_commands.Choice(name='最大 (4096px)', value=4096),
])
async def get_avatar(interaction: discord.Interaction, 用戶: discord.User = None,
                     大小: app_commands.Choice[int] = None):
    """獲取頭像"""
    target = 用戶 or interaction.user
    size = 大小.value if 大小 else 1024

    avatar_url = target.display_avatar.with_size(size).url

    embed = discord.Embed(
        title=f"🖼️ {target.display_name} 的頭像",
        color=discord.Color.blue()
    )
    embed.set_image(url=avatar_url)
    embed.add_field(name="📏 尺寸", value=f"{size}x{size}px", inline=True)
    embed.add_field(name="🔗 直連", value=f"[點擊下載]({avatar_url})", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="banner", description="獲取用戶的 Banner")
@app_commands.describe(用戶="要查看的用戶（預設為自己）")
async def get_banner(interaction: discord.Interaction, 用戶: discord.User = None):
    """獲取 Banner"""
    target = 用戶 or interaction.user

    # 需要 fetch 才能拿到 banner
    try:
        user = await bot.fetch_user(target.id)

        if user.banner:
            banner_url = user.banner.with_size(1024).url

            embed = discord.Embed(
                title=f"🎨 {target.display_name} 的 Banner",
                color=discord.Color.purple()
            )
            embed.set_image(url=banner_url)
            embed.add_field(name="🔗 直連", value=f"[點擊下載]({banner_url})", inline=False)

            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"❌ {target.mention} 沒有設定 Banner",
                ephemeral=True
            )
    except Exception as e:
        await interaction.response.send_message(f"❌ 獲取 Banner 失敗：{e}", ephemeral=True)


@bot.tree.command(name="個人資料", description="查看完整的用戶個人資料")
@app_commands.describe(用戶="要查看的用戶（預設為自己）")
async def user_profile(interaction: discord.Interaction, 用戶: discord.User = None):
    """完整個人資料"""
    target = 用戶 or interaction.user

    try:
        user = await bot.fetch_user(target.id)
        member = interaction.guild.get_member(target.id)

        embed = discord.Embed(
            title=f"👤 {user.display_name} 的個人資料",
            color=user.accent_color or discord.Color.blue()
        )

        # 頭像
        embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

        # Banner
        if user.banner:
            embed.set_image(url=user.banner.with_size(1024).url)

        # 基本資訊
        embed.add_field(
            name="📝 基本資訊",
            value=(
                f"**用戶名：** {user.name}\n"
                f"**ID：** `{user.id}`\n"
                f"**創建時間：** <t:{int(user.created_at.timestamp())}:R>"
            ),
            inline=False
        )

        # 伺服器資訊
        if member:
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            embed.add_field(
                name="🏰 伺服器資訊",
                value=(
                    f"**暱稱：** {member.display_name}\n"
                    f"**加入時間：** <t:{int(member.joined_at.timestamp())}:R>\n"
                    f"**身分組：** {' '.join(roles[:5]) if roles else '無'}"
                ),
                inline=False
            )

        # 遊戲統計
        money = MoneySystem.get_money(target.id)
        gacha_data = GachaSystem.get_user_pity(target.id)
        rank_data = RankingSystem.get_user_data(target.id)
        rank_info = RankingSystem.get_rank_info(rank_data['rank'])

        embed.add_field(
            name="🎮 遊戲統計",
            value=(
                f"💰 金錢：**{money:,}** 元\n"
                f"🎲 抽卡：**{gacha_data['total_pulls']}** 抽\n"
                f"🎖️ 牌位：{rank_info['emoji']} **{rank_info['name']}**"
            ),
            inline=False
        )

        # 下載連結
        links = []
        links.append(f"[頭像]({user.display_avatar.with_size(4096).url})")
        if user.banner:
            links.append(f"[Banner]({user.banner.with_size(4096).url})")

        embed.add_field(
            name="🔗 下載連結",
            value=" | ".join(links),
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ 獲取資料失敗：{e}", ephemeral=True)


# ==================== 主程式進入點 ====================
if __name__ == "__main__":
    print()

    # 檢查 FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        print("✅ FFmpeg 已安裝")
    except:
        print("❌ 警告：找不到 FFmpeg！請先安裝 FFmpeg。")

    # 檢查火焰影片
    if os.path.exists(FOREGROUND_VIDEO):
        print(f"✅ 火焰影片已找到：{FOREGROUND_VIDEO}")
    else:
        print(f"❌ 警告：找不到火焰影片：{FOREGROUND_VIDEO}")

    print()
    print("正在啟動 Bot...")

    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n正在關閉 Bot...")
    finally:
        # 關閉前儲存資料
        DataManager.save_data()
        print("👋 Bot 已安全關閉")
