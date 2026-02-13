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

# ランダム返信メッセージリスト
RANDOM_REPLIES = [
    "なんでボットと喧嘩してるの", "スキル不足", "負け犬", "lol", "クソ", "笑える",
    "ハハハハ", "ゴミ", "かわいそう", "それだけ？", "既読", "却下", "次は必ず", "fuck",
    "知らないな", "ママは知ってる？", "🗿", "やだ", "めんどくさい", "後で", "消えろ",
    "no", "cope", "L", "ratio", "誰も聞いてない", "didn't ask", "touch grass",
    "忙しい", "黙れ", "うるさい", "shut up", "cringe", "💀", "🤡",
    "nobody cares", "ok and?", "so what", "うざい", "annoying af", "mald",
    "seethe", "cope harder", "L + ratio + cope", "誰も気にしない", "関係ない",
    "既読スルー", "seen", "は？", "だから何", "知らんがな", "👎", "🖕", "cry more",
    "whatever", "どうでもいい", "相手したくない", "失せろ", "get rekt", "gg ez", "trash",
    "雑魚", "笑うわ", "弱すぎ", "ダメ", "へへ", "うんうん", "sure jan", "yikes", "oof",
    "言いたくない", "無言", "speechless", "😑", "🙄", "😴", "🥱", "ちょっと",
    "いい加減にして", "諦めろ", "ふざけるな", "can't relate",
    "not my problem", "idc", "idk", "nah", "nope", "pass", "blocked",
    "muted", "ignored", "めんどい", "したくない", "お断り", "ご意見ありがとう", "次の方", "next",
    "skip", "boring", "つまらない", "ネタがない", "古いネタ", "heard it before", "続けて",
    "then what", "and?", "your point?", "要点は？", "だから", "じゃなきゃ",
    "who asked tho", "まあまあ", "そんなもん", "普通", "mid", "夢見すぎ", "夢",
    "考えすぎ", "overthinking", "delusional", "よく言えるな", "恥ずかしくないの", "I'm dead",
    "💩", "📉", "🚮", "not it", "hard pass", "major L", "massive L",
    "楽しければいいね", "自分で楽しめばいい", "頑張れよ", "自己満足", "stay mad",
    "keep crying", "git gud", "uninstall", "リセマラしろ", "seriously?",
    "for real?", "マジで", "sure buddy", "ok boomer", "時代遅れ", "outdated",
    "救いようがない", "hopeless", "終わったな", "it's over", "gg ez", "FUCK OFF",
    "nigger", "stfu"
]

# ==================== Discord Bot 初期化 ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==================== お金システム ====================
class MoneySystem:
    user_money: Dict[int, int] = {}  # ユーザーのお金
    user_stats: Dict[int, dict] = {}  # ユーザー統計データ
    earn_cooldowns: Dict[int, datetime] = {}  # お金稼ぎクールダウン

    @classmethod
    def get_money(cls, user_id: int) -> int:
        """ユーザーのお金を取得"""
        if user_id not in cls.user_money:
            cls.user_money[user_id] = 0
        return cls.user_money[user_id]

    @classmethod
    def add_money(cls, user_id: int, amount: int):
        """お金を追加（ショップバフ統合）"""
        # ===== 🆕 財運お守り効果 =====
        if ShopSystem.has_active_item(user_id, 'double_money'):
            amount *= 2

        if user_id not in cls.user_money:
            cls.user_money[user_id] = 0

        # 破産チェック
        if cls.user_money[user_id] == 0 and amount > 0:
            tracking = AchievementSystem.get_user_tracking(user_id)
            tracking['bankruptcy_count'] += 1

        cls.user_money[user_id] += amount
        cls._update_stats(user_id, 'total_earned', amount)

    @classmethod
    def deduct_money(cls, user_id: int, amount: int) -> bool:
        """お金を差し引く、成功したかどうかを返す"""
        if cls.get_money(user_id) >= amount:
            cls.user_money[user_id] -= amount
            cls._update_stats(user_id, 'total_spent', amount)
            return True
        return False

    @classmethod
    def transfer_money(cls, from_user: int, to_user: int, amount: int) -> Tuple[bool, int]:
        """
        送金機能
        戻り値：(成功したか, 手数料)
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
        クールダウン時間をチェック
        戻り値：残り秒数（None は使用可能）
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
        """クールダウン時間を設定"""
        cls.earn_cooldowns[user_id] = datetime.now()

    @classmethod
    def get_stats(cls, user_id: int) -> dict:
        """ユーザー統計データを取得"""
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
        """統計データを更新"""
        stats = cls.get_stats(user_id)
        if stat_name in stats:
            stats[stat_name] += amount


# ==================== アイテム管理システム ====================
class InventorySystem:
    """
    アイテム管理システム
    ユーザーのガチャアイテム在庫を管理
    """
    user_inventory: Dict[int, Dict[str, int]] = {}  # {user_id: {'blue': 数量, 'purple': 数量, ...}}

    # アイテム価格表
    ITEM_PRICES = {
        'blue': 30,  # 星3
        'purple': 170,  # 星4
        'gold_up': 2600,  # 星5UP
        'gold_off': 2000  # 星5すり抜け
    }

    @classmethod
    def get_inventory(cls, user_id: int) -> Dict[str, int]:
        """ユーザーのアイテム在庫を取得"""
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
        """アイテムを追加"""
        inventory = cls.get_inventory(user_id)
        if item_type in inventory:
            inventory[item_type] += amount

    @classmethod
    def remove_item(cls, user_id: int, item_type: str, amount: int = 1) -> bool:
        """アイテムを削除、成功したかどうかを返す"""
        inventory = cls.get_inventory(user_id)
        if item_type in inventory and inventory[item_type] >= amount:
            inventory[item_type] -= amount
            return True
        return False

    @classmethod
    def sell_item(cls, user_id: int, item_type: str, amount: int = 1) -> Tuple[bool, int]:
        """
        アイテムを売却
        戻り値：(成功したか, 獲得金額)
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
        """在庫総額を計算"""
        inventory = cls.get_inventory(user_id)
        total = 0
        for item_type, count in inventory.items():
            if item_type in cls.ITEM_PRICES:
                total += cls.ITEM_PRICES[item_type] * count
        return total


# ==================== ガチャシステム ====================
class GachaSystem:
    """
    崩壊スターレイル風ガチャシステム
    ソフト天井、ハード天井、確定天井メカニズムを含む
    """
    # 恒常星5キャラクタープール
    STANDARD_5STAR = ['ブローニャ', 'クララ', '姫子', 'ジェパード', '白露', 'ヴェルト', '彦卿']

    # UPキャラクター名
    current_up_character = '花火'

    # 各ユーザーのガチャ状態を保存
    user_data: Dict[int, dict] = {}

    @classmethod
    def get_user_pity(cls, user_id: int):
        """ユーザーの天井状態を取得"""
        if user_id not in cls.user_data:
            cls.user_data[user_id] = {
                'pity_count': 0,  # 前回星5からの引き数
                'guarantee': False,  # 確定天井かどうか
                'four_star_pity': 0,  # 星4天井カウント
                'history': [],  # ガチャ履歴記録
                'total_pulls': 0,  # 総ガチャ回数
                'five_star_count': 0,  # 星5総数
                'five_star_up_count': 0,  # UP星5数量
            }
        return cls.user_data[user_id]

    @classmethod
    def single_pull(cls, user_id: int):
        """単発ガチャロジック"""
        data = cls.get_user_pity(user_id)
        data['pity_count'] += 1
        data['four_star_pity'] += 1
        data['total_pulls'] += 1

        # 星5判定（90連ハード天井）
        base_5star_rate = 0.006  # 0.6% 基本星5率

        if ShopSystem.has_active_item(user_id, 'gacha_luck'):
            base_5star_rate += 0.03  # 幸運の草 +3%

        # ソフト天井メカニズム（73連後確率上昇）
        if data['pity_count'] >= 73:
            base_5star_rate += (data['pity_count'] - 72) * 0.06

        # ハード天井または星5当選
        if data['pity_count'] >= 90 or random.random() < base_5star_rate:
            current_pull = data['pity_count']
            data['five_star_count'] += 1

            if data['guarantee']:
                # 確定天井：必ずUP
                result = ('gold_up', current_pull)
                data['guarantee'] = False
                data['five_star_up_count'] += 1
                data['history'].append(('星5UP', cls.current_up_character, current_pull))
                InventorySystem.add_item(user_id, 'gold_up')
            else:
                # 小天井：50%確率でUP
                if random.random() < 0.5:
                    result = ('gold_up', current_pull)
                    data['guarantee'] = False
                    data['five_star_up_count'] += 1
                    data['history'].append(('星5UP', cls.current_up_character, current_pull))
                    InventorySystem.add_item(user_id, 'gold_up')
                else:
                    # すり抜け
                    off_banner_char = random.choice(cls.STANDARD_5STAR)
                    result = ('gold_off', off_banner_char, current_pull)
                    data['guarantee'] = True
                    data['history'].append(('星5すり抜け', off_banner_char, current_pull))
                    InventorySystem.add_item(user_id, 'gold_off')

            data['pity_count'] = 0
            data['four_star_pity'] = 0
            return result

        # 星4判定（10連ハード天井）
        base_4star_rate = 0.051

        if data['four_star_pity'] >= 10 or random.random() < base_4star_rate:
            data['four_star_pity'] = 0
            InventorySystem.add_item(user_id, 'purple')
            return 'purple'

        # 星3
        InventorySystem.add_item(user_id, 'blue')
        return 'blue'

    @classmethod
    def ten_pull(cls, user_id: int):
        """10連ガチャ"""
        results = []
        for _ in range(10):
            results.append(cls.single_pull(user_id))
        return results

    @staticmethod
    def rarity_to_emoji(rarity):
        """レアリティを絵文字に変換"""
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
        """5x2形式にフォーマット"""
        lines = []
        for i in range(0, 10, 5):
            row = results[i:i + 5]
            lines.append(' '.join([GachaSystem.rarity_to_emoji(r) for r in row]))
        return '\n'.join(lines)

    @classmethod
    def get_gacha_stats(cls, user_id: int) -> dict:
        """ガチャ統計を取得"""
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


# ==================== ギャンブルシステム ====================
class GambleSystem:
    """ギャンブルシステム"""

    @staticmethod
    def get_tier_info(amount: int) -> Tuple[str, int, float]:
        """
        賭け金額に応じて返す：(ランク名, 倍率, 勝率)
        """
        if amount <= 500:
            return "小遣い稼ぎ", 2, 0.6
        elif amount <= 2000:
            return "中規模賭博", 3, 0.4
        elif amount <= 5000:
            return "ハイリスク賭博", 5, 0.19
        else:
            return "大勝負", 10, 0.1

    @classmethod
    def gamble(cls, user_id: int, amount: int) -> Tuple[bool, int, str]:
        """ギャンブル実行（ショップバフ統合）"""
        tier, multiplier, win_rate = cls.get_tier_info(amount)

        # ===== 🆕 ショップバフボーナス =====
        if ShopSystem.has_active_item(user_id, 'gamble_boost'):
            win_rate += 0.15
            win_rate = min(win_rate, 0.95)

        is_win = random.random() < win_rate

        # ===== 連勝追跡（実績用） =====
        tracking = AchievementSystem.get_user_tracking(user_id)

        if is_win:
            reward = amount * multiplier
            profit = reward - amount
            MoneySystem.get_stats(user_id)['gamble_wins'] += 1
            MoneySystem.get_stats(user_id)['gamble_total_won'] += profit

            # 連勝カウント
            tracking['gamble_streak'] += 1

            return True, reward, tier
        else:
            MoneySystem.get_stats(user_id)['gamble_losses'] += 1
            MoneySystem.get_stats(user_id)['gamble_total_lost'] += amount

            # 連勝中断
            tracking['gamble_streak'] = 0

            return False, amount, tier


# ==================== ミニゲームシステム ====================
class MiniGames:
    """ミニゲーム集"""

    @staticmethod
    def guess_number_game() -> int:
        """数当てゲーム：正解を返す（1-5）"""
        return random.randint(1, 5)

    @staticmethod
    def rock_paper_scissors(player_choice: str) -> Tuple[str, str]:
        """
        じゃんけん
        戻り値：(ボットの選択, 結果: 'win'/'lose'/'tie')
        """
        choices = ['はさみ', 'いわ', 'かみ']
        bot_choice = random.choice(choices)

        win_conditions = {
            'はさみ': 'かみ',
            'いわ': 'はさみ',
            'かみ': 'いわ'
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
        サイコロ勝負
        戻り値：(プレイヤーの出目, ボットの出目, 結果: 'win'/'lose'/'tie')
        """
        player_dice = random.randint(1, 6)
        bot_dice = random.randint(1, 6)

        if player_dice > bot_dice:
            return player_dice, bot_dice, 'win'
        elif player_dice < bot_dice:
            return player_dice, bot_dice, 'lose'
        else:
            return player_dice, bot_dice, 'tie'


# ==================== ランキングシステム ====================
class LeaderboardSystem:
    """ランキングシステム"""

    @staticmethod
    def get_money_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
        """お金ランキング"""
        sorted_users = sorted(
            MoneySystem.user_money.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_users[:limit]

    @staticmethod
    def get_gacha_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
        """ガチャ回数ランキング"""
        gacha_counts = [
            (user_id, data['total_pulls'])
            for user_id, data in GachaSystem.user_data.items()
        ]
        sorted_users = sorted(gacha_counts, key=lambda x: x[1], reverse=True)
        return sorted_users[:limit]

    @staticmethod
    def get_gamble_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
        """ギャンブル最高利益ランキング"""
        gamble_profits = [
            (user_id, stats['gamble_total_won'] - stats['gamble_total_lost'])
            for user_id, stats in MoneySystem.user_stats.items()
        ]
        sorted_users = sorted(gamble_profits, key=lambda x: x[1], reverse=True)
        return sorted_users[:limit]


# ==================== FFmpeg 動画合成システム ====================
class FFmpegComposer:
    """FFmpegを使用した動画合成"""

    @staticmethod
    def create_temp_path(ext: str) -> str:
        """一時ファイルパスを生成"""
        timestamp = int(time.time() * 1000)
        random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
        return os.path.join(tempfile.gettempdir(), f'fire-{timestamp}-{random_str}{ext}')

    @staticmethod
    async def download_file(url: str, dest: str) -> None:
        """ファイルをダウンロード"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f'ファイルのダウンロードに失敗: HTTP {resp.status}')
                with open(dest, 'wb') as f:
                    f.write(await resp.read())

    @staticmethod
    def get_video_dimensions(video_path: str) -> tuple[int, int]:
        """ffprobeを使用して動画サイズを取得"""
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
        """FFmpegを使用して動画を合成"""
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
        """MP4をGIFに変換"""
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
        """メイン合成関数"""
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


# ==================== 📅 デイリーチェックインシステム ====================
class DailyCheckIn:
    """デイリーチェックインシステム"""
    user_checkin: Dict[int, dict] = {}  # {user_id: {'last_checkin': datetime, 'streak': int}}

    # チェックイン報酬表
    CHECKIN_REWARDS = [200, 400, 800, 1200, 2000, 2200]
    BONUS_REWARD = 300  # 7日目以降の毎日追加報酬

    @classmethod
    def get_user_data(cls, user_id: int) -> dict:
        """ユーザーチェックインデータを取得"""
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
        チェックイン可能かチェック
        戻り値：(チェックイン可能か, エラーメッセージ)
        """
        data = cls.get_user_data(user_id)

        if data['last_checkin'] is None:
            return True, None

        now = datetime.now()
        last_checkin = data['last_checkin']

        # 前回のチェックインからの時間を計算
        time_diff = now - last_checkin

        # 前回のチェックインから24時間未満の場合
        if time_diff < timedelta(hours=24):
            remaining = timedelta(hours=24) - time_diff
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return False, f"⏰ 今日はもうチェックイン済みです！\n次回チェックイン時間：**{hours}時間{minutes}分**後"

        return True, None

    @classmethod
    def calculate_reward(cls, streak: int) -> int:
        """チェックイン報酬を計算"""
        if streak < len(cls.CHECKIN_REWARDS):
            return cls.CHECKIN_REWARDS[streak]
        else:
            # 7日目以降、基本2200 + 追加300
            days_after_six = streak - len(cls.CHECKIN_REWARDS)
            return cls.CHECKIN_REWARDS[-1] + (cls.BONUS_REWARD * (days_after_six + 1))

    @classmethod
    def checkin(cls, user_id: int) -> Tuple[int, int, bool]:
        """
        チェックインを実行
        戻り値：(獲得金額, 連続日数, 連続記録が途切れたか)
        """
        data = cls.get_user_data(user_id)
        now = datetime.now()

        broke_streak = False

        # 連続記録が途切れたかチェック
        if data['last_checkin'] is not None:
            time_diff = now - data['last_checkin']

            # 48時間以上経過した場合、連続記録が途切れたとみなす
            if time_diff >= timedelta(hours=48):
                data['streak'] = 0
                broke_streak = True
            else:
                data['streak'] += 1
        else:
            # 初回チェックイン
            data['streak'] = 0

        # 報酬を計算
        reward = cls.calculate_reward(data['streak'])

        # データを更新
        data['last_checkin'] = now
        data['total_checkins'] += 1
        data['total_earned'] += reward

        # 報酬を付与
        MoneySystem.add_money(user_id, reward)

        current_streak = data['streak'] + 1  # +1 今日を含む

        return reward, current_streak, broke_streak

    @classmethod
    def get_next_rewards(cls, current_streak: int, count: int = 7) -> List[Tuple[int, int]]:
        """
        今後数日間の報酬プレビューを取得
        戻り値：[(日数, 報酬金額), ...]
        """
        rewards = []
        for i in range(count):
            day = current_streak + i
            reward = cls.calculate_reward(day)
            rewards.append((day + 1, reward))
        return rewards


# ==================== 📅 チェックインコマンド ====================

@bot.tree.command(name="チェックイン", description="デイリーチェックインで報酬を受け取る")
async def daily_checkin(interaction: discord.Interaction):
    """デイリーチェックイン"""
    user_id = interaction.user.id

    # チェックイン可能かチェック
    can_checkin, error_msg = DailyCheckIn.can_checkin(user_id)

    if not can_checkin:
        await interaction.response.send_message(error_msg, ephemeral=True)
        return

    # チェックインを実行
    reward, streak, broke_streak = DailyCheckIn.checkin(user_id)

    # メッセージを構築
    message_parts = [
        f"✅ **チェックイン成功！**",
        f"",
    ]

    if broke_streak:
        message_parts.append(f"⚠️ 連続チェックインが中断！新たに開始します")
        message_parts.append(f"")

    message_parts.extend([
        f"💰 獲得金額：**{reward}** 円",
        f"🔥 連続チェックイン：**{streak}** 日",
        f"💵 現在の金額：**{MoneySystem.get_money(user_id)}** 円",
        f"",
    ])

    # 今後7日間の報酬を表示
    next_rewards = DailyCheckIn.get_next_rewards(streak, 7)
    message_parts.append("📅 **今後の報酬プレビュー：**")

    for day, amount in next_rewards:
        if day == streak + 1:
            message_parts.append(f"├ 明日（{day}日目）：**{amount}** 円")
        else:
            message_parts.append(f"├ {day}日目：**{amount}** 円")

    # 特別なお知らせ
    if streak >= 6:
        message_parts.append(f"")
        message_parts.append(f"🎉 連続チェックイン6日達成おめでとう！以降毎日 +300 円！")

    await AchievementSystem.check_and_unlock(user_id, interaction.channel)
    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="チェックイン情報", description="あなたのチェックイン統計を見る")
async def checkin_info(interaction: discord.Interaction):
    """チェックイン情報"""
    user_id = interaction.user.id
    data = DailyCheckIn.get_user_data(user_id)

    if data['last_checkin'] is None:
        await interaction.response.send_message(
            "📅 まだチェックインしたことがないよ！\n`/チェックイン` でチェックインの旅を始めよう！",
            ephemeral=True
        )
        return

    # 今日チェックイン済みかチェック
    can_checkin, _ = DailyCheckIn.can_checkin(user_id)
    today_status = "❌ 今日はチェックイン済み" if not can_checkin else "✅ 今日はまだチェックインしていません"

    # 次回チェックイン時間を計算
    if not can_checkin:
        now = datetime.now()
        time_diff = now - data['last_checkin']
        remaining = timedelta(hours=24) - time_diff
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        next_checkin = f"{hours}時間{minutes}分後"
    else:
        next_checkin = "今すぐチェックインできます！"

    message = f"""
📅 **{interaction.user.display_name} のチェックイン情報**

🔥 **現在の連続記録：{data['streak'] + 1}** 日
📊 **累計チェックイン：{data['total_checkins']}** 回
💰 **チェックイン総収入：{data['total_earned']}** 円

{today_status}
⏰ **次回チェックイン：{next_checkin}**

💡 **ヒント：**
- 連続チェックイン報酬は増加します
- 48時間以上チェックインしないと連続記録が途切れます
- 7日目以降は毎日固定 2200 + 300×日数
"""

    await interaction.response.send_message(message)


@bot.tree.command(name="チェックインランキング", description="チェックインランキングを見る")
async def checkin_leaderboard(interaction: discord.Interaction):
    """チェックインランキング"""
    # ソート：連続日数、次に総チェックイン回数
    sorted_users = sorted(
        DailyCheckIn.user_checkin.items(),
        key=lambda x: (x[1]['streak'], x[1]['total_checkins']),
        reverse=True
    )[:10]

    if not sorted_users:
        await interaction.response.send_message("📊 まだチェックインデータがありません！", ephemeral=True)
        return

    message_parts = [
        "🏆 **チェックインランキング Top 10**",
        "（連続日数順）",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, data) in enumerate(sorted_users, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        streak = data['streak'] + 1
        total = data['total_checkins']

        message_parts.append(f"{medal} **{name}**: {streak}日連続 ({total}回合計)")

    await interaction.response.send_message('\n'.join(message_parts))

# ==================== 💾 データ管理システム ====================
class DataManager:
    """データ管理システム - 安定版"""
    DATA_FILE = Path("bot_data.json")
    BACKUP_DIR = Path("backups")
    MAX_BACKUPS = 5  # 最新5つのバックアップを保持

    @classmethod
    def ensure_backup_dir(cls):
        """バックアップディレクトリが存在することを確認"""
        if not cls.BACKUP_DIR.exists():
            cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_backup(cls):
        """バックアップを作成"""
        if not cls.DATA_FILE.exists():
            return

        try:
            cls.ensure_backup_dir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = cls.BACKUP_DIR / f"bot_data_{timestamp}.json"

            shutil.copy(cls.DATA_FILE, backup_file)
            print(f"📦 バックアップ作成：{backup_file.name}")

            # 古いバックアップをクリーンアップ
            cls.cleanup_old_backups()
        except Exception as e:
            print(f"⚠️ バックアップ失敗：{e}")

    @classmethod
    def cleanup_old_backups(cls):
        """古いバックアップをクリーンアップ、最新のものだけを保持"""
        try:
            backups = sorted(cls.BACKUP_DIR.glob("bot_data_*.json"), reverse=True)

            for old_backup in backups[cls.MAX_BACKUPS:]:
                old_backup.unlink()
                print(f"🗑️ 古いバックアップを削除：{old_backup.name}")
        except Exception as e:
            print(f"⚠️ バックアップのクリーンアップ失敗：{e}")

    @classmethod
    def load_data(cls):
        """データを読み込む（エラー回復付き）"""
        if not cls.DATA_FILE.exists():
            print("ℹ️ 保存データなし、空のデータを使用します")
            return

        try:
            with open(cls.DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ==================== 各システムデータを読み込む ====================
            cls._load_money_data(data)
            cls._load_gacha_data(data)
            cls._load_inventory_data(data)
            cls._load_checkin_data(data)
            cls._load_stock_data(data)
            cls._load_achievement_data(data)
            cls._load_shop_data(data)
            cls._load_ranking_data(data)
            cls._load_fortune_data(data)

            print("✅ データ読み込み成功！")
            cls._print_load_summary()

        except json.JSONDecodeError as e:
            print(f"❌ JSON解析エラー：{e}")
            print(f"   エラー位置：{e.lineno}行、{e.colno}列")
            print("🔄 バックアップから復元を試みます...")

            if cls._restore_from_backup():
                print("✅ バックアップからデータを復元しました")
                cls.load_data()  # 再読み込み
            else:
                print("❌ 利用可能なバックアップなし、空のデータを使用します")

        except Exception as e:
            print(f"❌ データ読み込み失敗：{e}")
            import traceback
            traceback.print_exc()

    @classmethod
    def _restore_from_backup(cls) -> bool:
        """バックアップから復元"""
        try:
            cls.ensure_backup_dir()
            backups = sorted(cls.BACKUP_DIR.glob("bot_data_*.json"), reverse=True)

            for backup in backups:
                try:
                    with open(backup, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # バックアップが有効、メインファイルにコピー
                    shutil.copy(backup, cls.DATA_FILE)
                    print(f"✅ {backup.name} から復元しました")
                    return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"❌ 復元失敗：{e}")
            return False

    @classmethod
    def _load_money_data(cls, data):
        """お金データを読み込む"""
        if 'money' in data:
            MoneySystem.user_money = {int(k): v for k, v in data['money'].items()}
        if 'stats' in data:
            MoneySystem.user_stats = {int(k): v for k, v in data['stats'].items()}

    @classmethod
    def _load_gacha_data(cls, data):
        """ガチャデータを読み込む"""
        if 'gacha' in data:
            for user_id, user_data in data['gacha'].items():
                GachaSystem.user_data[int(user_id)] = user_data

    @classmethod
    def _load_inventory_data(cls, data):
        """アイテムデータを読み込む"""
        if 'inventory' in data:
            InventorySystem.user_inventory = {int(k): v for k, v in data['inventory'].items()}

    @classmethod
    def _load_checkin_data(cls, data):
        """チェックインデータを読み込む"""
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
        """株式データを読み込む"""
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
        """実績データを読み込む"""
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
        """ショップアイテムを読み込む"""
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
        """ランクデータを読み込む"""
        if 'rankings' in data:
            RankingSystem.user_rankings = {
                int(k): v for k, v in data['rankings'].items()
            }

    @classmethod
    def _load_fortune_data(cls, data):

        if 'fortunes' in data:
            FortuneSystem.user_fortunes = {int(k): v for k, v in data['fortunes'].items()}

        if 'fortune_history' in data:
            FortuneSystem.fortune_history = {int(k): v for k, v in data['fortune_history'].items()}

    @classmethod
    def _print_load_summary(cls):
        """読み込み概要を表示"""
        print(f"   - お金：{len(MoneySystem.user_money)} 人のユーザー")
        print(f"   - 統計：{len(MoneySystem.user_stats)} 人のユーザー")
        print(f"   - ガチャ：{len(GachaSystem.user_data)} 人のユーザー")
        print(f"   - アイテム：{len(InventorySystem.user_inventory)} 人のユーザー")
        print(f"   - チェックイン：{len(DailyCheckIn.user_checkin)} 人のユーザー")
        print(f"   - 株式：{len(StockSystem.user_holdings)} 人のユーザー")
        print(f"   - 実績：{len(AchievementSystem.user_achievements)} 人のユーザー")
        print(f"   - ランク：{len(RankingSystem.user_rankings)} 人のユーザー")

    @classmethod
    def save_data(cls):
        """データを保存（バックアップ付き）"""
        try:
            # 1. バックアップを作成
            if cls.DATA_FILE.exists():
                cls.create_backup()

            # 2. 全データを準備
            data = cls._prepare_all_data()

            # 3. まず一時ファイルに書き込む
            temp_file = cls.DATA_FILE.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 4. 一時ファイルを検証
            with open(temp_file, 'r', encoding='utf-8') as f:
                json.load(f)  # 正しく読み取れるかテスト

            # 5. メインファイルを置き換え
            if cls.DATA_FILE.exists():
                cls.DATA_FILE.unlink()
            temp_file.rename(cls.DATA_FILE)

            print("✅ データ保存完了")
            cls._print_save_summary()

        except Exception as e:
            print(f"❌ データ保存失敗：{e}")
            import traceback
            traceback.print_exc()

            # 破損した一時ファイルを削除
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
        """保存概要を表示"""
        print(f"   - お金：{len(MoneySystem.user_money)} 人のユーザー")
        print(f"   - 統計：{len(MoneySystem.user_stats)} 人のユーザー")
        print(f"   - ガチャ：{len(GachaSystem.user_data)} 人のユーザー")
        print(f"   - アイテム：{len(InventorySystem.user_inventory)} 人のユーザー")
        print(f"   - チェックイン：{len(DailyCheckIn.user_checkin)} 人のユーザー")
        print(f"   - 株式：{len(StockSystem.user_holdings)} 人のユーザー")


def cleanup_files(*files: str) -> None:
    """ファイルをクリーンアップ"""
    for file in files:
        try:
            if os.path.exists(file):
                os.remove(file)
        except:
            pass


# ==================== 定期自動保存 ====================
async def auto_save():
    """5分ごとに自動保存"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(300)  # 5分
        DataManager.save_data()
        print("🔄 自動保存完了")


# ==================== Bot イベント処理 ====================
@bot.event
async def on_ready():
    """Botが準備完了したとき"""
    print(f'🔥 Botが{bot.user}としてログインしました')

    # データを読み込む
    DataManager.load_data()

    # ⭐ 株式システムを初期化
    StockSystem.initialize()

    # ⭐ 株価更新を開始
    bot.loop.create_task(update_stock_prices())

    # 自動保存を開始
    bot.loop.create_task(auto_save())

    await bot.change_presence(activity=discord.Game(name="Powered / Made by yulun"))

    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)}個のコマンドを同期しました')
    except Exception as e:
        print(f'❌ コマンド同期中にエラー: {e}')


@bot.event
async def on_message(message):
    """メッセージを受信したとき"""
    if message.author == bot.user:
        return

    # 「クソ」をチェック
    if message.content.strip() == "クソ":
        await message.channel.send("クソ")
        return

    # ボットがメンションされているかチェック
    if bot.user.mentioned_in(message):
        reply = random.choice(RANDOM_REPLIES)
        await message.reply(reply)

    await bot.process_commands(message)

# ==================== 💸 お金関連コマンド ====================

@bot.tree.command(name="お金を見る", description="お金を確認（対象を指定可能）")
@app_commands.describe(対象="確認したい対象（デフォルトは自分）")
async def check_money(interaction: discord.Interaction, 対象: discord.User = None):
    """お金を確認"""
    # 対象が指定されていればその対象、そうでなければコマンド送信者（自分）を使用
    target_user = 対象 or interaction.user

    money = MoneySystem.get_money(target_user.id)

    await interaction.response.send_message(
        f"💰 **{target_user.display_name} の財布**\n"
        f"現在のお金：**{money}** 円"
    )


@bot.tree.command(name="送金", description="他のプレイヤーに送金（手数料 5%）")
@app_commands.describe(
    対象="送金先",
    金額="送金する金額"
)
async def transfer(interaction: discord.Interaction, 対象: discord.User, 金額: int):
    """送金システム"""
    user_id = interaction.user.id

    # 自分への送金チェック
    if 対象.id == user_id:
        await interaction.response.send_message("❌ 自分に送金できません！", ephemeral=True)
        return

    # 金額チェック
    if 金額 <= 0:
        await interaction.response.send_message("❌ 金額は0より大きくなければなりません！", ephemeral=True)
        return

    # 手数料計算
    fee = int(金額 * TRANSFER_FEE_RATE)
    total = 金額 + fee

    # 残高チェック
    current_money = MoneySystem.get_money(user_id)
    if current_money < total:
        await interaction.response.send_message(
            f"❌ お金が足りません！\n"
            f"必要：**{total}** 円（手数料 {fee} 円を含む）\n"
            f"あなたの所持金：**{current_money}** 円",
            ephemeral=True
        )
        return

    # 送金実行
    success, actual_fee = MoneySystem.transfer_money(user_id, 対象.id, 金額)

    if success:
        await interaction.response.send_message(
            f"✅ **送金成功！**\n"
            f"{interaction.user.mention} → {対象.mention}\n"
            f"💰 金額：**{金額}** 円\n"
            f"💸 手数料：**{actual_fee}** 円\n"
            f"📊 あなたの残高：**{MoneySystem.get_money(user_id)}** 円"
        )
    else:
        await interaction.response.send_message("❌ 送金失敗！", ephemeral=True)


# ==================== 🎮 お金稼ぎミニゲーム ====================

@bot.tree.command(name="稼ぐ", description="数学の問題に答えてお金を稼ぐ（クールタイム5秒）")
async def earn_money_jp(interaction: discord.Interaction):
    user_id = interaction.user.id

    # 檢查冷卻
    remaining = MoneySystem.check_cooldown(user_id)
    if remaining is not None:
        await interaction.response.send_message(
            f"⏰ クールタイム中！あと **{remaining}** 秒お待ちください",
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
        f"🧮 **数学タイム！**\n"
        f"10秒以内に答えてください：\n"
        f"**{question} = ?**"
    )

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', timeout=10.0, check=check)

        try:
            user_answer = int(msg.content.strip())
        except ValueError:
            await interaction.followup.send("❌ 数字を入力してください！")
            return

        if user_answer == answer:
            # 設置冷卻
            MoneySystem.set_cooldown(user_id)

            # 計算獎勵
            if random.random() < 0.4:
                base_reward = random.randint(20, 300)
            else:
                base_reward = random.randint(300, 2200)

            # 檢查發財符
            has_double = ShopSystem.has_active_item(user_id, 'double_money')

            if has_double:
                actual_reward = base_reward * 2
            else:
                actual_reward = base_reward

            # 手動加錢
            MoneySystem.user_money[user_id] = MoneySystem.user_money.get(user_id, 0) + actual_reward
            MoneySystem._update_stats(user_id, 'total_earned', base_reward)

            current_money = MoneySystem.get_money(user_id)

            # 根據是否雙倍顯示不同訊息
            if has_double:
                message = (
                    f"✅ **正解！**\n"
                    f"💰 基本報酬：**{base_reward}** 円\n"
                    f"✨ **発財符が発動！報酬2倍！**\n"
                    f"💵 実際獲得：**{actual_reward}** 円 (x2)\n"
                    f"📊 現在の所持金：**{current_money}** 円"
                )
            else:
                message = (
                    f"✅ **正解！**\n"
                    f"💰 獲得 **{actual_reward}** 円\n"
                    f"📊 現在の所持金：**{current_money}** 円"
                )

            await AchievementSystem.check_and_unlock(user_id, interaction.channel)
            await interaction.followup.send(message)
        else:
            MoneySystem.deduct_money(user_id, 200)
            current_money = MoneySystem.get_money(user_id)
            await AchievementSystem.check_and_unlock(user_id, interaction.channel)
            await interaction.followup.send(
                f"❌ **不正解！**\n"
                f"正解は：**{answer}**\n"
                f"💸 **200** 円を失いました\n"
                f"現在の所持金：**{current_money}** 円"
            )

    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ タイムアップ！回答なし")


@bot.tree.command(name="数当て", description="数当てゲーム（1-5、賭け金1000円、当たれば4500円）")
@app_commands.describe(数字="あなたの予想（1-5）")
@app_commands.choices(数字=[
    app_commands.Choice(name='1', value=1),
    app_commands.Choice(name='2', value=2),
    app_commands.Choice(name='3', value=3),
    app_commands.Choice(name='4', value=4),
    app_commands.Choice(name='5', value=5),
])
async def guess_number_jp(interaction: discord.Interaction, 数字: app_commands.Choice[int]):
    """数当てゲーム（日語版）"""
    user_id = interaction.user.id
    bet = 1000
    base_reward = 4500

    # 檢查金錢
    if not MoneySystem.deduct_money(user_id, bet):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ 所持金不足！**{bet}** 円必要ですが、**{current_money}** 円しかありません",
            ephemeral=True
        )
        return

    # 遊戲邏輯
    answer = MiniGames.guess_number_game()
    player_guess = 数字.value

    MoneySystem.get_stats(user_id)['games_played'] += 1

    if player_guess == answer:
        # 檢查發財符
        has_double = ShopSystem.has_active_item(user_id, 'double_money')

        if has_double:
            actual_reward = base_reward * 2
        else:
            actual_reward = base_reward

        # 手動加錢
        MoneySystem.user_money[user_id] = MoneySystem.user_money.get(user_id, 0) + actual_reward
        MoneySystem._update_stats(user_id, 'total_earned', base_reward)

        MoneySystem.get_stats(user_id)['games_won'] += 1
        current_money = MoneySystem.get_money(user_id)

        await AchievementSystem.check_and_unlock(user_id, interaction.channel)

        # 根據是否雙倍顯示不同訊息
        if has_double:
            message = (
                f"🎉 **当たり！**\n"
                f"答えは：**{answer}**\n"
                f"💰 基本報酬：**{base_reward}** 円\n"
                f"✨ **発財符が発動！報酬2倍！**\n"
                f"💎 実際獲得：**{actual_reward}** 円 (x2)\n"
                f"📊 現在の所持金：**{current_money}** 円"
            )
        else:
            message = (
                f"🎉 **当たり！**\n"
                f"答えは：**{answer}**\n"
                f"💰 獲得：**{actual_reward}** 円\n"
                f"📊 現在の所持金：**{current_money}** 円"
            )

        await interaction.response.send_message(message)
    else:
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"❌ **外れ！**\n"
            f"答えは：**{answer}**\n"
            f"あなたの予想：**{player_guess}**\n"
            f"💸 損失：**{bet}** 円\n"
            f"現在の所持金：**{MoneySystem.get_money(user_id)}** 円"
        )

@bot.tree.command(name="じゃんけん", description="ボットとじゃんけん勝負（2000円賭けて、勝てば3600円獲得）")
@app_commands.describe(選択="あなたの選択")
@app_commands.choices(選択=[
    app_commands.Choice(name='✂️ はさみ', value='はさみ'),
    app_commands.Choice(name='🪨 いわ', value='いわ'),
    app_commands.Choice(name='📄 かみ', value='かみ'),
])
async def rps(interaction: discord.Interaction, 選択: app_commands.Choice[str]):
    """じゃんけん勝負"""
    user_id = interaction.user.id
    bet = 2000
    reward = 3600

    # お金チェック
    if not MoneySystem.deduct_money(user_id, bet):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ お金が足りません！**{bet}** 円必要、所持金は **{current_money}** 円",
            ephemeral=True
        )
        return

    # ゲームロジック
    bot_choice, result = MiniGames.rock_paper_scissors(選択.value)

    emoji_map = {
        'はさみ': '✂️',
        'いわ': '🪨',
        'かみ': '📄'
    }

    MoneySystem.get_stats(user_id)['games_played'] += 1

    if result == 'win':
        MoneySystem.add_money(user_id, reward)
        MoneySystem.get_stats(user_id)['games_won'] += 1
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🎉 **あなたの勝ち！**\n"
            f"あなた：{emoji_map[選択.value]} {選択.value}\n"
            f"ボット：{emoji_map[bot_choice]} {bot_choice}\n"
            f"💰 獲得：**{reward}** 円\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )
    elif result == 'lose':
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"💀 **あなたの負け！**\n"
            f"あなた：{emoji_map[選択.value]} {選択.value}\n"
            f"ボット：{emoji_map[bot_choice]} {bot_choice}\n"
            f"💸 損失：**{bet}** 円\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )
    else:
        MoneySystem.add_money(user_id, bet)  # 賭け金を返す
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🤝 **引き分け！**\n"
            f"あなた：{emoji_map[選択.value]} {選択.value}\n"
            f"ボット：{emoji_map[bot_choice]} {bot_choice}\n"
            f"💰 賭け金返還：**{bet}** 円"
        )


@bot.tree.command(name="サイコロ勝負", description="ボットとサイコロ勝負（2000円賭けて、勝てば4700円獲得）")
async def dice_game(interaction: discord.Interaction):
    """サイコロ勝負"""
    user_id = interaction.user.id
    bet = 2000
    reward = 4700

    # お金チェック
    if not MoneySystem.deduct_money(user_id, bet):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ お金が足りません！**{bet}** 円必要、所持金は **{current_money}** 円",
            ephemeral=True
        )
        return

    # ゲームロジック
    player_dice, bot_dice, result = MiniGames.dice_game()

    MoneySystem.get_stats(user_id)['games_played'] += 1

    if result == 'win':
        MoneySystem.add_money(user_id, reward)
        MoneySystem.get_stats(user_id)['games_won'] += 1
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🎉 **あなたの勝ち！**\n"
            f"🎲 あなたのサイコロ：**{player_dice}** の目\n"
            f"🎲 ボットのサイコロ：**{bot_dice}** の目\n"
            f"💰 獲得：**{reward}** 円\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )
    elif result == 'lose':
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"💀 **あなたの負け！**\n"
            f"🎲 あなたのサイコロ：**{player_dice}** の目\n"
            f"🎲 ボットのサイコロ：**{bot_dice}** の目\n"
            f"💸 損失：**{bet}** 円\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )
    else:
        MoneySystem.add_money(user_id, bet)  # 賭け金を返す
        await AchievementSystem.check_and_unlock(user_id, interaction.channel)
        await interaction.response.send_message(
            f"🤝 **引き分け！**\n"
            f"🎲 あなたのサイコロ：**{player_dice}** の目\n"
            f"🎲 ボットのサイコロ：**{bot_dice}** の目\n"
            f"💰 賭け金返還：**{bet}** 円"
        )


# ==================== 🎰 ギャンブルシステム ====================

@bot.tree.command(name="ギャンブル", description="ギャンブルで大金を稼ぐ！最低500円から")
@app_commands.describe(金額="賭ける金額")
async def gamble(interaction: discord.Interaction, 金額: int):
    """ギャンブルシステム"""

    user_id = interaction.user.id
    current_money = MoneySystem.get_money(user_id)

    # 最低金額チェック
    if current_money < 500:
        await interaction.response.send_message(
            f"❌ お金が足りません！\n"
            f"ギャンブル参加最低金額：**500** 円\n"
            f"現在の所持金：**{current_money}** 円",
            ephemeral=True
        )
        return

    # 金額チェック
    if 金額 <= 0:
        await interaction.response.send_message("❌ 金額は0より大きくなければなりません！", ephemeral=True)
        return

    if 金額 > current_money:
        await interaction.response.send_message(
            f"❌ お金が足りません！所持金：**{current_money}** 円",
            ephemeral=True
        )
        return

    # 賭け金を差し引く
    MoneySystem.deduct_money(user_id, 金額)

    # ギャンブル実行
    is_win, amount, tier = GambleSystem.gamble(user_id, 金額)

    if is_win:
        MoneySystem.add_money(user_id, amount)
        profit = amount - 金額

        await interaction.response.send_message(
            f"🎰 **{tier}**\n"
            f"💰 賭け金：**{金額}** 円\n"
            f"🎉 **勝ち！**\n"
            f"💵 獲得：**{amount}** 円（純利益 **{profit}** 円）\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )
    else:
        await interaction.response.send_message(
            f"🎰 **{tier}**\n"
            f"💰 賭け金：**{金額}** 円\n"
            f"💀 **負け！**\n"
            f"💸 損失：**{金額}** 円\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )


@bot.tree.command(name="ギャンブル詳細", description="ギャンブルシステムの倍率と勝率説明を見る")
async def gamble_info(interaction: discord.Interaction):
    """ギャンブル詳細"""
    info_message = """
🎰 **ギャンブルシステム詳細**

💰 **参加最低金額：500円**

📊 **賭け金ランクと倍率：**

**🟢 小遣い稼ぎ（1 ~ 500円）**
├ 倍率：**2倍**
├ 勝率：**60%**
└ 例：500円賭け → 勝てば1000円獲得（純利益500）

**🟡 中規模賭博（501 ~ 2000円）**
├ 倍率：**3倍**
├ 勝率：**40%**
└ 例：2000円賭け → 勝てば6000円獲得（純利益4000）

**🟠 ハイリスク賭博（2001 ~ 5000円）**
├ 倍率：**5倍**
├ 勝率：**19%**
└ 例：5000円賭け → 勝てば25000円獲得（純利益20000）

**🔴 大勝負（5001円以上）**
├ 倍率：**10倍**
├ 勝率：**10%**
└ 例：10000円賭け → 勝てば100000円獲得（純利益90000）

⚠️ **注意事項：**
- 負けると全額没収されます
- 賭け金が大きいほど、リスクも報酬も高くなります
- 無理のない範囲で、理性的なギャンブルを
"""
    await interaction.response.send_message(info_message)


# ==================== 🎲 ガチャシステム ====================

@bot.tree.command(name="単発", description="1回だけガチャを引く（120円必要）")
async def single_pull_command(interaction: discord.Interaction):
    """単発ガチャ"""
    user_id = interaction.user.id

    if not MoneySystem.deduct_money(user_id, 120):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ お金が足りません！**120** 円必要、所持金は **{current_money}** 円",
            ephemeral=True
        )
        return

    result = GachaSystem.single_pull(user_id)
    data = GachaSystem.get_user_pity(user_id)

    message_parts = [
        f"🎲 **{interaction.user.display_name} の単発結果**",
        f"💸 消費：**120** 円",
        ""
    ]

    if isinstance(result, tuple):
        if result[0] == 'gold_up':
            message_parts.append(f"🟡 **星5！**")
            message_parts.append(f"✨ **おめでとう！UPキャラ「{GachaSystem.current_up_character}」を獲得！** ({result[1]}連目)")
        elif result[0] == 'gold_off':
            message_parts.append(f"🟠 **星5！**")
            message_parts.append(f"🟠 **すり抜け {result[1]} ({result[2]}連目)...次は確定天井**")
    elif result == 'purple':
        message_parts.append(f"🟣 **星4**")
    else:
        message_parts.append(f"🔵 **星3**")

    message_parts.append("")
    message_parts.append(f"📊 前回星5から: {data['pity_count']} 連")
    message_parts.append(f"🟣 前回星4から: {data['four_star_pity']} 連")
    message_parts.append(f"💰 残金: {MoneySystem.get_money(user_id)} 円")

    if data['guarantee']:
        message_parts.append("🎯 **確定天井状態**（次の星5は必ずUP）")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="10連", description="崩壊スターレイル風10連ガチャ（1200円必要）")
async def ten_pull(interaction: discord.Interaction):
    """10連ガチャ"""
    user_id = interaction.user.id

    if not MoneySystem.deduct_money(user_id, 1200):
        current_money = MoneySystem.get_money(user_id)
        await interaction.response.send_message(
            f"❌ お金が足りません！**1200** 円必要、所持金は **{current_money}** 円",
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
        f"🎲 **{interaction.user.display_name} の10連結果**",
        f"💸 消費：**1200** 円",
        "",
        display,
        "",
        f"🔵 星3: {blue}  🟣 星4: {purple}  🟡 星5: {gold_count}",
    ]

    if gold_up_list:
        pulls_text = '、'.join([f"{p}連目" for p in gold_up_list])
        message_parts.append(f"✨ **おめでとう！UPキャラ「{GachaSystem.current_up_character}」を獲得！** ({pulls_text})")

    if gold_off_list:
        off_texts = [f"{char}({pull}連目)" for char, pull in gold_off_list]
        off_banner_text = '、'.join(off_texts)
        message_parts.append(f"🟠 **すり抜け {off_banner_text}...次は確定天井**")

    updated_data = GachaSystem.get_user_pity(user_id)
    message_parts.append(f"\n📊 前回星5から: {updated_data['pity_count']} 連")
    message_parts.append(f"🟣 前回星4から: {updated_data['four_star_pity']} 連")
    message_parts.append(f"💰 残金: {MoneySystem.get_money(user_id)} 円")

    if updated_data['guarantee']:
        message_parts.append("🎯 **確定天井状態**（次の星5は必ずUP）")

    await AchievementSystem.check_and_unlock(user_id, interaction.channel)
    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="天井確認", description="あなたのガチャ天井状態を見る")
async def check_pity(interaction: discord.Interaction):
    """天井確認"""
    user_id = interaction.user.id
    data = GachaSystem.get_user_pity(user_id)

    message = [
        f"📊 **{interaction.user.display_name} の天井状態**",
        f"",
        f"🎲 前回星5から: **{data['pity_count']}** / 90 連",
        f"🟣 前回星4から: **{data['four_star_pity']}** / 10 連",
        f"🎯 確定天井: **{'はい' if data['guarantee'] else 'いいえ'}**",
        f"",
    ]

    if data['guarantee']:
        message.append(f"✨ 次の星5は必ずUPキャラ「{GachaSystem.current_up_character}」！")
    else:
        message.append("💫 次の星5は50%確率でUP")

    if data['pity_count'] >= 73:
        message.append(f"🔥 ソフト天井圏内に突入！（73連後確率大幅上昇）")

    await interaction.response.send_message('\n'.join(message))


@bot.tree.command(name="履歴", description="あなたの星5獲得履歴を見る")
async def gacha_history(interaction: discord.Interaction):
    """履歴"""
    user_id = interaction.user.id
    data = GachaSystem.get_user_pity(user_id)
    history = data.get('history', [])

    if not history:
        await interaction.response.send_message("📝 まだ星5獲得記録がありません！", ephemeral=True)
        return

    message_parts = [
        f"📜 **{interaction.user.display_name} の星5獲得履歴**",
        ""
    ]

    for idx, (rarity_type, char_name, pull_count) in enumerate(history, 1):
        if rarity_type == '星5UP':
            message_parts.append(f"{idx}. 🟡 {char_name} ({pull_count}連目)")
        else:
            message_parts.append(f"{idx}. 🟠 {char_name} ({pull_count}連目)")

    message_parts.append("")
    message_parts.append(f"星5獲得合計: **{len(history)}** 回")

    up_count = sum(1 for r in history if r[0] == '星5UP')
    off_count = len(history) - up_count

    message_parts.append(f"UPキャラ: {up_count} 回")
    message_parts.append(f"すり抜け: {off_count} 回")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="確率説明", description="ガチャ確率上昇メカニズムの説明を見る")
async def gacha_rates(interaction: discord.Interaction):
    """確率説明"""
    explanation = """
📊 **崩壊スターレイル ガチャ確率説明**

**星5確率：**
- 基本確率：**0.6%**
- 総合確率（天井含む）：**1.6%**
- ハード天井：**90連**で必ず星5

**ソフト天井メカニズム（確率上昇）：**
- **73連目**から、毎回確率が **6%** 上昇
- 73連目：0.6% + 6% = **6.6%**
- 74連目：0.6% + 12% = **12.6%**
- 75連目：0.6% + 18% = **18.6%**
- ...このように、引くほど出やすくなります

**星4確率：**
- 基本確率：**5.1%**
- 総合確率（天井含む）：**13%**
- ハード天井：**10連**で必ず星4

**UP確率（小天井 & 確定天井）：**
- 小天井：星5を引いた時 **50%** がUPキャラ
- 確定天井：すり抜けた場合、次の星5は **100%** UPキャラ

**例：**
72連星5が出ていない場合：
→ 73連目：6.6% 出現確率
→ 74連目：12.6% 出現確率
→ 80連目：48.6% 出現確率
→ 90連目：**100%** 必ず出現（ハード天井）
"""
    await interaction.response.send_message(explanation)


@bot.tree.command(name="upキャラ", description="現在のUPガチャのキャラを見る")
async def current_up_character(interaction: discord.Interaction):
    """UPキャラを見る"""
    await interaction.response.send_message(
        f"🎯 **現在のUPキャラ：{GachaSystem.current_up_character}**"
    )


@bot.tree.command(name="天井リセット", description="あなたのガチャ記録をリセット（自分のみ使用可能）")
async def reset_pity(interaction: discord.Interaction):
    """天井リセット"""
    user_id = interaction.user.id
    if user_id in GachaSystem.user_data:
        del GachaSystem.user_data[user_id]

    await interaction.response.send_message("✅ ガチャ記録をリセットしました！", ephemeral=True)


# ==================== 🎒 アイテム管理コマンド ====================

@bot.tree.command(name="バッグを見る", description="あなたのガチャアイテム在庫を見る")
async def check_inventory(interaction: discord.Interaction):
    """バッグを見る"""
    user_id = interaction.user.id
    inventory = InventorySystem.get_inventory(user_id)
    total_value = InventorySystem.get_total_value(user_id)

    message = [
        f"🎒 **{interaction.user.display_name} のバッグ**",
        "",
        f"🔵 星3：**{inventory['blue']}** 個（単価 {InventorySystem.ITEM_PRICES['blue']} 円）",
        f"🟣 星4：**{inventory['purple']}** 個（単価 {InventorySystem.ITEM_PRICES['purple']} 円）",
        f"🟡 星5UP：**{inventory['gold_up']}** 個（単価 {InventorySystem.ITEM_PRICES['gold_up']} 円）",
        f"🟠 星5すり抜け：**{inventory['gold_off']}** 個（単価 {InventorySystem.ITEM_PRICES['gold_off']} 円）",
        "",
        f"💰 **総額：{total_value} 円**"
    ]

    await interaction.response.send_message('\n'.join(message))


@bot.tree.command(name="アイテム売却", description="ガチャアイテムを売却してお金に換える")
@app_commands.describe(
    アイテム種類="売却するアイテムの種類",
    数量="売却する数量"
)
@app_commands.choices(アイテム種類=[
    app_commands.Choice(name='🔵 星3 (30円)', value='blue'),
    app_commands.Choice(name='🟣 星4 (170円)', value='purple'),
    app_commands.Choice(name='🟡 星5UP (2600円)', value='gold_up'),
    app_commands.Choice(name='🟠 星5すり抜け (2000円)', value='gold_off'),
])
async def sell_item(interaction: discord.Interaction, アイテム種類: app_commands.Choice[str], 数量: int):
    """アイテム売却"""
    user_id = interaction.user.id
    item_type = アイテム種類.value

    if 数量 <= 0:
        await interaction.response.send_message("❌ 数量は0より大きくなければなりません！", ephemeral=True)
        return

    inventory = InventorySystem.get_inventory(user_id)
    current_count = inventory.get(item_type, 0)

    if current_count < 数量:
        await interaction.response.send_message(
            f"❌ アイテム数量が足りません！\n"
            f"所持数：**{current_count}** 個\n"
            f"必要数：**{数量}** 個",
            ephemeral=True
        )
        return

    # 売却実行
    success, total_earned = InventorySystem.sell_item(user_id, item_type, 数量)

    if success:
        item_name_map = {
            'blue': '🔵 星3',
            'purple': '🟣 星4',
            'gold_up': '🟡 星5UP',
            'gold_off': '🟠 星5すり抜け'
        }

        await interaction.response.send_message(
            f"✅ **売却成功！**\n"
            f"アイテム：{item_name_map[item_type]}\n"
            f"数量：**{数量}** 個\n"
            f"💰 獲得：**{total_earned}** 円\n"
            f"現在のお金：**{MoneySystem.get_money(user_id)}** 円"
        )
    else:
        await interaction.response.send_message("❌ 売却失敗！", ephemeral=True)


@bot.tree.command(name="一括売却", description="指定したレアリティのアイテムを全て一括売却")
@app_commands.describe(レアリティ="売却するレアリティ")
@app_commands.choices(レアリティ=[
    app_commands.Choice(name='🔵 星3全て', value='blue'),
    app_commands.Choice(name='🟣 星4全て', value='purple'),
    app_commands.Choice(name='🟠 星5すり抜け全て', value='gold_off'),
    app_commands.Choice(name='💎 星3+星4全て', value='blue_purple'),
    app_commands.Choice(name='🗑️ 全アイテム', value='all'),
])
async def sell_all(interaction: discord.Interaction, レアリティ: app_commands.Choice[str]):
    """一括売却"""
    user_id = interaction.user.id
    inventory = InventorySystem.get_inventory(user_id)

    total_earned = 0
    sold_items = []

    if レアリティ.value == 'all':
        # 全て売却
        for item_type in ['blue', 'purple', 'gold_off', 'gold_up']:
            count = inventory[item_type]
            if count > 0:
                success, earned = InventorySystem.sell_item(user_id, item_type, count)
                if success:
                    total_earned += earned
                    sold_items.append((item_type, count, earned))

    elif レアリティ.value == 'blue_purple':
        # 星3+星4売却
        for item_type in ['blue', 'purple']:
            count = inventory[item_type]
            if count > 0:
                success, earned = InventorySystem.sell_item(user_id, item_type, count)
                if success:
                    total_earned += earned
                    sold_items.append((item_type, count, earned))

    else:
        # 単一レアリティ売却
        item_type = レアリティ.value
        count = inventory[item_type]
        if count > 0:
            success, earned = InventorySystem.sell_item(user_id, item_type, count)
            if success:
                total_earned += earned
                sold_items.append((item_type, count, earned))

    if not sold_items:
        await interaction.response.send_message("❌ 売却できるアイテムがありません！", ephemeral=True)
        return

    item_name_map = {
        'blue': '🔵 星3',
        'purple': '🟣 星4',
        'gold_up': '🟡 星5UP',
        'gold_off': '🟠 星5すり抜け'
    }

    message = [
        "✅ **一括売却完了！**",
        ""
    ]

    for item_type, count, earned in sold_items:
        message.append(f"{item_name_map[item_type]}：**{count}** 個 → **{earned}** 円")

    message.append("")
    message.append(f"💰 総獲得：**{total_earned}** 円")
    message.append(f"現在のお金：**{MoneySystem.get_money(user_id)}** 円")

    await interaction.response.send_message('\n'.join(message))

# ==================== 📊 統計とランキング ====================

@bot.tree.command(name="個人統計", description="あなたの個人統計パネルを見る")
async def personal_stats(interaction: discord.Interaction):
    """個人統計パネル"""
    user_id = interaction.user.id
    stats = MoneySystem.get_stats(user_id)
    gacha_stats = GachaSystem.get_gacha_stats(user_id)

    # ギャンブル勝率計算
    total_gambles = stats['gamble_wins'] + stats['gamble_losses']
    gamble_win_rate = (stats['gamble_wins'] / total_gambles * 100) if total_gambles > 0 else 0

    # ゲーム勝率計算
    games_win_rate = (stats['games_won'] / stats['games_played'] * 100) if stats['games_played'] > 0 else 0

    # 純利益計算
    net_profit = stats['total_earned'] - stats['total_spent']

    message = f"""
📊 **{interaction.user.display_name} の統計パネル**

💰 **お金統計：**
├ 現在のお金：**{MoneySystem.get_money(user_id)}** 円
├ 総獲得：**{stats['total_earned']}** 円
├ 総消費：**{stats['total_spent']}** 円
└ 純利益：**{net_profit}** 円

🎰 **ギャンブル統計：**
├ 総試合数：**{total_gambles}** 試合
├ 勝利：**{stats['gamble_wins']}** 試合
├ 敗北：**{stats['gamble_losses']}** 試合
├ 勝率：**{gamble_win_rate:.1f}%**
├ 総獲得：**{stats['gamble_total_won']}** 円
└ 総損失：**{stats['gamble_total_lost']}** 円

🎮 **ミニゲーム統計：**
├ プレイ回数：**{stats['games_played']}** 回
├ 勝利回数：**{stats['games_won']}** 回
└ 勝率：**{games_win_rate:.1f}%**

🎲 **ガチャ統計：**
├ 総ガチャ回数：**{gacha_stats['total_pulls']}** 回
├ 星5数：**{gacha_stats['five_star_count']}** 個
├ 出現率：**{gacha_stats['five_star_rate']:.2f}%**
├ UPキャラ：**{gacha_stats['up_count']}** 個
└ UP率：**{gacha_stats['up_rate']:.1f}%**

💸 **送金統計：**
├ 送金額：**{stats['transfer_sent']}** 円
└ 受取額：**{stats['transfer_received']}** 円
"""

    await interaction.response.send_message(message)


@bot.tree.command(name="お金ランキング", description="お金ランキングトップ10を見る")
async def money_leaderboard(interaction: discord.Interaction):
    """お金ランキング"""
    leaderboard = LeaderboardSystem.get_money_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 まだランキングデータがありません！", ephemeral=True)
        return

    message_parts = [
        "🏆 **お金ランキング Top 10**",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, money) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        message_parts.append(f"{medal} **{name}**: {money:,} 円")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="ガチャランキング", description="ガチャ回数ランキングトップ10を見る")
async def gacha_leaderboard(interaction: discord.Interaction):
    """ガチャランキング"""
    leaderboard = LeaderboardSystem.get_gacha_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 まだランキングデータがありません！", ephemeral=True)
        return

    message_parts = [
        "🎲 **ガチャ回数ランキング Top 10**",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, pulls) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        message_parts.append(f"{medal} **{name}**: {pulls} 回")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="ギャンブル神ランキング", description="ギャンブル最高利益ランキングトップ10を見る")
async def gamble_leaderboard(interaction: discord.Interaction):
    """ギャンブル神ランキング"""
    leaderboard = LeaderboardSystem.get_gamble_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 まだランキングデータがありません！", ephemeral=True)
        return

    message_parts = [
        "🎰 **ギャンブル神ランキング Top 10**",
        "（総獲得 - 総損失）",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, profit) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        sign = "+" if profit >= 0 else ""
        message_parts.append(f"{medal} **{name}**: {sign}{profit:,} 円")

    await interaction.response.send_message('\n'.join(message_parts))


# ==================== 🎉 その他エンタメ機能 ====================

@bot.tree.command(name="くじ引き", description="あなたの運を試す")
async def lottery(interaction: discord.Interaction):
    """くじ引き"""
    results = [
        ("💀", "終わった (50%)", ["スキル不足", "負け犬", "L", "笑える", "かわいそう", "それだけ？", "ゴミ", "ダメ", "雑魚", "弱すぎ"]),
        ("🗿", "普通にダメ (30%)", ["まあまあ", "普通", "mid", "何もない", "そんなもん", "一般的", "つまらない", "無感"]),
        ("😑", "かろうじて及第点 (10%)", ["まあいいか", "まあまあ", "まあまあかな", "頑張って", "そこそこ", "まあまあ"]),
        ("👌", "良い (5%)", ["いいよ", "まあまあだね", "及第点", "ちょっとやるね", "まあまあ", "OK"]),
        ("✨", "小勝ち (3%)", ["おめでとう", "運が良い", "いいね", "実力あり", "いいね"]),
        ("🎉", "勝った (1.5%)", ["おめでとう！", "ヨーロッパ人", "運が良いね", "大当たり", "本当に良い", "すごい"]),
        ("💎", "大当たり (0.4%)", ["大当たり！！", "運の神", "神すぎ", "運気爆発", "勝ち確", "運が爆発"]),
        ("👑", "超大当たり (0.08%)", ["超ラッキー！", "運気が逆転", "チート級", "やばすぎ", "神", "この運気は何"]),
        ("🌟", "伝説級 (0.02%)", ["伝説降臨！！！", "ありえない", "チート", "宝くじ買え", "ロト買って", "WTF"]),
    ]

    weights = [50, 30, 10, 5, 3, 1.5, 0.4, 0.08, 0.02]
    chosen = random.choices(results, weights=weights)[0]

    emoji, title, messages = chosen
    message = random.choice(messages)

    extra_flame = ""
    if title in ["終わった (50%)", "普通にダメ (30%)", "かろうじて及第点 (10%)"]:
        if random.random() < 0.3:
            flames = ["cope", "L", "💀", "🤡", "スキル不足", "笑える"]
            extra_flame = f" {random.choice(flames)}"

    result_text = f"{emoji} **{title}**\n{message}{extra_flame}"

    await interaction.response.send_message(result_text)


# ==================== 🔥 炎エフェクトシステム ====================

@bot.tree.command(name="fire", description="ユーザーのアバターに炎エフェクトを追加")
@app_commands.describe(
    user="炎エフェクトを追加するユーザーを選択（デフォルトは自分）",
    format="出力形式（デフォルトはGIF）",
    low_quality="超低品質を使用するか（ファイルサイズが小さくなる）"
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
    """炎エフェクト"""
    await interaction.response.defer()

    target_user = user or interaction.user
    output_format = format.value if format else 'gif'
    ext = '.gif' if output_format == 'gif' else '.mp4'

    avatar_path = FFmpegComposer.create_temp_path('.png')
    output_path = FFmpegComposer.create_temp_path(ext)

    try:
        if not os.path.exists(FOREGROUND_VIDEO):
            await interaction.followup.send(
                f"❌ 炎動画ファイルが見つかりません：`{FOREGROUND_VIDEO}`\n"
                f"ファイルがbotディレクトリに存在することを確認してください。"
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
                f"❌ ファイルが大きすぎます ({file_size / (1024 * 1024):.1f}MB)！\n"
                f"以下を試してください：\n"
                f"• `low_quality=True` パラメータを使用\n"
                f"• 炎動画の長さを短縮\n"
                f"• MP4形式を選択（通常GIFより小さい）"
            )
            return

        # ===== 🆕 炎エフェクト使用回数を追跡 =====
        tracking = AchievementSystem.get_user_tracking(interaction.user.id)
        tracking['fire_usage'] += 1

        # 実績チェック
        await AchievementSystem.check_and_unlock(interaction.user.id, interaction.channel)
        # ======================================

        quality_text = "（超低品質）" if low_quality else ""
        file = discord.File(output_path, filename=f'fire{ext}')
        await interaction.followup.send(
            f"🔥 **{target_user.mention} 完了！**{quality_text}\n",
            file=file
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        await interaction.followup.send(
            f"❌ FFmpeg処理エラー：\n```\n{error_msg[:1000]}\n```\n"
            f"FFmpegが正しくインストールされていることを確認してください。"
        )
        print(f"FFmpegエラー詳細：{error_msg}")

    except Exception as e:
        await interaction.followup.send(f"❌ エラーが発生しました：{str(e)}")
        print(f"エラー詳細：{e}")
        import traceback
        traceback.print_exc()

    finally:
        cleanup_files(avatar_path, output_path)


import yt_dlp
from discord import FFmpegPCMAudio
# ==================== 🎵 音楽再生システム ====================
class MusicPlayer:
    """音楽再生システム"""
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

    # 検索専用設定 (高速、タイトルのみ取得)
    YDL_SEARCH_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,  # キー：情報のみ取得、ストリーム解析なし、速度10倍
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
        """完全な動画情報を取得（再生用）"""
        try:
            with yt_dlp.YoutubeDL(cls.YDL_OPTIONS) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(query, download=False)
                )
                if 'entries' in info:
                    info = info['entries'][0]
                return info
        except Exception as e:
            print(f"❌ 動画取得失敗: {e}")
            return None

    @classmethod
    async def search_candidates(cls, query: str, amount: int = 5) -> list:
        """🆕 候補動画を検索（インタラクティブメニュー用）"""
        try:
            with yt_dlp.YoutubeDL(cls.YDL_SEARCH_OPTIONS) as ydl:
                results = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch{amount}:{query}", download=False)
                )
            if not results or 'entries' not in results:
                return []
            return [e for e in results['entries'] if e]
        except Exception as e:
            print(f"❌ 候補検索失敗: {e}")
            return []

    @classmethod
    async def search_next_recommendation(cls, guild_id: int):
        """アルゴリズム更新：「チャンネル名 (Uploader)」に基づいて次の曲を検索"""
        state = cls.get_guild_state(guild_id)
        current = state.get('current')
        if not current: return

        # === コア修正：チャンネル名を主な検索基準として使用 ===
        uploader = current.get('uploader', '')
        title = current.get('title', '')

        # チャンネル名があれば、"{チャンネル名} music"で検索
        # チャンネル名がなければ、タイトルで検索
        if uploader:
            query = f"{uploader} music"
        else:
            # 代替案：uploaderが取得できない場合、タイトルから括弧内を削除して検索
            import re
            clean_title = re.sub(r'[\(\[].*?[\)\]]', '', title).strip()
            query = f"{clean_title} music"

        print(f"🔍 自動再生検索 (チャンネル基準): {query}")

        try:
            # extract_flat=True を使用して検索速度を向上
            with yt_dlp.YoutubeDL(cls.YDL_SEARCH_OPTIONS) as ydl:
                results = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch10:{query}", download=False)
                )

            if not results or 'entries' not in results: return

            candidates = []
            # 再生履歴と現在の曲IDを取得、重複再生を避ける
            played_ids = set(state['play_history'])
            if current.get('id'):
                played_ids.add(current.get('id'))

            import difflib
            for entry in results['entries']:
                if not entry: continue
                video_id = entry.get('id')
                video_title = entry.get('title')

                # フィルター 1: 既に再生済み
                if video_id in played_ids: continue

                # フィルター 2: タイトルが似すぎている (同じ曲の別バージョンを避ける)
                if difflib.SequenceMatcher(None, title, video_title).ratio() > 0.85: continue

                # 🆕 フィルター 3: 10分（600秒）を超える場合はスキップ
                if entry.get('duration', 0) > 600: continue

                candidates.append(entry)

            if candidates:
                # 候補リストからランダムに1曲選択、ランダム性を向上
                suggestion = random.choice(candidates)
                state['next_suggestion'] = suggestion

                if state['text_channel']:
                    embed = discord.Embed(
                        description=f" **自動おすすめ：** 次は **{suggestion['title']}** を再生します",
                        color=discord.Color.teal()
                    )
                    await state['text_channel'].send(embed=embed)
            else:
                print("⚠️ 適切なおすすめ曲が見つかりません")

        except Exception as e:
            print(f"❌ おすすめ失敗: {e}")

    @classmethod
    async def play_next(cls, guild_id: int, voice_client, text_channel=None):
        """次の曲を再生するロジック"""
        state = cls.get_guild_state(guild_id)

        # 1. 履歴を記録
        if state['current']:
            state['play_history'].append(state['current']['id'])
            if len(state['play_history']) > 50: state['play_history'].pop(0)

        # 2. シングルループ
        if state['loop'] and state['current']:
            info = await cls.get_video_info(state['current']['webpage_url'])
            if info: cls._play_audio(guild_id, voice_client, info)
            return

        # 3. キュー再生
        if state['queue']:
            next_song = state['queue'].pop(0)
            state['current'] = next_song
            state['next_suggestion'] = None
            cls._play_audio(guild_id, voice_client, next_song)

            if not state['queue'] and state['auto_play']:
                asyncio.create_task(cls.search_next_recommendation(guild_id))
            return

        # 4. 自動再生
        if state['auto_play']:
            if state['next_suggestion']:
                # 完全な情報を取得 (flat infoは再生できないため)
                full_info = await cls.get_video_info(state['next_suggestion']['url'])
                if full_info:
                    state['current'] = full_info
                    state['next_suggestion'] = None
                    cls._play_audio(guild_id, voice_client, full_info)
                    asyncio.create_task(cls.search_next_recommendation(guild_id))
                    return

            # その場で計算
            await cls.search_next_recommendation(guild_id)
            if state['next_suggestion']:
                await cls.play_next(guild_id, voice_client, text_channel)
            else:
                state['current'] = None
        else:
            state['current'] = None

    @classmethod
    def _play_audio(cls, guild_id, voice_client, info):
        """低レベル再生 + 絵文字ステータス表示の修正"""
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

            # 🆕 通知UI最適化
            if state['text_channel']:
                # 時間表示処理
                duration_seconds = info.get('duration', 0)
                m, s = divmod(duration_seconds, 60)
                duration_str = f"{m:02d}:{s:02d}"

                embed = discord.Embed(
                    title="🎵 再生中",
                    description=f"**[{info['title']}]({info['webpage_url']})**",
                    color=discord.Color.from_rgb(255, 105, 180)  # ピンク系
                )

                if info.get('thumbnail'):
                    embed.set_thumbnail(url=info['thumbnail'])

                embed.add_field(name="🎤 チャンネル/アーティスト", value=info.get('uploader', '不明'), inline=True)
                embed.add_field(name="⏱️ 時間", value=duration_str, inline=True)

                # === コア修正：ステータス絵文字表示 ===
                status_parts = []

                # シングルループチェック
                if state['loop']:
                    status_parts.append("🔂 シングルループ中")

                # 自動再生チェック
                if state['auto_play']:
                    status_parts.append("🤖 自動再生ON")

                # キューチェック
                queue_len = len(state['queue'])
                if queue_len > 0:
                    status_parts.append(f"📝 あと {queue_len} 曲")

                # Footer テキスト組み合わせ
                footer_text = " | ".join(status_parts) if status_parts else "▶️ 通常再生"

                # Footer icon 設定 (オプション、ここではボットアバターまたは空白)
                embed.set_footer(text=footer_text, icon_url="https://i.imgur.com/5Nal4Iq.png")

                asyncio.run_coroutine_threadsafe(
                    state['text_channel'].send(embed=embed),
                    voice_client.loop
                )
        except Exception as e:
            print(f"再生エラー: {e}")
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
    株取引システム
    - 複数の株式選択可能
    - 価格は毎分変動
    - 買い/売りサポート
    - ポートフォリオ管理
    - 株価チャート
    """

    # 株式プール - 自由に追加可能
    STOCKS = {
        'AAPL': {'name': '知道コイン(5%)', 'base_price': 1000, 'volatility': 0.05},  # 変動率5%
        'TSLA': {'name': '17コイン(8%)', 'base_price': 800, 'volatility': 0.08},  # 変動率8%
        'NVDA': {'name': 'サンドバッグコイン(7%)', 'base_price': 1200, 'volatility': 0.07},
        'GOOG': {'name': '猛攻コイン(4%)', 'base_price': 900, 'volatility': 0.04},
        'MSFT': {'name': '夜露コイン(5%)', 'base_price': 1100, 'volatility': 0.05},
        'MEME': {'name': 'マリーコイン(15%)', 'base_price': 100, 'volatility': 0.15},  # ハイリスク・ハイリターン
    }

    # 現在の株価 {株式コード: 現在価格}
    current_prices: Dict[str, float] = {}

    # 価格履歴記録 {株式コード: [価格リスト]}
    price_history: Dict[str, List[float]] = {}

    # ユーザー保有株 {user_id: {株式コード: 数量}}
    user_holdings: Dict[int, Dict[str, int]] = {}

    # ユーザー取引記録 {user_id: [取引記録]}
    trade_history: Dict[int, List[dict]] = {}

    # 価格更新タスク
    price_update_task = None

    @classmethod
    def initialize(cls):
        """株価を初期化"""
        for symbol, data in cls.STOCKS.items():
            cls.current_prices[symbol] = data['base_price']
            cls.price_history[symbol] = [data['base_price']]
        print("✅ 株式システム初期化完了")

    @classmethod
    def update_prices(cls):
        """全株価を更新"""
        for symbol, data in cls.STOCKS.items():
            current = cls.current_prices[symbol]
            volatility = data['volatility']

            # ランダム変動 (-volatility% ~ +volatility%)
            change_percent = random.uniform(-volatility, volatility)
            new_price = current * (1 + change_percent)

            # 価格下限設定（基準価格の20%未満にはならない）
            min_price = data['base_price'] * 0.2
            new_price = max(new_price, min_price)

            # 価格更新
            cls.current_prices[symbol] = round(new_price, 2)

            # 履歴記録（最大60件保持）
            cls.price_history[symbol].append(new_price)
            if len(cls.price_history[symbol]) > 60:
                cls.price_history[symbol].pop(0)

    @classmethod
    def get_user_holdings(cls, user_id: int) -> Dict[str, int]:
        """ユーザーの保有株を取得"""
        if user_id not in cls.user_holdings:
            cls.user_holdings[user_id] = {}
        return cls.user_holdings[user_id]

    @classmethod
    def buy_stock(cls, user_id: int, symbol: str, quantity: int) -> Tuple[bool, str, int]:
        """
        株を購入
        戻り値：(成功したか, メッセージ, 消費金額)
        """
        if symbol not in cls.STOCKS:
            return False, "❌ 株式コードが存在しません！", 0

        if quantity <= 0:
            return False, "❌ 購入数量は0より大きくなければなりません！", 0

        # コスト計算（1% 手数料含む）
        price = cls.current_prices[symbol]
        cost = int(price * quantity * 1.01)

        # お金チェック
        if not MoneySystem.deduct_money(user_id, cost):
            return False, f"❌ お金が足りません！{cost} 円必要", 0

        # 保有株追加
        holdings = cls.get_user_holdings(user_id)
        holdings[symbol] = holdings.get(symbol, 0) + quantity

        # 取引記録
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

        return True, f"✅ {cls.STOCKS[symbol]['name']}({symbol}) x{quantity} 購入成功", cost

    @classmethod
    def sell_stock(cls, user_id: int, symbol: str, quantity: int) -> Tuple[bool, str, int]:
        """株を売却"""
        if symbol not in cls.STOCKS:
            return False, "❌ 株式コードが存在しません！", 0

        if quantity <= 0:
            return False, "❌ 売却数量は0より大きくなければなりません！", 0

        # 保有株チェック
        holdings = cls.get_user_holdings(user_id)
        if holdings.get(symbol, 0) < quantity:
            return False, f"❌ 保有株不足！{holdings.get(symbol, 0)} 株しかありません", 0

        # 収益計算（1% 手数料差し引き）
        price = cls.current_prices[symbol]
        revenue = int(price * quantity * 0.99)

        # ===== 🆕 利益計算（売値 - 買値）=====
        # 取引記録から最も早い購入価格を見つける
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

        # 保有株減少
        holdings[symbol] -= quantity
        if holdings[symbol] == 0:
            del holdings[symbol]

        # お金追加
        MoneySystem.add_money(user_id, revenue)

        # 取引記録
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

        return True, f"✅ {cls.STOCKS[symbol]['name']}({symbol}) x{quantity} 売却成功", revenue

    @classmethod
    def get_portfolio_value(cls, user_id: int) -> Tuple[int, Dict[str, dict]]:
        """
        ユーザーのポートフォリオ総額を計算
        戻り値：(総額, {株式コード: {数量, 現在価格, 総額}})
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
        価格推移チャート取得（ASCII）
        """
        if symbol not in cls.price_history:
            return ""

        history = cls.price_history[symbol][-periods:]
        if len(history) < 2:
            return ""

        # 最大値最小値を計算
        max_price = max(history)
        min_price = min(history)
        price_range = max_price - min_price

        if price_range == 0:
            return "価格変動なし"

        # ASCII チャート生成（5行の高さ）
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
        """株式リストを取得"""
        lines = ["📊 **取引可能株式リスト**\n"]

        for symbol, data in cls.STOCKS.items():
            current_price = cls.current_prices[symbol]
            base_price = data['base_price']

            # 変動計算
            change = current_price - base_price
            change_percent = (change / base_price) * 100

            if change > 0:
                # 上昇 = 赤色
                trend = f"🔴 +{change:.2f} (+{change_percent:.2f}%)"
            elif change < 0:
                # 下落 = 緑色
                trend = f"🟢 {change:.2f} ({change_percent:.2f}%)"
            else:
                trend = "⚪ 0.00 (0.00%)"

            lines.append(
                f"**{symbol}** - {data['name']}\n"
                f"├ 現在価格：**{current_price:.2f}** 円\n"
                f"└ {trend}\n"
            )

        return "\n".join(lines)


# ==================== 📈 株取引コマンド ====================
@bot.tree.command(name="全株式", description="全株式の概要を素早く確認")
async def all_stocks(interaction: discord.Interaction):
    """全株式概要"""
    message_parts = [
        "📊 **全株式概要**\n"
    ]

    for sym, data in StockSystem.STOCKS.items():
        current_price = StockSystem.current_prices[sym]
        base_price = data['base_price']

        # 変動計算
        change = current_price - base_price
        change_percent = (change / base_price) * 100

        # 色と記号決定
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
            f"├ 価格：**{current_price:.2f}** 円\n"
            f"└ {trend_emoji} {trend_text}\n"
        )

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="株式リスト", description="取引可能な全株式を見る")
async def stock_list(interaction: discord.Interaction):
    """株式リスト"""
    message = StockSystem.get_stock_list()
    await interaction.response.send_message(message)


@bot.tree.command(name="株式詳細", description="特定株式の詳細情報を見る")
@app_commands.describe(株式コード="株式コード（例：AAPL）")
@app_commands.choices(株式コード=[
    app_commands.Choice(name='AAPL - 知道コイン', value='AAPL'),
    app_commands.Choice(name='TSLA - 17コイン', value='TSLA'),
    app_commands.Choice(name='NVDA - サンドバッグコイン', value='NVDA'),
    app_commands.Choice(name='GOOG - 猛攻コイン', value='GOOG'),
    app_commands.Choice(name='MSFT - 夜露コイン', value='MSFT'),
    app_commands.Choice(name='MEME - マリーコイン', value='MEME'),
])
async def stock_detail(interaction: discord.Interaction, 株式コード: app_commands.Choice[str]):
    """株式詳細"""
    symbol = 株式コード.value

    if symbol not in StockSystem.STOCKS:
        await interaction.response.send_message("❌ 株式コードが存在しません！", ephemeral=True)
        return

    stock_data = StockSystem.STOCKS[symbol]
    current_price = StockSystem.current_prices[symbol]
    base_price = stock_data['base_price']

    # 変動計算
    change = current_price - base_price
    change_percent = (change / base_price) * 100

    if change > 0:
        # 上昇 = 赤色
        trend_emoji = "🔴"
        trend_text = f"+{change:.2f} (+{change_percent:.2f}%)"
    elif change < 0:
        # 下落 = 緑色
        trend_emoji = "🟢"
        trend_text = f"{change:.2f} ({change_percent:.2f}%)"
    else:
        trend_emoji = "⚪"
        trend_text = "0.00 (0.00%)"

    # 推移チャート取得
    trend_chart = StockSystem.get_price_trend(symbol, 20)

    message = f"""
📊 **{stock_data['name']} ({symbol})**

💰 **現在価格：{current_price:.2f} 円**
📍 基準価格：{base_price:.2f} 円
{trend_emoji} 変動：{trend_text}
⚡ 変動率：{stock_data['volatility'] * 100:.0f}%

📈 **最近の推移：**
```
{trend_chart}
```

💡 **取引手数料：**
├ 購入手数料：1%
└ 売却手数料：1%
"""

    await interaction.response.send_message(message)


@bot.tree.command(name="株購入", description="株を購入")
@app_commands.describe(
    株式コード="株式コード",
    数量="購入数量"
)
@app_commands.choices(株式コード=[
    app_commands.Choice(name='AAPL - 知道コイン', value='AAPL'),
    app_commands.Choice(name='TSLA - 17コイン', value='TSLA'),
    app_commands.Choice(name='NVDA - サンドバッグコイン', value='NVDA'),
    app_commands.Choice(name='GOOG - 猛攻コイン', value='GOOG'),
    app_commands.Choice(name='MSFT - 夜露コイン', value='MSFT'),
    app_commands.Choice(name='MEME - マリーコイン', value='MEME'),
])
async def buy_stock(interaction: discord.Interaction, 株式コード: app_commands.Choice[str], 数量: int):
    """株購入"""
    user_id = interaction.user.id
    symbol = 株式コード.value

    success, message, cost = StockSystem.buy_stock(user_id, symbol, 数量)

    if success:
        current_price = StockSystem.current_prices[symbol]
        current_money = MoneySystem.get_money(user_id)

        await interaction.response.send_message(
            f"{message}\n"
            f"💰 単価：**{current_price:.2f}** 円\n"
            f"💸 総支出：**{cost}** 円（1%手数料含む）\n"
            f"💵 残金：**{current_money}** 円"
        )
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="株売却", description="株を売却")
@app_commands.describe(
    株式コード="株式コード",
    数量="売却数量"
)
@app_commands.choices(株式コード=[
    app_commands.Choice(name='AAPL - 知道コイン', value='AAPL'),
    app_commands.Choice(name='TSLA - 17コイン', value='TSLA'),
    app_commands.Choice(name='NVDA - サンドバッグコイン', value='NVDA'),
    app_commands.Choice(name='GOOG - 猛攻コイン', value='GOOG'),
    app_commands.Choice(name='MSFT - 夜露コイン', value='MSFT'),
    app_commands.Choice(name='MEME - マリーコイン', value='MEME'),
])
async def sell_stock(interaction: discord.Interaction, 株式コード: app_commands.Choice[str], 数量: int):
    """株売却"""
    user_id = interaction.user.id
    symbol = 株式コード.value

    success, message, revenue = StockSystem.sell_stock(user_id, symbol, 数量)

    if success:
        current_price = StockSystem.current_prices[symbol]
        current_money = MoneySystem.get_money(user_id)

        await interaction.response.send_message(
            f"{message}\n"
            f"💰 単価：**{current_price:.2f}** 円\n"
            f"💵 獲得金額：**{revenue}** 円（1%手数料差し引き）\n"
            f"💰 現在のお金：**{current_money}** 円"
        )
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="保有株", description="あなたの保有株を見る")
async def my_portfolio(interaction: discord.Interaction):
    """保有株"""
    user_id = interaction.user.id

    total_value, details = StockSystem.get_portfolio_value(user_id)
    current_money = MoneySystem.get_money(user_id)

    if not details:
        await interaction.response.send_message(
            "📊 **あなたの保有株**\n\n"
            "現在保有株はありません\n"
            f"💰 現金：**{current_money}** 円\n"
            f"💎 総資産：**{current_money}** 円",
            ephemeral=True
        )
        return

    message_parts = [
        f"📊 **{interaction.user.display_name} の保有株**\n"
    ]

    for symbol, info in details.items():
        message_parts.append(
            f"**{symbol}** - {info['name']}\n"
            f"├ 保有数量：**{info['quantity']}** 株\n"
            f"├ 現在価格：**{info['price']:.2f}** 円\n"
            f"└ 保有額：**{info['value']}** 円\n"
        )

    total_assets = current_money + total_value

    message_parts.append(
        f"\n💰 現金：**{current_money}** 円\n"
        f"📈 株式総額：**{total_value}** 円\n"
        f"💎 総資産：**{total_assets}** 円"
    )

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="取引履歴", description="あなたの株取引履歴を見る")
async def trade_history(interaction: discord.Interaction):
    """取引履歴"""
    user_id = interaction.user.id

    if user_id not in StockSystem.trade_history or not StockSystem.trade_history[user_id]:
        await interaction.response.send_message("📝 まだ取引履歴がありません", ephemeral=True)
        return

    history = StockSystem.trade_history[user_id][-10:]  # 最近10件

    message_parts = [
        f"📝 **{interaction.user.display_name} の取引履歴**",
        "（最近10件）\n"
    ]

    for idx, trade in enumerate(reversed(history), 1):
        stock_name = StockSystem.STOCKS[trade['symbol']]['name']
        time_str = trade['time'].strftime('%m/%d %H:%M')

        if trade['type'] == 'buy':
            message_parts.append(
                f"{idx}. 📥 **購入** {stock_name}({trade['symbol']})\n"
                f"   ├ 数量：{trade['quantity']} 株\n"
                f"   ├ 単価：{trade['price']:.2f} 円\n"
                f"   ├ 支出：{trade['cost']} 円\n"
                f"   └ 時間：{time_str}\n"
            )
        else:
            message_parts.append(
                f"{idx}. 📤 **売却** {stock_name}({trade['symbol']})\n"
                f"   ├ 数量：{trade['quantity']} 株\n"
                f"   ├ 単価：{trade['price']:.2f} 円\n"
                f"   ├ 収入：{trade['revenue']} 円\n"
                f"   └ 時間：{time_str}\n"
            )

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="株式ランキング", description="株式大富豪ランキングを見る")
async def stock_leaderboard(interaction: discord.Interaction):
    """株式ランキング"""
    # 全ユーザーの総資産を計算
    rankings = []

    for user_id in StockSystem.user_holdings.keys():
        portfolio_value, _ = StockSystem.get_portfolio_value(user_id)
        cash = MoneySystem.get_money(user_id)
        total_assets = portfolio_value + cash

        rankings.append((user_id, total_assets, portfolio_value, cash))

    # ソート
    rankings.sort(key=lambda x: x[1], reverse=True)
    rankings = rankings[:10]  # トップ10

    if not rankings:
        await interaction.response.send_message("📊 まだ株取引記録がありません！", ephemeral=True)
        return

    message_parts = [
        "🏆 **株式大富豪ランキング Top 10**",
        ""
    ]

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, total, stocks, cash) in enumerate(rankings, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."

        message_parts.append(
            f"{medal} **{name}**\n"
            f"   💎 総資産：{total:,} 円\n"
            f"   📈 株式：{stocks:,} 円\n"
            f"   💰 現金：{cash:,} 円\n"
        )

    await interaction.response.send_message('\n'.join(message_parts))


# ==================== 📈 株価更新システム ====================

async def update_stock_prices():
    """毎分株価を更新"""
    await bot.wait_until_ready()

    while not bot.is_closed():
        StockSystem.update_prices()
        print("📊 株価更新完了")
        await asyncio.sleep(60)  # 60秒ごとに更新


# ==================== 🎵 音楽コマンド（更新版）====================

@bot.tree.command(name="参加", description="ボットをあなたのボイスチャンネルに参加させる")
async def join_voice(interaction: discord.Interaction):
    """ボイスチャンネルに参加"""
    # ユーザーがボイスチャンネルにいるかチェック
    if not interaction.user.voice:
        await interaction.response.send_message("❌ 先にボイスチャンネルに参加してください！", ephemeral=True)
        return

    # ボットが既にボイスチャンネルにいるかチェック
    voice_client = interaction.guild.voice_client

    # ボットが既に別のチャンネルにいる場合
    if voice_client and voice_client.is_connected():
        # 同じチャンネルかチェック
        if voice_client.channel == interaction.user.voice.channel:
            await interaction.response.send_message(
                "✅ ボットは既にこのボイスチャンネルにいます！",
                ephemeral=True
            )
            return
        else:
            # 新しいチャンネルに移動
            await voice_client.move_to(interaction.user.voice.channel)
            await interaction.response.send_message(
                f"🔄 **{interaction.user.voice.channel.name}** に移動しました"
            )
            return

    # ボイスチャンネルに参加
    try:
        voice_client = await interaction.user.voice.channel.connect()

        guild_id = interaction.guild_id
        state = MusicPlayer.get_guild_state(guild_id)

        # テキストチャンネルを記録
        state['text_channel'] = interaction.channel

        # 🆕 アイドルチェックタスク開始
        if state['inactivity_task']:
            state['inactivity_task'].cancel()
        state['inactivity_task'] = bot.loop.create_task(
            MusicPlayer.check_voice_channel_empty(guild_id, voice_client)
        )

        await interaction.response.send_message(
            f"✅ **{interaction.user.voice.channel.name}** に参加しました\n"
            f"💡 `/再生 <URL>` で音楽再生を開始"
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ ボイスチャンネル参加時にエラーが発生：{str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="音楽履歴クリア", description="再生履歴を削除")
async def clear_history(interaction: discord.Interaction):
    state = MusicPlayer.get_guild_state(interaction.guild_id)
    count = len(state['play_history'])
    state['play_history'].clear()
    await interaction.response.send_message(f"✅ {count} 曲の再生履歴を削除しました")


@bot.tree.command(name="再生履歴", description="最近再生した曲を見る")
async def view_history(interaction: discord.Interaction):
    state = MusicPlayer.get_guild_state(interaction.guild_id)
    history = state['play_history'][-10:]  # 最近 10 曲

    if not history:
        await interaction.response.send_message("📝 まだ再生履歴がありません", ephemeral=True)
        return

    message = "📜 **最近の再生履歴**\n\n"
    for idx, song in enumerate(reversed(history), 1):
        message += f"{idx}. {song['title']}\n"

    await interaction.response.send_message(message)


@bot.tree.command(name="リフレッシュ", description="現在の曲の再生リンクを再取得")
async def refresh_url(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ 現在音楽を再生していません", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    if state['current']:
        voice_client.stop()  # 自動的に play_next がトリガーされます
        await interaction.response.send_message("🔄 再生リンクを再取得中...")


# ==================== 🎵 最適化された再生コマンド ====================

@bot.tree.command(name="再生", description="URLを直接貼って再生、またはキーワードで検索して選曲")
@app_commands.describe(検索="YouTube URLまたはキーワード")
async def play_music(interaction: discord.Interaction, 検索: str):
    """再生コマンド (メニューサポート)"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ 先にボイスチャンネルに参加してください！", ephemeral=True)
        return

    await interaction.response.defer()

    guild_id = interaction.guild_id
    state = MusicPlayer.get_guild_state(guild_id)
    state['text_channel'] = interaction.channel

    # ボイス接続
    voice_client = interaction.guild.voice_client
    if not voice_client:
        try:
            voice_client = await interaction.user.voice.channel.connect()
            if not state['inactivity_task']:
                state['inactivity_task'] = bot.loop.create_task(
                    MusicPlayer.check_voice_channel_empty(guild_id, voice_client)
                )
        except Exception as e:
            await interaction.followup.send(f"❌ ボイスチャンネルに参加できません: {e}")
            return
    else:
        if voice_client.channel != interaction.user.voice.channel:
            await voice_client.move_to(interaction.user.voice.channel)

    # URLかどうか判定
    target_url = ""
    is_url = 検索.startswith("http")

    if is_url:
        target_url = 検索
    else:
        # ========== キーワード検索モード ==========
        candidates = await MusicPlayer.search_candidates(検索, amount=5)

        if not candidates:
            await interaction.followup.send("❌ 関連する曲が見つかりません。")
            return

        # --- 🛠️ 修正 1: 時間フォーマット関数 ---
        def format_duration(seconds):
            if not seconds: return "??:??"
            m, s = divmod(int(seconds), 60)
            return f"{m:02d}:{s:02d}"

        # メニュー作成
        options_text = ""
        for i, video in enumerate(candidates):
            # 秒数優先で取得、extract_flat で duration_string がない問題を解決
            duration_sec = video.get('duration')
            time_str = format_duration(duration_sec)

            options_text += f"**{i + 1}.** {video['title']} `[{time_str}]`\n"

        embed = discord.Embed(
            title=f"🔎 検索結果：{検索}",
            description=f"{options_text}\n👇 **30秒以内に数字 1-{len(candidates)} を入力して選択**",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)

        # --- 🛠️ 修正 2: 入力チェック最適化 (ID比較使用) ---
        def check(m):
            return (
                    m.author.id == interaction.user.id and  # ID比較が安全
                    m.channel.id == interaction.channel_id and  # ID比較が安全
                    m.content.strip().isdigit() and  # 空白除去後数字チェック
                    1 <= int(m.content.strip()) <= len(candidates)
            )

        try:
            # interaction.client.wait_for を使用して正しいbotインスタンスを確保
            msg = await interaction.client.wait_for('message', timeout=30.0, check=check)

            choice_index = int(msg.content.strip()) - 1
            target_url = candidates[choice_index]['url']

            # ユーザーの数字メッセージ削除試行 (ボットに権限がある場合)
            try:
                await msg.delete()
            except:
                pass

            await interaction.channel.send(f"✅ 選択：**{candidates[choice_index]['title']}**", delete_after=5)

        except asyncio.TimeoutError:
            await interaction.channel.send("⏰ 選択タイムアウト、キャンセルしました。")
            return

    # ========== 正式な再生処理 (完全な情報取得) ==========
    # 元々URLの場合はここで直接使用。選択した場合は選択したURLを使用。
    info = await MusicPlayer.get_video_info(target_url)

    if not info:
        await interaction.channel.send("❌ この動画を再生できません (制限されているか読み取れません)。")
        return

    # 再生ロジックに追加
    if voice_client.is_playing():
        state['queue'].append(info)
        embed = discord.Embed(
            description=f"➕ **{info['title']}** をキューに追加 (第 {len(state['queue'])} 曲)",
            color=discord.Color.blue()
        )
        # メニューを経由していない(直接URLを貼った)場合は followup、そうでなければ channel.send
        if is_url:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.channel.send(embed=embed)
    else:
        state['current'] = info
        MusicPlayer._play_audio(guild_id, voice_client, info)

        # 直接URLを貼った場合、前で defer したので返信が必要
        if is_url:
            await interaction.followup.send("▶️ 再生準備中...")

        # 自動再生アルゴリズム起動
        if state['auto_play']:
            asyncio.create_task(MusicPlayer.search_next_recommendation(guild_id))


@bot.tree.command(name="一時停止", description="音楽を一時停止")
async def pause_music(interaction: discord.Interaction):
    """音楽一時停止"""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ 現在再生中の音楽はありません", ephemeral=True)
        return

    voice_client.pause()
    await interaction.response.send_message("⏸️ 一時停止しました")


@bot.tree.command(name="再開", description="音楽を再開")
async def resume_music(interaction: discord.Interaction):
    """再開"""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_paused():
        await interaction.response.send_message("❌ 音楽は一時停止していません", ephemeral=True)
        return

    voice_client.resume()
    await interaction.response.send_message("▶️ 再開しました")


@bot.tree.command(name="スキップ", description="現在の曲をスキップ")
async def skip_music(interaction: discord.Interaction):
    """スキップ"""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ 現在再生中の音楽はありません", ephemeral=True)
        return

    voice_client.stop()
    await interaction.response.send_message("⏭️ 現在の曲をスキップしました")


@bot.tree.command(name="停止", description="再生を停止してキューをクリア")
async def stop_music(interaction: discord.Interaction):
    """停止"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ ボットはボイスチャンネルにいません", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    state['queue'].clear()
    state['current'] = None
    state['loop'] = False
    state['auto_play'] = False
    state['next_suggestion'] = None

    voice_client.stop()
    await interaction.response.send_message("⏹️ 再生を停止してキューをクリアしました")


@bot.tree.command(name="ループ", description="シングルループのオン/オフ")
async def loop_music(interaction: discord.Interaction):
    """シングルループ"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ ボットはボイスチャンネルにいません", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    state['loop'] = not state['loop']

    status = "ON" if state['loop'] else "OFF"
    await interaction.response.send_message(f"🔁 シングルループ {status}")


# 🆕 追加：自動再生コマンド
@bot.tree.command(name="自動再生", description="関連曲の自動再生をオン/オフ")
async def auto_play(interaction: discord.Interaction):
    """自動再生"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ ボットはボイスチャンネルにいません", ephemeral=True)
        return

    state = MusicPlayer.get_guild_state(interaction.guild_id)
    state['auto_play'] = not state['auto_play']

    status = "ON" if state['auto_play'] else "OFF"

    message = f"🤖 自動再生 {status}"
    if state['auto_play']:
        message += "\n再生キューが空になると、自動的に関連曲を検索して再生します"

    await interaction.response.send_message(message)


@bot.tree.command(name="キュー", description="現在の再生キューを見る")
async def queue_music(interaction: discord.Interaction):
    """キュー確認"""
    state = MusicPlayer.get_guild_state(interaction.guild_id)

    if not state['current'] and not state['queue']:
        await interaction.response.send_message("📝 再生キューは空です", ephemeral=True)
        return

    message_parts = ["🎵 **現在の再生キュー**\n"]

    if state['current']:
        loop_indicator = " 🔁" if state['loop'] else ""
        auto_play_indicator = " 🤖" if state['auto_play'] else ""
        message_parts.append(f"▶️ **再生中：** {state['current']['title']}{loop_indicator}{auto_play_indicator}\n")

    if state['queue']:
        message_parts.append("**次：**")
        for idx, song in enumerate(state['queue'][:10], 1):
            message_parts.append(f"{idx}. {song['title']}")

        if len(state['queue']) > 10:
            message_parts.append(f"\n...あと {len(state['queue']) - 10} 曲")

    await interaction.response.send_message('\n'.join(message_parts))


@bot.tree.command(name="退出", description="ボットをボイスチャンネルから退出させる")
async def leave_voice(interaction: discord.Interaction):
    """ボイス退出"""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        await interaction.response.send_message("❌ ボットはボイスチャンネルにいません", ephemeral=True)
        return

    # アイドルチェックタスクをキャンセル
    state = MusicPlayer.get_guild_state(interaction.guild_id)
    if state['inactivity_task']:
        state['inactivity_task'].cancel()
        state['inactivity_task'] = None

    await voice_client.disconnect()

    # 状態クリア
    state['queue'].clear()
    state['current'] = None
    state['loop'] = False
    state['auto_play'] = False

    await interaction.response.send_message("👋 ボイスチャンネルから退出しました")


@bot.tree.command(name="再生中", description="現在再生中の曲情報を表示")
async def now_playing(interaction: discord.Interaction):
    """再生中"""
    state = MusicPlayer.get_guild_state(interaction.guild_id)

    if not state['current']:
        await interaction.response.send_message("❌ 現在再生中の音楽はありません", ephemeral=True)
        return

    info = state['current']
    duration_text = f"{info['duration'] // 60}:{info['duration'] % 60:02d}" if info['duration'] else "不明"

    embed = discord.Embed(
        title="🎵 再生中",
        description=f"**{info['title']}**",
        color=discord.Color.green(),
        url=info['webpage_url']
    )

    embed.add_field(name="⏱️ 長さ", value=duration_text, inline=True)
    embed.add_field(name="🔁 ループ", value="ON" if state['loop'] else "OFF", inline=True)
    embed.add_field(name="🤖 自動再生", value="ON" if state['auto_play'] else "OFF", inline=True)
    embed.add_field(name="📝 キュー内", value=f"{len(state['queue'])} 曲", inline=True)

    if info['thumbnail']:
        embed.set_thumbnail(url=info['thumbnail'])

    await interaction.response.send_message(embed=embed)


# ==================== 🛠️ 管理者コマンド ====================

@bot.tree.command(name="お金設定", description="指定ユーザーのお金を設定（管理者限定）")
@app_commands.describe(
    ユーザー="お金を設定するユーザー",
    金額="設定する金額"
)
async def set_money(interaction: discord.Interaction, ユーザー: discord.User, 金額: int):
    """管理者がお金を設定"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 管理者のみがお金を設定できます！", ephemeral=True)
        return

    if 金額 < 0:
        await interaction.response.send_message("❌ 金額は負の数にできません！", ephemeral=True)
        return

    old_money = MoneySystem.get_money(ユーザー.id)
    MoneySystem.user_money[ユーザー.id] = 金額

    await interaction.response.send_message(
        f"✅ **お金を設定しました！**\n"
        f"ユーザー：{ユーザー.mention}\n"
        f"元のお金：**{old_money}** 円\n"
        f"新しいお金：**{金額}** 円"
    )


@bot.tree.command(name="お金調整", description="指定ユーザーのお金を増減（管理者限定）")
@app_commands.describe(
    ユーザー="お金を調整するユーザー",
    金額="調整する金額（正数で増加、負数で減少）"
)
async def adjust_money(interaction: discord.Interaction, ユーザー: discord.User, 金額: int):
    """管理者がお金を調整"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 管理者のみがお金を調整できます！", ephemeral=True)
        return

    old_money = MoneySystem.get_money(ユーザー.id)
    MoneySystem.add_money(ユーザー.id, 金額)
    new_money = MoneySystem.get_money(ユーザー.id)

    action = "増加" if 金額 > 0 else "減少"

    await interaction.response.send_message(
        f"✅ **お金を{action}しました！**\n"
        f"ユーザー：{ユーザー.mention}\n"
        f"元のお金：**{old_money}** 円\n"
        f"{action}：**{abs(金額)}** 円\n"
        f"新しいお金：**{new_money}** 円"
    )


@bot.tree.command(name="upキャラ設定", description="現在のUPガチャのキャラクター名を変更（管理者限定）")
@app_commands.describe(キャラクター名="UPに設定するキャラクター名")
async def set_up_character(interaction: discord.Interaction, キャラクター名: str):
    """UPキャラクター設定"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 管理者のみがUPキャラクターを変更できます！", ephemeral=True)
        return

    old_character = GachaSystem.current_up_character
    GachaSystem.current_up_character = キャラクター名

    await interaction.response.send_message(
        f"✅ **UPキャラクターを変更しました！**\n"
        f"「{old_character}」→「{キャラクター名}」"
    )

# ==================== 🔫 強盗システム ====================

class RobberySystem:
    """
    強盗システム (クールダウン、確率計算を含む)
    """
    cooldowns: Dict[int, datetime] = {}
    ROB_COOLDOWN = 180  # クールダウン時間 3分 (180秒)

    @classmethod
    def check_cooldown(cls, user_id: int) -> Optional[int]:
        """クールダウン時間をチェック、残り秒数を返す"""
        if user_id not in cls.cooldowns:
            return None
        elapsed = (datetime.now() - cls.cooldowns[user_id]).total_seconds()
        remaining = cls.ROB_COOLDOWN - elapsed
        if remaining <= 0:
            return None
        return int(remaining)

    @classmethod
    def set_cooldown(cls, user_id: int):
        """クールダウン時間を設定"""
        cls.cooldowns[user_id] = datetime.now()

    @staticmethod
    def calculate_odds(amount: int) -> Tuple[float, float]:
        """
        強盗の確率を計算
        戻り値：(成功率, 捕獲率)
        """
        base_success = 40.0
        base_caught = 50.0

        # 難易度係数：金額が大きいほど難しい
        difficulty = amount / 2000

        success_rate = base_success - difficulty
        caught_rate = base_caught + difficulty

        # 確率範囲を制限
        success_rate = max(5.0, min(90.0, success_rate))  # 最低5%、最高90%
        caught_rate = max(10.0, min(95.0, caught_rate))  # 最低10%、最高95%

        return success_rate, caught_rate


class RobberyView(discord.ui.View):
    """強盗確認ボタンインターフェース"""

    def __init__(self, interaction: discord.Interaction, target: discord.User, amount: int, success_rate: float,
                 caught_rate: float):
        super().__init__(timeout=30)  # 30秒以内に決定
        self.original_interaction = interaction
        self.robber = interaction.user
        self.target = target
        self.amount = amount
        self.success_rate = success_rate
        self.caught_rate = caught_rate
        self.value = None

    async def on_timeout(self):
        # タイムアウト時自動キャンセル
        for item in self.children:
            item.disabled = True
        try:
            await self.original_interaction.edit_original_response(content="⏰ 躊躇しすぎて、ターゲットは逃げました...", view=self)
        except:
            pass

    @discord.ui.button(label="🔥 実行 (確認)", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """強盗確認ボタン"""
        # 発起人かチェック
        if interaction.user.id != self.robber.id:
            await interaction.response.send_message("これはあなたの犯罪計画ではありません！", ephemeral=True)
            return

        await interaction.response.defer()  # ボタンがくるくる回るのを防ぐ

        # 二次チェック（確認期間中にお金が使われるのを防ぐ）
        target_money = MoneySystem.get_money(self.target.id)
        robber_money = MoneySystem.get_money(self.robber.id)

        if target_money < self.amount:
            await interaction.followup.send("❌ ターゲットがお金を使ってしまいました！行動キャンセル。", ephemeral=True)
            return

        # ===== 🆕 ターゲットが保護アイテムを持っているかチェック =====
        if ShopSystem.has_active_item(self.target.id, 'anti_robbery'):
            embed = discord.Embed(
                title="🛡️ 防御システム起動！",
                description=f"{self.target.mention} のハッカーコンピューターが侵入を検知、あなたは反撃されました！",
                color=discord.Color.blue()
            )
            await self.original_interaction.edit_original_response(content=None, embed=embed, view=None)
            self.stop()
            return

        # 強盗ロジック実行開始
        RobberySystem.set_cooldown(self.robber.id)

        rng = random.uniform(0, 100)

        # === 成功 ===
        if rng < self.success_rate:
            # 🆕 ターゲットが保険を持っているかチェック
            actual_loss = self.amount
            if ShopSystem.has_active_item(self.target.id, 'insurance'):
                actual_loss = int(self.amount * 0.3)  # 保険：30%のみ損失
                refund = self.amount - actual_loss
                MoneySystem.add_money(self.target.id, refund)

            # ターゲットのお金を差し引く
            MoneySystem.deduct_money(self.target.id, actual_loss)
            # 強盗がお金を獲得
            MoneySystem.add_money(self.robber.id, actual_loss)

            # 🆕 強盗成功回数を追跡 (実績用)
            tracking = AchievementSystem.get_user_tracking(self.robber.id)
            tracking['robbery_success'] += 1

            embed = discord.Embed(title="🔫 強盗成功！", color=discord.Color.green())
            embed.description = (
                f"{self.target.mention} から **{actual_loss:,}** 円を奪いました！\n"
                f"早く逃げろ！\n\n"
                f"📊 確率判定：{rng:.1f}% (必要 < {self.success_rate:.1f}%)"
            )

            # 保険がある場合、補償情報を表示
            if actual_loss < self.amount:
                refund_amount = self.amount - actual_loss
                embed.add_field(
                    name="🛡️ 保険発動",
                    value=f"{self.target.mention} の保険が {refund_amount:,} 円を補償しました",
                    inline=False
                )

            # 被害者にDM
            try:
                victim_embed = discord.Embed(
                    title="⚠️ 強盗に遭いました！",
                    description=f"**{self.robber.display_name}** があなたから **{actual_loss:,}** 円を奪いました！",
                    color=discord.Color.red()
                )
                if actual_loss < self.amount:
                    victim_embed.add_field(
                        name="🛡️ 保険請求",
                        value=f"あなたの保険が損失を軽減、実際の損失は {actual_loss:,} 円のみ",
                        inline=False
                    )
                await self.target.send(embed=victim_embed)
            except:
                pass

        # === 失敗 ===
        else:
            caught_rng = random.uniform(0, 100)

            # --- 捕まった ---
            if caught_rng < self.caught_rate:
                # 罰金額は強盗金額の30% ~ 50%
                fine_ratio = random.uniform(0.3, 0.5)
                fine = int(self.amount * fine_ratio)

                # 罰金が強盗の所持金を超えないようにする
                actual_fine = min(robber_money, fine)

                # 精神的賠償金 (罰金の半分を被害者に)
                compensation = actual_fine // 2

                MoneySystem.deduct_money(self.robber.id, actual_fine)
                MoneySystem.add_money(self.target.id, compensation)

                embed = discord.Embed(title="🚓 警察に捕まった！", color=discord.Color.red())
                embed.description = (
                    f"逃走中に転んで、警察にその場で制圧されました！\n"
                    f"💸 罰金支払い：**{actual_fine:,}** 円\n"
                    f"🤝 うち **{compensation:,}** 円を被害者に賠償\n\n"
                    f"📊 捕獲判定：{caught_rng:.1f}% (必要 < {self.caught_rate:.1f}%)"
                )

            # --- 失敗したが逃げた ---
            else:
                embed = discord.Embed(title="💨 行動失敗 (逃走)", color=discord.Color.light_grey())
                embed.description = (
                    f"相手の警戒心が高すぎて、手を出せませんでした...\n"
                    f"良いニュース：逃げ足が速かったので警察に捕まりませんでした。\n\n"
                    f"📊 運判定：強盗失敗、しかし捕獲判定は発生せず。"
                )

        # 🆕 実績チェック
        await AchievementSystem.check_and_unlock(self.robber.id, self.original_interaction.channel)

        # 元のメッセージを更新、ボタンを削除して結果を表示
        await self.original_interaction.edit_original_response(content=None, embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="🏳️ やめる (キャンセル)", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """キャンセルボタン"""
        if interaction.user.id != self.robber.id:
            await interaction.response.send_message("これはあなたの犯罪計画ではありません！", ephemeral=True)
            return

        await interaction.response.edit_message(content="❌ 犯罪計画をキャンセルしました、良い市民でいましょう。", view=None, embed=None)
        self.stop()


# ==================== 🔫 強盗コマンド ====================

@bot.tree.command(name="強盗", description="ハイリスク・ハイリターン！強盗前に確率が表示されます")
@app_commands.describe(
    対象="強盗のターゲット",
    金額="強盗を試みる金額"
)
async def rob_player(interaction: discord.Interaction, 対象: discord.User, 金額: int):
    """強盗コマンド"""
    user_id = interaction.user.id
    target_id = 対象.id

    # 1. 基本チェック
    if user_id == target_id:
        await interaction.response.send_message("❌ 自分を強盗できません！", ephemeral=True)
        return

    if 対象.bot:
        await interaction.response.send_message("❌ ボットを強盗できません！", ephemeral=True)
        return

    if 金額 <= 0:
        await interaction.response.send_message("❌ 金額は0より大きくなければなりません！", ephemeral=True)
        return

    # 2. クールダウンチェック
    remaining = RobberySystem.check_cooldown(user_id)
    if remaining:
        minutes = remaining // 60
        seconds = remaining % 60
        await interaction.response.send_message(
            f"🚓 警察がパトロール中！身を潜める必要があります。\n"
            f"残り時間：**{minutes}分 {seconds}秒**",
            ephemeral=True
        )
        return

    # 3. 財力チェック
    target_money = MoneySystem.get_money(target_id)
    if target_money < 金額:
        await interaction.response.send_message(
            f"❌ ターゲットが貧しすぎます！所持金は **{target_money:,}** 円のみ。",
            ephemeral=True
        )
        return

    robber_money = MoneySystem.get_money(user_id)
    min_fine = int(金額 * 0.1)  # 最低でも強盗金額の10%のお金が必要
    if robber_money < min_fine:
        await interaction.response.send_message(
            f"❌ 所持金が少なすぎます！\n"
            f"発生する可能性のある罰金を支払うため、最低 **{min_fine:,}** 円 (強盗金額の10%) が必要です",
            ephemeral=True
        )
        return

    # 4. 確率計算とパネル表示
    success_rate, caught_rate = RobberySystem.calculate_odds(金額)

    embed = discord.Embed(title="📋 犯罪計画書", color=discord.Color.dark_grey())
    embed.add_field(name="🔪 ターゲット", value=対象.mention, inline=True)
    embed.add_field(name="💰 強奪予定", value=f"{金額:,} 円", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)  # 空行

    # 確率に応じて色を表示
    s_emoji = "🟢" if success_rate > 50 else "🔴"
    c_emoji = "🟢" if caught_rate < 30 else "🔴"

    embed.add_field(name=f"{s_emoji} 成功率", value=f"**{success_rate:.1f}%**", inline=True)
    embed.add_field(name=f"{c_emoji} 失敗時の捕獲率", value=f"**{caught_rate:.1f}%**", inline=True)

    max_fine = int(金額 * 0.5)

    # 🆕 ターゲットが保護を持っているかチェック
    if ShopSystem.has_active_item(target_id, 'anti_robbery'):
        embed.add_field(
            name="🛡️ ターゲット状態",
            value="⚠️ ターゲットはハッカーコンピューター保護をON！",
            inline=False
        )

    if ShopSystem.has_active_item(target_id, 'insurance'):
        embed.add_field(
            name="📋 ターゲット状態",
            value="ℹ️ ターゲットは保険加入済み (30%しか奪えません)",
            inline=False
        )

    embed.set_footer(text=f"⚠️ 捕まった場合、最高罰金約 {max_fine:,} 円")

    view = RobberyView(interaction, 対象, 金額, success_rate, caught_rate)
    await interaction.response.send_message(embed=embed, view=view)


# ==================== ⚔️ デュエルシステム ====================
class DuelSystem:
    """
    デュエルシステム
    含む：攻撃、防御、クリティカル、神レベルチート
    特色：大量のランダムクリエイティブテキスト
    """

    # ==================== クリエイティブテキストライブラリ ====================

    # 1. 神レベルチート (1%) - ダメージ 9999
    GOD_TEXTS = [
        "🌌 **{attacker}** が突然宇宙の真理を悟り、**{defender}** に「天罰」を降らせた！(システム判定：即処刑)",
        "💻 **{attacker}** が開発者コンソールを開き、`/kill {defender}` と入力した...",
        "⚡ **{attacker}** がスーパーサイヤ人ブルーに変身、かめはめ波で **{defender}** を宇宙の彼方へ！",
        "😈 **{attacker}** がインフィニティガントレットを取り出し、指を鳴らした... **{defender}** は灰になった。",
        "🛑 **{attacker}** が「ザ・ワールド」で時を止め、ロードローラーを投げつけた！ **{defender}** は無抵抗！",
        "🔧 **{attacker}** がこのゲームのバグを発見、**{defender}** のHPバーを削除した。",
        "🗡️ **{attacker}** が「王の財宝」を召喚、無数の宝具が天から降り注ぐ！ **{defender}** は即死！",
        "💀 **{attacker}** がデスノートを使用、**{defender}** の名前を書き込んだ...",
        "🔥 **{attacker}** が「炎炎烈日」を発動、**{defender}** は蒸発した！",
        "❄️ **{attacker}** が「絶対零度」を使用、**{defender}** は氷の彫刻になって砕け散った！",
        "⚡ **{attacker}** が千鳥を放ち、**{defender}** の心臓を貫通！",
        "🌊 **{attacker}** が津波を召喚、**{defender}** は深海に飲み込まれ二度と浮かんでこなかった...",
        "💥 **{attacker}** がビッグバンを使用、**{defender}** は骨も残らない！",
        "🎯 **{attacker}** がオートエイムチートを起動、ヘッドショット一撃必殺！",
        "🚀 **{attacker}** が核ミサイルを発射、**{defender}** のいる都市ごと消滅...",
    ]

    # 2. クリティカル (15%) - ダメージ 30~50
    CRIT_TEXTS = [
        "🔥 **{attacker}** が **{defender}** の隙を突き、「マジ殴り」を放った！ (クリティカル)",
        "💢 **{attacker}** が元カノを思い出し、怒りを全て **{defender}** にぶつけた！ (感情ダメージクリティカル)",
        "🗡️ **{attacker}** が石中剣を抜き、**{defender}** の大動脈を一刀両断！ (致命的一撃)",
        "💣 **{attacker}** が **{defender}** の油断を突いて、股間に手榴弾を詰め込んだ！ (弱点クリティカル)",
        "🚗 **{attacker}** が異世界トラックを召喚、**{defender}** を高速で轢いた！ (転生クリティカル)",
        "🐉 **{attacker}** が青眼の白龍を召喚、滅びの爆裂疾風弾を発動！ (砕け散れ玉砕！)",
        "🧠 **{attacker}** が **{defender}** の黒歴史を暴露、巨大な精神ダメージ！ (真実ダメージ)",
        "⚔️ **{attacker}** が「抜刀術」を使用、**{defender}** は反応すらできなかった！ (先制攻撃)",
        "🦵 **{attacker}** が「無影脚」を繰り出し、**{defender}** を10メートル蹴り飛ばした！",
        "👊 **{attacker}** が「北斗百裂拳」を使用、**{defender}** はもう死んでいる！",
        "🎸 **{attacker}** が魔音を奏で、**{defender}** の鼓膜が破裂！ (音波攻撃)",
        "🔨 **{attacker}** がミョルニルを振り上げ、一撃で **{defender}** を地底に叩き込んだ！",
        "🏹 **{attacker}** が必殺の矢を放ち、**{defender}** の急所に命中！",
        "💎 **{attacker}** が「ダイヤモンドパンチ」を使用、**{defender}** の鎧が粉砕！",
        "🌪️ **{attacker}** が竜巻を召喚、**{defender}** は空に巻き上げられた！",
        "☄️ **{attacker}** が隕石を召喚、**{defender}** の頭に直撃！",
        "🦈 **{attacker}** がサメを召喚、**{defender}** の足が食いちぎられた！",
        "🕷️ **{attacker}** が猛毒クモを放ち、**{defender}** は毒に侵された！",
        "🔪 **{attacker}** が「バックスタブ」を使用、300%ダメージ！",
        "💀 **{attacker}** が「死の宣告」を使用、**{defender}** は呪われた！",
        "⚡ **{attacker}** が「雷霆万鈞」を放ち、**{defender}** は黒焦げに！",
        "🧨 **{attacker}** がC4爆薬を投げ、**{defender}** は爆風で吹き飛んだ！",
        "🎭 **{attacker}** が「幻術」を使用、**{defender}** は自分自身を攻撃した！",
        "🌙 **{attacker}** が「月読」を発動、**{defender}** は幻境で72時間拷問された！",
        "🔥 **{attacker}** が「天照」を使用、黒い炎が **{defender}** を焼き尽くした！",
    ]

    # 3. 防御/回復 (15%) - 回復 15~30
    HEAL_TEXTS = [
        "🛡️ **{attacker}** がタピオカミルクティーを取り出し、飲みながら観戦。(HP +{heal})",
        "💊 **{attacker}** がヤバいと感じて、仙豆を飲み込んだ。(HP +{heal})",
        "🧘 **{attacker}** がその場で座禅を組み、法輪功を修行し始めた。(HP +{heal})",
        "🍕 **{attacker}** がデリバリーピザを注文、お腹いっぱいになってから戦う。(HP +{heal})",
        "💉 **{attacker}** が救急キットを取り出し、絆創膏を貼った。(HP +{heal})",
        "🛡️ **{attacker}** が「絶対防御」を発動、ついでに昼寝した。(HP +{heal})",
        "✨ **{attacker}** が女神の加護を受け、聖光が傷を癒した。(HP +{heal})",
        "🍖 **{attacker}** が焼肉をかじり、体力が回復！(HP +{heal})",
        "☕ **{attacker}** がコーヒーを飲んで、元気いっぱい！(HP +{heal})",
        "🍜 **{attacker}** がラーメンを食べて、HPバーが満タンに！(HP +{heal})",
        "🧃 **{attacker}** がエナジードリンクを飲んで、活力全開！(HP +{heal})",
        "🍎 **{attacker}** がリンゴを食べて、医者が遠ざかる。(HP +{heal})",
        "🌟 **{attacker}** が回復パックを拾った、運がいい！(HP +{heal})",
        "💤 **{attacker}** が少し寝て、傷が癒えた。(HP +{heal})",
        "🔮 **{attacker}** が治療術を使用、傷口が光って治癒。(HP +{heal})",
        "🎵 **{attacker}** が癒しの音楽を聴いて、気分が良くなった。(HP +{heal})",
        "🌿 **{attacker}** が草タイプスキル「光合成」を使用。(HP +{heal})",
        "💧 **{attacker}** が聖水を一口飲み、怪我が回復。(HP +{heal})",
        "🕊️ **{attacker}** が平和の鳩を召喚、癒しの力をもたらした。(HP +{heal})",
        "🌈 **{attacker}** が虹を見て、気分が良くなり怪我が軽減。(HP +{heal})",
    ]

    # 4. 通常攻撃 (50%) - ダメージ 10~25
    NORMAL_TEXTS = [
        "⚔️ **{attacker}** が床のスリッパを拾い、**{defender}** の顔を激しく叩いた！",
        "👊 **{attacker}** が **{defender}** に通常パンチを使った。",
        "⌨️ **{attacker}** がキーボードを引き抜き、**{defender}** の頭に連打！",
        "🦵 **{attacker}** が **{defender}** の小指を蹴った！(見てるだけで痛い)",
        "🌊 **{attacker}** が **{defender}** に熱湯をぶっかけた。",
        "🎤 **{attacker}** がジャイアンの歌を歌い始め、**{defender}** の耳から血が出た。",
        "📦 **{attacker}** がレゴブロックを投げ、**{defender}** が一歩踏んだ！",
        "📱 **{attacker}** がNokia 3310で **{defender}** の額を殴った。",
        "📢 **{attacker}** が **{defender}** の耳元で「金返せ」と叫んだ！",
        "🏀 **{attacker}** がドリブル突破を使い、ついでに **{defender}** に肘打ち。",
        "🪑 **{attacker}** が椅子を持ち上げ、WWEレスラーが憑依！",
        "🥄 **{attacker}** がスプーンで **{defender}** を一すくい！",
        "🧹 **{attacker}** がほうきを持ち、**{defender}** をゴミのように掃いた！",
        "🔔 **{attacker}** が鈴を **{defender}** の耳元で鳴らし、うるさい！",
        "📚 **{attacker}** が分厚い辞書で **{defender}** の頭を殴った！",
        "🥊 **{attacker}** がストレートパンチ、**{defender}** の鼻に命中！",
        "🦶 **{attacker}** が **{defender}** の足を踏んだ、痛い！",
        "👋 **{attacker}** が **{defender}** にビンタ一発！",
        "🪛 **{attacker}** がドライバーで **{defender}** を突いた！",
        "🔨 **{attacker}** がハンマーで **{defender}** の膝を叩いた！",
        "🎯 **{attacker}** がダーツを投げ、**{defender}** の尻に刺さった！",
        "🪃 **{attacker}** がブーメランを投げ、**{defender}** の後頭部に当たった！",
        "🎱 **{attacker}** がビリヤードボールを **{defender}** に投げつけた！",
        "🏓 **{attacker}** がラケットで **{defender}** の顔を叩いた！",
        "🥍 **{attacker}** がバットで **{defender}** の頭を叩いた！",
        "🎾 **{attacker}** がサーブ、直接 **{defender}** の急所に命中！",
        "⛳ **{attacker}** がゴルフクラブを振り、**{defender}** に当たった！",
        "🏏 **{attacker}** がクリケットバットで **{defender}** を打った！",
        "🏑 **{attacker}** がホッケースティックで **{defender}** の足を払った！",
        "🥌 **{attacker}** がカーリングストーンを押し出し、**{defender}** の足の指に当たった！",
        "🎿 **{attacker}** がスキーポールで **{defender}** を突いた！",
        "🛹 **{attacker}** がスケートボードを **{defender}** の顔に投げつけた！",
        "🛼 **{attacker}** がローラースケートを履いて **{defender}** に突進！",
        "🚴 **{attacker}** が自転車で **{defender}** を撥ね飛ばした！",
        "🛴 **{attacker}** がキックボードのハンドルで **{defender}** の腹を突いた！",
        "🏍️ **{attacker}** がバイクで **{defender}** を轢いた！",
        "🚙 **{attacker}** が車で **{defender}** を撥ね飛ばした！",
        "✈️ **{attacker}** が紙飛行機で **{defender}** の目を狙った！",
        "🪁 **{attacker}** が凧で **{defender}** の首を絡めた！",
        "🎈 **{attacker}** が風船で **{defender}** の頭を叩いた、軽いけど鬱陶しい！",
        "🎀 **{attacker}** がリボンで **{defender}** の首を絞めた！",
        "🧵 **{attacker}** が糸で **{defender}** の手足を縛った！",
        "🪡 **{attacker}** が針で **{defender}** を刺した！",
        "✂️ **{attacker}** がハサミで **{defender}** の髪を切った！",
        "📌 **{attacker}** が画鋲で **{defender}** の尻を刺した！",
        "📍 **{attacker}** がピンで **{defender}** を刺した！",
        "🔗 **{attacker}** が鎖で **{defender}** を打った！",
        "🪝 **{attacker}** がフックで **{defender}** の服を引っ掛けた！",
        "🧲 **{attacker}** が磁石で **{defender}** の入れ歯を吸い取った！",
        "🔋 **{attacker}** が電池で **{defender}** を感電させた！",
        "💡 **{attacker}** が電球で **{defender}** の頭を殴った！",
    ]

    # 5. ミス (19%) - ダメージなし
    MISS_TEXTS = [
        "💨 **{attacker}** が攻撃しようとして、自分の左足で右足を引っ掛けて転んだ...",
        "📶 **{attacker}** がネット遅延 (Ping: 999ms)、攻撃無効！",
        "👀 **{attacker}** が道端の野良猫に気を取られ、攻撃を忘れた。",
        "💤 **{attacker}** が突然疲れを感じ、1ターン休むことにした。",
        "🚫 **{attacker}** の攻撃を **{defender}** が顔で受け止めた！(しかし **{defender}** の面の皮が厚すぎて無傷)",
        "🐛 **{attacker}** がバグに遭遇、スキルはクールダウン中...",
        "💃 **{attacker}** が突然ブレイクダンスを始め、攻撃機会を逃した。",
        "🎮 **{attacker}** のコントローラーが切断、サーバーに接続できない！",
        "📞 **{attacker}** のママから電話、家に帰ってご飯を食べなさいと。",
        "🦟 **{attacker}** が蚊に刺され、そこを掻いている。",
        "🌞 **{attacker}** が太陽に目が眩んで、何も見えない。",
        "💩 **{attacker}** が犬のウンチを踏んで滑って転んだ、攻撃失敗。",
        "🍌 **{attacker}** がバナナの皮を踏んで、華麗に転倒。",
        "🕳️ **{attacker}** が罠に落ちて、這い上がれない。",
        "🌧️ **{attacker}** が雨に濡れて、凍えて動けない。",
        "❄️ **{attacker}** の手が凍えて、武器を握れない。",
        "🔥 **{attacker}** が火に触れて、武器を落とした。",
        "💧 **{attacker}** が水溜まりで滑って、犬食いで転倒。",
        "🌪️ **{attacker}** が風に煽られて、攻撃が外れた。",
        "⚡ **{attacker}** が静電気でビリッとして、手が痺れた。",
        "🦅 **{attacker}** が鷹にカツラを奪われて、驚いて攻撃できない。",
        "🐝 **{attacker}** が蜂に刺されて、痛くて跳び上がった。",
        "🦂 **{attacker}** がサソリに刺されて、毒で麻痺した。",
        "🐍 **{attacker}** が蛇に驚いて、怖くて動けない。",
        "🦎 **{attacker}** がトカゲに這われて、痒くてたまらない。",
        "🐸 **{attacker}** がカエルに顔に飛びつかれて、視界が遮られた。",
        "🦗 **{attacker}** がコオロギの鳴き声で気が散った。",
        "🪰 **{attacker}** がハエに煩わされて、ずっとハエを追い払っている。",
        "🕸️ **{attacker}** がクモの巣に絡まって、身動きできない。",
        "🦇 **{attacker}** がコウモリにぶつかられて、気絶した。",
        "🐁 **{attacker}** がネズミに驚いて、跳び上がって叫んだ。",
    ]

    @staticmethod
    def draw_hp_bar(current: int, max_hp: int, length: int = 12) -> str:
        """精美なHPバーを描画"""
        current = max(0, current)
        percentage = current / max_hp
        fill = int(percentage * length)
        empty = length - fill

        # HPに応じて色を変える
        status_icon = "💚"
        if percentage < 0.5: status_icon = "💛"
        if percentage < 0.2: status_icon = "❤️"
        if current == 0: status_icon = "💀"

        bar = "█" * fill + "░" * empty
        return f"{status_icon} `[{bar}]` {current}/{max_hp}"

    @staticmethod
    async def run_duel(interaction: discord.Interaction, player: discord.User, target: discord.User):
        # 初期設定
        p1_name = player.display_name
        p2_name = target.display_name

        max_hp = 100
        hp = {player.id: max_hp, target.id: max_hp}

        # 🆕 復活装置使用追跡
        used_revive = {player.id: False, target.id: False}

        # 初期メッセージ作成
        embed = discord.Embed(
            title="⚔️ 世紀の対決開始！",
            description=f"**{p1_name}** ⚡ **{p2_name}**\n双方準備完了、試合開始！",
            color=discord.Color.red()
        )
        embed.add_field(name=f"🥊 {p1_name}", value=DuelSystem.draw_hp_bar(max_hp, max_hp), inline=True)
        embed.add_field(name=f"🥊 {p2_name}", value=DuelSystem.draw_hp_bar(max_hp, max_hp), inline=True)

        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        # 戦闘変数
        turn_count = 0

        # 先攻決定
        attacker = player if random.choice([True, False]) else target
        defender = target if attacker == player else player

        # 双方がまだHPがある間
        while True:
            turn_count += 1
            await asyncio.sleep(3.5)

            # ===== 確率と数値判定 =====
            rand = random.uniform(0, 100)
            damage = 0
            heal = 0
            action_text = ""
            current_color = discord.Color.light_grey()

            # 1. 神レベルチート (1%)
            if rand <= 1:
                damage = 9999
                template = random.choice(DuelSystem.GOD_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                current_color = discord.Color.purple()

            # 2. クリティカル (15%)
            elif rand < 16:
                damage = random.randint(30, 50)
                template = random.choice(DuelSystem.CRIT_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                action_text += f"\n💥 **{damage} ポイントのクリティカルダメージ！**"
                current_color = discord.Color.dark_red()

            # 3. 防御/回復 (15%)
            elif rand < 31:
                heal = random.randint(15, 30)
                hp[attacker.id] = min(max_hp, hp[attacker.id] + heal)
                template = random.choice(DuelSystem.HEAL_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name, heal=heal)
                current_color = discord.Color.green()

            # 4. 通常攻撃 (50%)
            elif rand < 81:
                damage = random.randint(10, 25)
                template = random.choice(DuelSystem.NORMAL_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                action_text += f"\n💢 **{damage}** ポイントのダメージを与えた。"
                current_color = discord.Color.orange()

            # 5. ミス (19%)
            else:
                template = random.choice(DuelSystem.MISS_TEXTS)
                action_text = template.format(attacker=attacker.display_name, defender=defender.display_name)
                current_color = discord.Color.blue()

            # ===== HP計算 =====
            if damage > 0:
                hp[defender.id] -= damage

            log_str = f"第 {turn_count} ターン：\n{action_text}"

            # Embed更新
            embed = discord.Embed(description=log_str, color=current_color)

            # 双方のHPバー更新
            hp1_bar = DuelSystem.draw_hp_bar(hp[player.id], max_hp)
            hp2_bar = DuelSystem.draw_hp_bar(hp[target.id], max_hp)

            embed.add_field(name=f"🥊 {p1_name}", value=hp1_bar, inline=False)
            embed.add_field(name=f"🥊 {p2_name}", value=hp2_bar, inline=False)
            embed.set_footer(text="戦闘進行中...お待ちください")

            await message.edit(embed=embed)

            # 🆕 ===== 修正：復活装置チェックロジック =====
            # HP <= 0 かつ未使用の場合のみトリガー
            if hp[player.id] <= 0 and not used_revive[player.id]:
                if ShopSystem.has_active_item(player.id, 'revive_device'):
                    ShopSystem.use_consumable(player.id, 'revive_device')
                    hp[player.id] = 50  # 50 HP で復活
                    used_revive[player.id] = True  # 使用済みマーク

                    revive_embed = discord.Embed(
                        title="⚡ 復活装置起動！",
                        description=f"**{player.display_name}** が復活装置を使用、50 HP 回復！",
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
                        title="⚡ 復活装置起動！",
                        description=f"**{target.display_name}** が復活装置を使用、50 HP 回復！",
                        color=discord.Color.blue()
                    )
                    await message.edit(embed=revive_embed)
                    await asyncio.sleep(2)

            # 本当に戦闘終了かチェック（両方とも復活済みまたは本当に死亡）
            if hp[player.id] <= 0 and used_revive[player.id]:
                break  # プレイヤー1本当に死亡
            if hp[target.id] <= 0 and used_revive[target.id]:
                break  # プレイヤー2本当に死亡
            if hp[player.id] <= 0 and not ShopSystem.has_active_item(player.id, 'revive_device'):
                break  # プレイヤー1復活装置なし
            if hp[target.id] <= 0 and not ShopSystem.has_active_item(target.id, 'revive_device'):
                break  # プレイヤー2復活装置なし

            # 攻守交代
            attacker, defender = defender, attacker

        # ===== 戦闘終了 =====
        await asyncio.sleep(1.5)

        # 勝者判定
        winner = player if hp[player.id] > 0 else target
        loser = target if winner == player else player

        winner_change, loser_change = await RankingSystem.record_match(
            winner.id,
            loser.id,
            interaction.channel
        )

        # デュエル終了メッセージ更新
        end_embed = discord.Embed(title="🏆 デュエル終了！", color=discord.Color.gold())
        end_embed.description = (
            f"👑 **勝者：{winner.mention}**\n"
            f"💀 **敗者：{loser.mention}**\n\n"
            f"これは {turn_count} ターンの激戦だった！"
        )

        # 最終HP表示
        end_embed.add_field(
            name="最終状態",
            value=f"{winner.display_name}: {max(0, hp[winner.id])} HP\n{loser.display_name}: 0 HP",
            inline=False
        )

        # ポイント変動表示
        winner_rank_info = RankingSystem.get_rank_info(winner_change['new_rank'])
        loser_rank_info = RankingSystem.get_rank_info(loser_change['new_rank'])

        points_text = (
            f"**{winner.display_name}**\n"
            f"{winner_rank_info['emoji']} {winner_rank_info['name']} | "
            f"{'+' if winner_change['points_change'] > 0 else ''}{winner_change['points_change']} ポイント\n\n"
            f"**{loser.display_name}**\n"
            f"{loser_rank_info['emoji']} {loser_rank_info['name']} | "
            f"{loser_change['points_change']} ポイント"
        )

        end_embed.add_field(name="📊 ポイント変動", value=points_text, inline=False)

        # ランダムな締めの言葉
        win_quotes = ["勝者総取り！", "実力差が歴然。", "辛勝！", "運も実力のうち。"]
        end_embed.set_footer(text=random.choice(win_quotes))

        # 実績追跡更新
        tracking = AchievementSystem.get_user_tracking(winner.id)
        tracking['duel_wins'] += 1

        await message.edit(embed=end_embed)


@bot.tree.command(name="デュエル", description="友達とランダムなターン制デュエル")
@app_commands.describe(対象="挑戦する相手")
async def duel(interaction: discord.Interaction, 対象: discord.User):
    """デュエルコマンド"""
    # 自分への挑戦チェック
    if 対象.id == interaction.user.id:
        await interaction.response.send_message("❌ 自分とは戦えません！(精神分裂になります)", ephemeral=True)
        return

    # ボットへの挑戦チェック
    if 対象.bot:
        await interaction.response.send_message("❌ ボットは無敵モードをON、勝てません。", ephemeral=True)
        return

    # デュエル実行
    await DuelSystem.run_duel(interaction, interaction.user, 対象)


# ==================== 🏆 実績システム ====================
class AchievementSystem:
    """
    実績システム
    - プレイヤーの行動を自動追跡
    - 条件達成時自動解除
    - 報酬付与
    """

    # 実績定義
    ACHIEVEMENTS = {
        'starter': {
            'name': '💼 白手起家',
            'description': '累計 10,000 円稼ぐ',
            'condition': 'total_earned',
            'target': 10000,
            'reward': 2000,
            'category': 'money'
        },
        'gacha_addict': {
            'name': '🎰 ガチャ中毒',
            'description': '100 回ガチャを引く',
            'condition': 'total_pulls',
            'target': 100,
            'reward': 10000,
            'category': 'gacha'
        },
        'social_expert': {
            'name': '💬 社交の達人',
            'description': '送金で 50,000 円使う',
            'condition': 'transfer_sent',
            'target': 50000,
            'reward': 10000,
            'category': 'social'
        },
        'billionaire': {
            'name': '💎 億万長者',
            'description': '1,000,000 円保有',
            'condition': 'current_money',
            'target': 1000000,
            'reward': 50000,
            'category': 'money'
        },
        'gacha_maniac': {
            'name': '🎲 ガチャ狂人',
            'description': '累計 1,000 回ガチャ',
            'condition': 'total_pulls',
            'target': 1000,
            'reward': 30000,
            'category': 'gacha'
        },
        'gamble_god': {
            'name': '🎰 ギャンブルの神',
            'description': 'ギャンブル 10 連勝',
            'condition': 'gamble_streak',
            'target': 10,
            'reward': 100000,
            'category': 'gamble'
        },

        # ===== 新規実績 =====
        'lucky_draw': {
            'name': '🍀 超ラッキー',
            'description': '1回の10連で星5を3個引く',
            'condition': 'ten_pull_3_gold',
            'target': 1,
            'reward': 50000,
            'category': 'gacha'
        },
        'poor_guy': {
            'name': '💸 破産専門家',
            'description': '5回破産する',
            'condition': 'bankruptcy_count',
            'target': 5,
            'reward': 20000,
            'category': 'money'
        },
        'stock_master': {
            'name': '📈 株式大富豪',
            'description': '株式総利益 500,000 円達成',
            'condition': 'stock_profit',
            'target': 500000,
            'reward': 80000,
            'category': 'stock'
        },
        'robber_king': {
            'name': '🔫 強盗王',
            'description': '強盗成功 50 回',
            'condition': 'robbery_success',
            'target': 50,
            'reward': 150000,
            'category': 'combat'
        },
        'duel_master': {
            'name': '⚔️ デュエルチャンピオン',
            'description': 'デュエル勝利 30 回',
            'condition': 'duel_wins',
            'target': 30,
            'reward': 60000,
            'category': 'combat'
        },
        'daily_login_7': {
            'name': '📅 チェックイン達人',
            'description': '連続チェックイン 7 日',
            'condition': 'checkin_streak',
            'target': 7,
            'reward': 15000,
            'category': 'daily'
        },
        'daily_login_30': {
            'name': '🔥 チェックイン狂',
            'description': '連続チェックイン 30 日',
            'condition': 'checkin_streak',
            'target': 30,
            'reward': 100000,
            'category': 'daily'
        },
        'generous': {
            'name': '🎁 慈善家',
            'description': '累計 1,000,000 円を他人に送金',
            'condition': 'transfer_sent',
            'target': 1000000,
            'reward': 200000,
            'category': 'social'
        },
        'collector': {
            'name': '🗂️ コレクター',
            'description': 'バッグに星5キャラ 100 個保有',
            'condition': 'gold_inventory',
            'target': 100,
            'reward': 120000,
            'category': 'gacha'
        },
        'fire_master': {
            'name': '🔥 炎のマスター',
            'description': '/fire コマンドを 50 回使用',
            'condition': 'fire_usage',
            'target': 50,
            'reward': 25000,
            'category': 'fun'
        },
    }

    # プレイヤー実績進捗 {user_id: {achievement_id: unlocked(bool)}}
    user_achievements: Dict[int, Dict[str, bool]] = {}

    # プレイヤー追跡データ {user_id: {stat_name: value}}
    user_tracking: Dict[int, Dict[str, int]] = {}

    @classmethod
    def get_user_achievements(cls, user_id: int) -> Dict[str, bool]:
        """プレイヤー実績状態を取得"""
        if user_id not in cls.user_achievements:
            cls.user_achievements[user_id] = {ach_id: False for ach_id in cls.ACHIEVEMENTS.keys()}
        return cls.user_achievements[user_id]

    @classmethod
    def get_user_tracking(cls, user_id: int) -> Dict[str, int]:
        """プレイヤー追跡データを取得"""
        if user_id not in cls.user_tracking:
            cls.user_tracking[user_id] = {
                'gamble_streak': 0,  # ギャンブル連勝
                'ten_pull_3_gold': 0,  # 10連3金
                'bankruptcy_count': 0,  # 破産回数
                'stock_profit': 0,  # 株利益
                'robbery_success': 0,  # 強盗成功回数
                'duel_wins': 0,  # デュエル勝利
                'fire_usage': 0,  # 炎エフェクト使用回数
            }
        return cls.user_tracking[user_id]

    @classmethod
    async def check_and_unlock(cls, user_id: int, text_channel=None) -> List[dict]:
        """
        実績をチェックして解除
        戻り値：新規解除された実績リスト
        """
        achievements = cls.get_user_achievements(user_id)
        tracking = cls.get_user_tracking(user_id)
        stats = MoneySystem.get_stats(user_id)
        gacha_data = GachaSystem.get_user_pity(user_id)
        inventory = InventorySystem.get_inventory(user_id)
        checkin_data = DailyCheckIn.get_user_data(user_id)

        newly_unlocked = []

        for ach_id, ach_data in cls.ACHIEVEMENTS.items():
            # 既に解除済みならスキップ
            if achievements[ach_id]:
                continue

            condition = ach_data['condition']
            target = ach_data['target']
            current_value = 0

            # 条件に応じて現在の進捗を取得
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

            # 条件達成
            if current_value >= target:
                achievements[ach_id] = True
                reward = ach_data['reward']
                MoneySystem.add_money(user_id, reward)

                newly_unlocked.append({
                    'name': ach_data['name'],
                    'description': ach_data['description'],
                    'reward': reward
                })

                # 通知送信
                if text_channel:
                    embed = discord.Embed(
                        title="🎉 実績解除！",
                        description=f"**{ach_data['name']}**\n{ach_data['description']}",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="💰 報酬", value=f"{reward:,} 円", inline=False)

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
        実績進捗を取得
        戻り値：(現在進捗, 目標)
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
        """解除済み実績数を取得"""
        achievements = cls.get_user_achievements(user_id)
        return sum(1 for unlocked in achievements.values() if unlocked)


# ==================== 🏪 ショップシステム ====================
class ShopSystem:
    """
    ショップシステム
    - アイテム購入
    - バフ効果管理
    - アイテム在庫
    """

    # 商品定義
    SHOP_ITEMS = {
        'gamble_boost': {
            'name': '🎰 ギャンブル神の遺産お守り',
            'price': 130000,
            'description': 'ギャンブル勝率 +15% (1時間持続)',
            'duration': 3600,  # 秒
            'type': 'buff',
            'effect': 'gamble_boost',
            'stackable': False  # スタック不可
        },
        'anti_robbery': {
            'name': '💻 ハッカーコンピューター',
            'price': 100000,
            'description': '24時間強盗不可',
            'duration': 86400,
            'type': 'protection',
            'effect': 'robbery_immune',
            'stackable': False
        },
        'revive_device': {
            'name': '⚡ 復活装置',
            'price': 100000,
            'description': 'デュエル敗北時自動復活 (使い切り消耗品)',
            'duration': None,  # 使用まで永久有効
            'type': 'consumable',
            'effect': 'auto_revive',
            'stackable': True  # 複数購入可能
        },
        'gacha_luck': {
            'name': '🍀 幸運の四つ葉',
            'price': 80000,
            'description': 'ガチャ星5確率 +3% (30分持続)',
            'duration': 1800,
            'type': 'buff',
            'effect': 'gacha_luck',
            'stackable': False
        },
        'double_money': {
            'name': '💰 財運お守り',
            'price': 50000,
            'description': '全収入2倍 (1時間持続)',
            'duration': 3600,
            'type': 'buff',
            'effect': 'double_income',
            'stackable': False
        },
        'stock_insider': {
            'name': '📊 内部情報',
            'price': 120000,
            'description': '今後10分間の株価推移を表示 (使い切り)',
            'duration': None,
            'type': 'consumable',
            'effect': 'stock_preview',
            'stackable': True
        },
        'vip_pass': {
            'name': '👑 VIP パス',
            'price': 500000,
            'description': '送金手数料無料 + チェックイン報酬 +50% (7日間持続)',
            'duration': 604800,
            'type': 'vip',
            'effect': 'vip_status',
            'stackable': False
        },
        'insurance': {
            'name': '🛡️ 保険契約',
            'price': 150000,
            'description': '強盗被害時30%のみ損失 (3日間持続)',
            'duration': 259200,
            'type': 'protection',
            'effect': 'damage_reduction',
            'stackable': False
        },
        'exp_boost': {
            'name': '📈 経験値ブースター(現在無効)',
            'price': 60000,
            'description': '全活動経験値 +100% (2時間持続)',
            'duration': 7200,
            'type': 'buff',
            'effect': 'exp_boost',
            'stackable': False
        },
        'teleport': {
            'name': '🌀 緊急転送',
            'price': 30000,
            'description': '全クールダウンを即座にリセット (使い切り)',
            'duration': None,
            'type': 'consumable',
            'effect': 'reset_cooldown',
            'stackable': True
        },
    }

    # プレイヤーアイテム在庫 {user_id: {item_id: {'quantity': int, 'expires': datetime}}}
    user_inventory: Dict[int, Dict[str, dict]] = {}

    @classmethod
    def get_user_inventory(cls, user_id: int) -> Dict[str, dict]:
        """プレイヤーのショップアイテムを取得"""
        if user_id not in cls.user_inventory:
            cls.user_inventory[user_id] = {}
        return cls.user_inventory[user_id]

    @classmethod
    def buy_item(cls, user_id: int, item_id: str) -> Tuple[bool, str]:
        """
        アイテムを購入
        戻り値：(成功したか, メッセージ)
        """
        if item_id not in cls.SHOP_ITEMS:
            return False, "❌ 商品が存在しません！"

        item = cls.SHOP_ITEMS[item_id]
        price = item['price']

        # お金チェック
        if not MoneySystem.deduct_money(user_id, price):
            current_money = MoneySystem.get_money(user_id)
            return False, f"❌ お金が足りません！{price:,} 円必要、所持金は {current_money:,} 円"

        # スタック可能かチェック
        inventory = cls.get_user_inventory(user_id)

        if item_id in inventory and not item['stackable']:
            # 期限切れかチェック
            if inventory[item_id]['expires'] and datetime.now() < inventory[item_id]['expires']:
                MoneySystem.add_money(user_id, price)  # 返金
                remaining = (inventory[item_id]['expires'] - datetime.now()).total_seconds()
                minutes = int(remaining // 60)
                return False, f"❌ 既にこのアイテムを所有しています！\n残り有効期限：{minutes} 分"

        # アイテム追加
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

        return True, f"✅ **{item['name']}** を購入しました！"

    @classmethod
    def has_active_item(cls, user_id: int, item_id: str) -> bool:
        """アイテムが有効かチェック"""
        inventory = cls.get_user_inventory(user_id)

        if item_id not in inventory:
            return False

        item_data = inventory[item_id]

        # 期限切れかチェック
        if item_data['expires'] and datetime.now() > item_data['expires']:
            del inventory[item_id]  # 期限切れアイテムを削除
            return False

        return item_data['quantity'] > 0

    @classmethod
    def use_consumable(cls, user_id: int, item_id: str) -> bool:
        """消耗品を使用"""
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
        """全有効バフを取得"""
        inventory = cls.get_user_inventory(user_id)
        active_buffs = []

        for item_id, item_data in list(inventory.items()):
            # 期限切れチェック
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

# ==================== 🏆 実績コマンド ====================

@bot.tree.command(name="マイ実績", description="あなたの実績進捗を見る")
async def my_achievements(interaction: discord.Interaction):
    """実績を見る"""
    user_id = interaction.user.id
    achievements = AchievementSystem.get_user_achievements(user_id)

    unlocked_count = AchievementSystem.get_unlocked_count(user_id)
    total_count = len(AchievementSystem.ACHIEVEMENTS)

    # カテゴリー別に整理
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

    # カテゴリー名
    cat_names = {
        'money': '💰 お金',
        'gacha': '🎲 ガチャ',
        'gamble': '🎰 ギャンブル',
        'social': '💬 社交',
        'stock': '📈 株式',
        'combat': '⚔️ 戦闘',
        'daily': '📅 チェックイン',
        'fun': '🎉 エンタメ'
    }

    embed = discord.Embed(
        title=f"🏆 {interaction.user.display_name} の実績",
        description=f"解除済み：**{unlocked_count}/{total_count}** ({unlocked_count / total_count * 100:.1f}%)",
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
                value='\n'.join(lines[:5]),  # 最大5個表示
                inline=False
            )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="実績詳細", description="特定実績の詳細情報を見る")
@app_commands.describe(実績名="実績の完全名称")
async def achievement_detail(interaction: discord.Interaction, 実績名: str):
    """実績詳細"""
    user_id = interaction.user.id

    # 実績を検索
    target_ach = None
    target_id = None

    for ach_id, ach_data in AchievementSystem.ACHIEVEMENTS.items():
        if 実績名.lower() in ach_data['name'].lower():
            target_ach = ach_data
            target_id = ach_id
            break

    if not target_ach:
        await interaction.response.send_message(f"❌ 実績「{実績名}」が見つかりません", ephemeral=True)
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
        embed.add_field(name="ステータス", value="✅ 解除済み", inline=True)
    else:
        percentage = min(100, int(current / target * 100))
        embed.add_field(name="進捗", value=f"{current}/{target} ({percentage}%)", inline=True)

    embed.add_field(name="💰 報酬", value=f"{target_ach['reward']:,} 円", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="実績ランキング", description="実績解除ランキングを見る")
async def achievement_leaderboard(interaction: discord.Interaction):
    """実績ランキング"""
    rankings = []

    for user_id in AchievementSystem.user_achievements.keys():
        count = AchievementSystem.get_unlocked_count(user_id)
        if count > 0:
            rankings.append((user_id, count))

    rankings.sort(key=lambda x: x[1], reverse=True)
    rankings = rankings[:10]

    if not rankings:
        await interaction.response.send_message("📊 まだ実績記録がありません！", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏆 実績マスターランキング Top 10",
        description="解除実績数ランキング",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, count) in enumerate(rankings, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        total = len(AchievementSystem.ACHIEVEMENTS)
        percentage = count / total * 100

        embed.add_field(
            name=f"{medal} {name}",
            value=f"**{count}/{total}** 個の実績 ({percentage:.1f}%)",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# ==================== 🏪 ショップコマンド ====================

@bot.tree.command(name="ショップ", description="ショップの全商品を見る")
async def shop(interaction: discord.Interaction):
    """ショップ"""
    embed = discord.Embed(
        title="🏪 神秘のショップ",
        description="ようこそ！ここでは各種強力アイテムを販売しています",
        color=discord.Color.blue()
    )

    # タイプ別にグループ化
    buffs = []
    protections = []
    consumables = []
    vips = []

    for item_id, item in ShopSystem.SHOP_ITEMS.items():
        price_str = f"{item['price']:,} 円"

        if item['type'] == 'buff':
            buffs.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")
        elif item['type'] == 'protection':
            protections.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")
        elif item['type'] == 'consumable':
            consumables.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")
        elif item['type'] == 'vip':
            vips.append(f"**{item['name']}** - {price_str}\n└ {item['description']}")

    if buffs:
        embed.add_field(name="⚡ バフアイテム", value='\n\n'.join(buffs), inline=False)
    if protections:
        embed.add_field(name="🛡️ 保護アイテム", value='\n\n'.join(protections), inline=False)
    if consumables:
        embed.add_field(name="💊 消耗品", value='\n\n'.join(consumables), inline=False)
    if vips:
        embed.add_field(name="👑 VIP 特典", value='\n\n'.join(vips), inline=False)

    embed.set_footer(text="/購入 <商品名> でアイテムを購入")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="購入", description="ショップアイテムを購入")
@app_commands.describe(商品名="購入する商品名")
async def buy_shop_item(interaction: discord.Interaction, 商品名: str):
    """アイテム購入"""
    user_id = interaction.user.id

    # 商品を検索
    target_item = None
    target_id = None

    for item_id, item in ShopSystem.SHOP_ITEMS.items():
        if 商品名.lower() in item['name'].lower():
            target_item = item
            target_id = item_id
            break

    if not target_item:
        await interaction.response.send_message(f"❌ 商品「{商品名}」が見つかりません", ephemeral=True)
        return

    # 購入
    success, message = ShopSystem.buy_item(user_id, target_id)

    if success:
        current_money = MoneySystem.get_money(user_id)

        embed = discord.Embed(
            title="✅ 購入成功！",
            description=f"**{target_item['name']}**\n{target_item['description']}",
            color=discord.Color.green()
        )
        embed.add_field(name="💰 消費", value=f"{target_item['price']:,} 円", inline=True)
        embed.add_field(name="💵 残金", value=f"{current_money:,} 円", inline=True)

        if target_item['duration']:
            minutes = target_item['duration'] // 60
            embed.add_field(name="⏱️ 持続時間", value=f"{minutes} 分", inline=True)

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="マイアイテム", description="所有しているショップアイテムを見る")
async def my_items(interaction: discord.Interaction):
    """マイアイテム"""
    user_id = interaction.user.id
    active_buffs = ShopSystem.get_active_buffs(user_id)

    if not active_buffs:
        await interaction.response.send_message("🎒 現在アイテムを所持していません", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🎒 {interaction.user.display_name} のアイテム",
        color=discord.Color.blue()
    )

    for buff in active_buffs:
        if 'remaining' in buff:
            remaining = buff['remaining']
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            time_str = f"{hours}時間{minutes}分" if hours > 0 else f"{minutes}分"

            embed.add_field(
                name=buff['name'],
                value=f"⏱️ 残り：{time_str}",
                inline=False
            )
        else:
            embed.add_field(
                name=buff['name'],
                value=f"📦 数量：{buff['quantity']}",
                inline=False
            )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="アイテム使用", description="消耗品アイテムを使用")
@app_commands.describe(アイテム名="使用するアイテム名")
async def use_item(interaction: discord.Interaction, アイテム名: str):
    """アイテム使用"""
    user_id = interaction.user.id

    # アイテムを検索
    target_item = None
    target_id = None

    for item_id, item in ShopSystem.SHOP_ITEMS.items():
        if アイテム名.lower() in item['name'].lower():
            target_item = item
            target_id = item_id
            break

    if not target_item:
        await interaction.response.send_message(f"❌ アイテム「{アイテム名}」が見つかりません", ephemeral=True)
        return

    # 特殊アイテム効果
    if target_id == 'reset_cooldown':
        # クールダウンクリア
        if ShopSystem.use_consumable(user_id, target_id):
            MoneySystem.earn_cooldowns.pop(user_id, None)
            RobberySystem.cooldowns.pop(user_id, None)

            await interaction.response.send_message("✅ 全クールダウンをクリアしました！")
        else:
            await interaction.response.send_message("❌ このアイテムを所持していません！", ephemeral=True)

    elif target_id == 'stock_insider':
        # 株価予測
        if ShopSystem.use_consumable(user_id, target_id):
            embed = discord.Embed(title="📊 内部情報", color=discord.Color.green())

            for symbol in StockSystem.STOCKS.keys():
                current = StockSystem.current_prices[symbol]
                # 未来価格をシミュレート
                future = current * random.uniform(0.95, 1.05)
                change = ((future - current) / current) * 100

                trend = "📈 上昇予想" if change > 0 else "📉 下落予想"
                embed.add_field(
                    name=f"{symbol} - {StockSystem.STOCKS[symbol]['name']}",
                    value=f"{trend} 予想変動：{change:+.2f}%",
                    inline=False
                )

            embed.set_footer(text="⚠️ これは予測であり、正確性は保証されません")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ このアイテムを所持していません！", ephemeral=True)

    else:
        await interaction.response.send_message("❌ このアイテムはパッシブ効果のため、手動使用不要", ephemeral=True)


class RankingSystem:
    """ランクシステム"""

    # ユーザーランクデータ {user_id: {'wins': int, 'losses': int, 'rank': str, 'points': int}}
    user_rankings: Dict[int, dict] = {}

    # ランク定義（低→高）
    RANKS = [
        {
            'id': 'bronze',
            'name': '🥉 ブロンズ',
            'emoji': '🥉',
            'min_points': 0,
            'max_points': 999,
            'color': 0xCD7F32,
            'promotion_reward': 5000
        },
        {
            'id': 'silver',
            'name': '🥈 シルバー',
            'emoji': '🥈',
            'min_points': 1000,
            'max_points': 1999,
            'color': 0xC0C0C0,
            'promotion_reward': 10000
        },
        {
            'id': 'gold',
            'name': '🥇 ゴールド',
            'emoji': '🥇',
            'min_points': 2000,
            'max_points': 2999,
            'color': 0xFFD700,
            'promotion_reward': 20000
        },
        {
            'id': 'platinum',
            'name': '💎 プラチナ',
            'emoji': '💎',
            'min_points': 3000,
            'max_points': 3999,
            'color': 0xE5E4E2,
            'promotion_reward': 35000
        },
        {
            'id': 'diamond',
            'name': '💠 ダイヤモンド',
            'emoji': '💠',
            'min_points': 4000,
            'max_points': 4999,
            'color': 0xB9F2FF,
            'promotion_reward': 50000
        },
        {
            'id': 'master',
            'name': '👑 マスター',
            'emoji': '👑',
            'min_points': 5000,
            'max_points': 5999,
            'color': 0xFF1493,
            'promotion_reward': 80000
        },
        {
            'id': 'grandmaster',
            'name': '🌟 グランドマスター',
            'emoji': '🌟',
            'min_points': 6000,
            'max_points': 7499,
            'color': 0xFF6347,
            'promotion_reward': 120000
        },
        {
            'id': 'challenger',
            'name': '⚡ チャレンジャー',
            'emoji': '⚡',
            'min_points': 7500,
            'max_points': 999999,
            'color': 0xFF0000,
            'promotion_reward': 200000
        }
    ]

    @classmethod
    def get_user_data(cls, user_id: int) -> dict:
        """ユーザーランクデータを取得"""
        if user_id not in cls.user_rankings:
            cls.user_rankings[user_id] = {
                'wins': 0,
                'losses': 0,
                'points': 0,  # ポイント
                'rank': 'bronze',
                'current_streak': 0,  # 連勝
                'best_streak': 0,  # 最高連勝
                'total_matches': 0,
                'last_match': None,
                'promotion_count': 0  # 昇格回数
            }
        return cls.user_rankings[user_id]

    @classmethod
    def get_rank_info(cls, rank_id: str) -> dict:
        """ランクIDからランク情報を取得"""
        for rank in cls.RANKS:
            if rank['id'] == rank_id:
                return rank
        return cls.RANKS[0]  # デフォルトはブロンズ

    @classmethod
    def get_rank_by_points(cls, points: int) -> dict:
        """ポイントから対応するランクを取得"""
        for rank in reversed(cls.RANKS):
            if points >= rank['min_points']:
                return rank
        return cls.RANKS[0]

    @classmethod
    def calculate_points_change(cls, winner_points: int, loser_points: int, is_winner: bool) -> int:
        """ポイント変動を計算（動的K値）"""

        # ===== 🆕 ランクに応じてK値を動的調整 =====
        def get_dynamic_k(points: int) -> int:
            if points < 1000:  # ブロンズ
                return 80  # 初心者は速くランクアップ
            elif points < 2000:  # シルバー
                return 64
            elif points < 3000:  # ゴールド
                return 48
            elif points < 4000:  # プラチナ
                return 40
            elif points < 5000:  # ダイヤモンド
                return 32
            else:  # マスター以上
                return 24  # 高ランクは変動が遅く、より安定

        # 勝者のK値を使用
        K = get_dynamic_k(winner_points if is_winner else loser_points)

        expected_winner = 1 / (1 + 10 ** ((loser_points - winner_points) / 400))
        expected_loser = 1 - expected_winner

        if is_winner:
            points_change = int(K * (1 - expected_winner))

            # ===== 🆕 連勝ボーナス =====
            winner_data = cls.get_user_data(winner_points)  # user_idを渡す必要がある
            if winner_data['current_streak'] >= 3:
                bonus = min(20, winner_data['current_streak'] * 2)  # 連勝3+ 追加ポイント
                points_change += bonus

            return max(25, min(100, points_change))
        else:
            points_change = int(K * (0 - expected_loser))

            # ===== 🆕 ランク保護（急激なランク低下を防ぐ）=====
            loser_data = cls.get_user_data(loser_points)
            loser_rank_info = cls.get_rank_by_points(loser_data['points'])

            # ランク低下しそうな場合、減点を軽減
            if loser_data['points'] - abs(points_change) < loser_rank_info['min_points']:
                points_change = int(points_change * 0.7)  # 減点を30%軽減

            return max(-80, min(-15, points_change))

    @classmethod
    async def record_match(cls, winner_id: int, loser_id: int, channel) -> Tuple[dict, dict]:
        """
        対戦結果を記録してランクを更新
        戻り値：(勝者の変化, 敗者の変化)
        """
        winner_data = cls.get_user_data(winner_id)
        loser_data = cls.get_user_data(loser_id)

        # 元のランクを記録
        old_winner_rank = winner_data['rank']
        old_loser_rank = loser_data['rank']
        old_winner_points = winner_data['points']
        old_loser_points = loser_data['points']

        # ポイント変動を計算
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

        # ポイント更新
        winner_data['points'] = max(0, winner_data['points'] + winner_points_change)
        loser_data['points'] = max(0, loser_data['points'] + loser_points_change)

        # 勝敗数更新
        winner_data['wins'] += 1
        loser_data['losses'] += 1
        winner_data['total_matches'] += 1
        loser_data['total_matches'] += 1

        # 連勝更新
        winner_data['current_streak'] += 1
        winner_data['best_streak'] = max(winner_data['best_streak'], winner_data['current_streak'])
        loser_data['current_streak'] = 0

        # 時間記録
        winner_data['last_match'] = datetime.now()
        loser_data['last_match'] = datetime.now()

        # ランク更新
        new_winner_rank_info = cls.get_rank_by_points(winner_data['points'])
        new_loser_rank_info = cls.get_rank_by_points(loser_data['points'])

        winner_data['rank'] = new_winner_rank_info['id']
        loser_data['rank'] = new_loser_rank_info['id']

        # 昇格/降格チェック
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

        # 勝者昇格チェック
        if old_winner_rank != winner_data['rank']:
            old_rank_info = cls.get_rank_info(old_winner_rank)
            new_rank_info = cls.get_rank_info(winner_data['rank'])

            if new_rank_info['min_points'] > old_rank_info['min_points']:
                winner_change['promoted'] = True
                winner_change['reward'] = new_rank_info['promotion_reward']
                winner_data['promotion_count'] += 1

                MoneySystem.add_money(winner_id, winner_change['reward'])

                # 昇格通知送信
                await cls.send_promotion_notification(channel, winner_id, new_rank_info, winner_change['reward'])

        # 敗者降格チェック
        if old_loser_rank != loser_data['rank']:
            old_rank_info = cls.get_rank_info(old_loser_rank)
            new_rank_info = cls.get_rank_info(loser_data['rank'])

            if new_rank_info['min_points'] < old_rank_info['min_points']:
                loser_change['demoted'] = True

                # 降格通知送信
                await cls.send_demotion_notification(channel, loser_id, old_rank_info, new_rank_info)

        return winner_change, loser_change

    @classmethod
    async def send_promotion_notification(cls, channel, user_id: int, rank_info: dict, reward: int):
        """昇格通知を送信"""
        try:
            user = await channel.guild.get_member(user_id) or await channel.guild.fetch_member(user_id)

            embed = discord.Embed(
                title="🎊 ランク昇格！",
                description=f"**{user.mention}** が **{rank_info['name']}** に昇格しました！",
                color=rank_info['color']
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="💰 昇格報酬", value=f"{reward:,} 円", inline=True)
            embed.add_field(name="🏆 新ランク", value=rank_info['emoji'], inline=True)
            embed.set_footer(text="さらに上のランクを目指して頑張ろう！")

            await channel.send(embed=embed)
        except Exception as e:
            print(f"昇格通知送信失敗: {e}")

    @classmethod
    async def send_demotion_notification(cls, channel, user_id: int, old_rank: dict, new_rank: dict):
        """降格通知を送信"""
        try:
            user = await channel.guild.get_member(user_id) or await channel.guild.fetch_member(user_id)

            embed = discord.Embed(
                title="📉 ランク降格",
                description=f"**{user.mention}** が **{old_rank['name']}** から **{new_rank['name']}** に降格",
                color=0x808080
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="諦めず、頑張り続けよう！")

            await channel.send(embed=embed)
        except Exception as e:
            print(f"降格通知送信失敗: {e}")

    @classmethod
    def get_rank_progress(cls, user_id: int) -> Tuple[int, int, int]:
        """
        ランク進捗を取得
        戻り値：(現在ポイント, 現在ランク最低点, 次ランク最低点)
        """
        data = cls.get_user_data(user_id)
        current_rank = cls.get_rank_info(data['rank'])

        # 次のランクを探す
        current_index = next((i for i, r in enumerate(cls.RANKS) if r['id'] == data['rank']), 0)

        if current_index < len(cls.RANKS) - 1:
            next_rank = cls.RANKS[current_index + 1]
            return data['points'], current_rank['min_points'], next_rank['min_points']
        else:
            # 既に最高ランク
            return data['points'], current_rank['min_points'], current_rank['max_points']

    @classmethod
    def get_winrate(cls, user_id: int) -> float:
        """勝率を計算"""
        data = cls.get_user_data(user_id)
        total = data['total_matches']
        if total == 0:
            return 0.0
        return (data['wins'] / total) * 100

    @classmethod
    def get_leaderboard(cls, limit: int = 10) -> list:
        """ランキングを取得"""
        rankings = [
            (user_id, data['points'], data['rank'], data['wins'], data['losses'])
            for user_id, data in cls.user_rankings.items()
        ]
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings[:limit]


@bot.tree.command(name="マイランク", description="あなたのランク情報を見る")
async def my_rank(interaction: discord.Interaction):
    """自分のランクを見る"""
    user_id = interaction.user.id
    data = RankingSystem.get_user_data(user_id)
    rank_info = RankingSystem.get_rank_info(data['rank'])

    # 勝率計算
    winrate = RankingSystem.get_winrate(user_id)

    # 進捗計算
    current_points, min_points, next_points = RankingSystem.get_rank_progress(user_id)
    progress = current_points - min_points
    needed = next_points - min_points
    percentage = (progress / needed * 100) if needed > 0 else 100

    # プログレスバー
    bar_length = 10
    filled = int(bar_length * (progress / needed)) if needed > 0 else bar_length
    bar = "█" * filled + "░" * (bar_length - filled)

    embed = discord.Embed(
        title=f"🎖️ {interaction.user.display_name} のランク",
        color=rank_info['color']
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    # ランク情報
    embed.add_field(
        name="📊 現在のランク",
        value=f"{rank_info['emoji']} **{rank_info['name']}**\nポイント：**{data['points']}** pt",
        inline=False
    )

    # プログレスバー
    if data['rank'] != 'challenger':  # 最高ランクでない
        embed.add_field(
            name="📈 昇格進捗",
            value=f"`[{bar}]` {percentage:.1f}%\n**{next_points - current_points}** pt で昇格",
            inline=False
        )
    else:
        embed.add_field(
            name="👑 最高ランク到達",
            value="あなたは既にチャレンジャーです！",
            inline=False
        )

    # 戦績
    embed.add_field(
        name="⚔️ 戦績",
        value=(
            f"総試合数：**{data['total_matches']}** 試合\n"
            f"勝利：**{data['wins']}** 試合\n"
            f"敗北：**{data['losses']}** 試合\n"
            f"勝率：**{winrate:.1f}%**"
        ),
        inline=True
    )

    # 連勝
    embed.add_field(
        name="🔥 連勝記録",
        value=(
            f"現在連勝：**{data['current_streak']}** 試合\n"
            f"最高連勝：**{data['best_streak']}** 試合"
        ),
        inline=True
    )

    # 統計
    embed.add_field(
        name="📜 その他",
        value=f"昇格回数：**{data['promotion_count']}** 回",
        inline=True
    )

    embed.set_footer(text="/デュエル でランクを上げよう！")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ランク確認", description="他のプレイヤーのランクを見る")
@app_commands.describe(プレイヤー="確認するプレイヤー")
async def check_rank(interaction: discord.Interaction, プレイヤー: discord.User):
    """他人のランクを見る"""
    user_id = プレイヤー.id
    data = RankingSystem.get_user_data(user_id)
    rank_info = RankingSystem.get_rank_info(data['rank'])

    winrate = RankingSystem.get_winrate(user_id)

    embed = discord.Embed(
        title=f"🎖️ {プレイヤー.display_name} のランク",
        color=rank_info['color']
    )
    embed.set_thumbnail(url=プレイヤー.display_avatar.url)

    embed.add_field(
        name="📊 ランク",
        value=f"{rank_info['emoji']} **{rank_info['name']}**\nポイント：**{data['points']}** pt",
        inline=False
    )

    embed.add_field(
        name="⚔️ 戦績",
        value=(
            f"{data['wins']}勝 {data['losses']}敗\n"
            f"勝率：**{winrate:.1f}%**"
        ),
        inline=True
    )

    embed.add_field(
        name="🔥 連勝",
        value=f"現在：{data['current_streak']} 試合\n最高：{data['best_streak']} 試合",
        inline=True
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ランクランキング", description="ランクランキング Top 10 を見る")
async def rank_leaderboard(interaction: discord.Interaction):
    """ランクランキング"""
    leaderboard = RankingSystem.get_leaderboard(10)

    if not leaderboard:
        await interaction.response.send_message("📊 まだランキングデータがありません！", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏆 ランクランキング Top 10",
        description="（ポイント順）",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, points, rank_id, wins, losses) in enumerate(leaderboard, 1):
        try:
            user = await interaction.client.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        rank_info = RankingSystem.get_rank_info(rank_id)
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."

        total_matches = wins + losses
        winrate = (wins / total_matches * 100) if total_matches > 0 else 0

        embed.add_field(
            name=f"{medal} {name}",
            value=(
                f"{rank_info['emoji']} **{rank_info['name']}** | {points} pt\n"
                f"戦績：{wins}勝 {losses}敗 ({winrate:.1f}%)"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ランク説明", description="全ランクの詳細説明を見る")
async def rank_info(interaction: discord.Interaction):
    """ランク説明"""
    embed = discord.Embed(
        title="🎖️ ランクシステム説明",
        description="デュエルでポイントを貯めて、ランクを上げよう！",
        color=discord.Color.blue()
    )

    for rank in RankingSystem.RANKS:
        points_range = f"{rank['min_points']} ~ {rank['max_points']}" if rank[
                                                                             'max_points'] < 999999 else f"{rank['min_points']}+"

        embed.add_field(
            name=f"{rank['emoji']} {rank['name']}",
            value=(
                f"ポイント範囲：**{points_range}**\n"
                f"昇格報酬：**{rank['promotion_reward']:,}** 円"
            ),
            inline=True
        )

    embed.add_field(
        name="\n📌 ポイントルール",
        value=(
            "• 勝利で 15~50 ポイント獲得\n"
            "• 敗北で 10~50 ポイント減少\n"
            "• ポイント変動は相手の実力で調整\n"
            "• 強者に勝つとより多くのポイント獲得"
        ),
        inline=False
    )

    embed.set_footer(text="/デュエル でランク戦の旅を始めよう！")

    await interaction.response.send_message(embed=embed)

# ==================== 占いシステム ====================
class FortuneSystem:
    """占いシステム"""

    # ユーザー占いデータ
    user_fortunes: Dict[int, dict] = {}

    # 🔧 ===== クールタイム設定（ここを変更）===== 🔧
    FORTUNE_COOLDOWN = 1  # デフォルト12時間（43200秒）

    # クイックリファレンス：
    # 0秒 = クールタイムなし
    # 60秒 = 1分
    # 300秒 = 5分
    # 600秒 = 10分
    # 1800秒 = 30分
    # 3600秒 = 1時間
    # 7200秒 = 2時間
    # 21600秒 = 6時間
    # 43200秒 = 12時間
    # 86400秒 = 24時間

    # 運勢レベル定義（そのまま維持）
    FORTUNE_LEVELS = [
        {
            'id': 'catastrophe',
            'name': '💀 大凶',
            'probability': 2,
            'color': 0x000000,
            'emoji': '💀',
            'title': '終末の予兆',
            'messages': [
                "今日は外出しないことをお勧めします、本当に。",
                "呼吸するだけでむせるかも、布団の中にいることをお勧めします。",
                "外出するとバナナの皮を踏み、家にいると天井が落ちてきます。",
                "あなたの厄運値は天井突破、人生をリセットすることをお勧めします。",
                "今日のあなたは歩く災害現場のようです。",
                "今日は死んだふりをして、何もしないことをお勧めします。",
                "今日外出すると詐欺、強盗、そして元恋人に遭遇するかも。",
                "運勢が悪すぎてフォーチュンクッキーの中も悪い知らせです。",
                "今日の最良の選択は明日まで寝ることです。"
            ],
            'advice': [
                "🚫 ギャンブル禁止、パンツまで失います",
                "🚫 ガチャ禁止、武器しか出ません",
                "🚫 決闘禁止、人生を疑うほど負けます",
                "🚫 株取引禁止、破産します",
                "✅ 推奨：電源を切って寝る"
            ]
        },
        {
            'id': 'very_bad',
            'name': '😱 凶',
            'probability': 8,
            'color': 0x8B0000,
            'emoji': '😱',
            'title': '水星逆行警報',
            'messages': [
                "今日外出すると犬のフンを踏むかも。",
                "あなたの不運指数は警戒値に達しています。",
                "今日は一つのことだけをすることをお勧めします：寝転がる。",
                "今日のあなたの運はあなたの貯金と同じくらい少ないです。",
                "今日は運が必要なことは何もしない方がいいです。",
                "今日は病気のふりをして休むことをお勧めします。",
                "今日は会いたくない人全員に出会うかもしれません。",
                "運勢が悪すぎてロボットさえ同情します。"
            ],
            'advice': [
                "🚫 カジノから離れて、パンツまで負けます",
                "🚫 ガチャ禁止、天井も助けてくれません",
                "🚫 PK回避、みっともなく負けます",
                "⚠️ ログインボーナスは可、でも期待しないで",
                "💡 推奨：ドラマ鑑賞、睡眠、ぼーっとする"
            ]
        },
        {
            'id': 'bad',
            'name': '😰 小凶',
            'probability': 15,
            'color': 0xCD5C5C,
            'emoji': '😰',
            'title': '雨模様',
            'messages': [
                "今日の運はあまり良くないですが、そこまで悲惨でもありません。",
                "今日は小さなトラブルに遭遇するかもしれません。",
                "期待値を下げることをお勧めします、がっかりしないように。",
                "今日のあなたは寝起きのナマケモノのようです。",
                "運勢はやや悪いですが、世界の終わりではありません。",
                "今日は運が必要ないことをするのに適しています。",
                "あなたの幸運値は今日休暇を取りました。",
                "保守的に行動することをお勧めします、一夜で大金持ちは考えないで。"
            ],
            'advice': [
                "⚠️ ギャンブルは注意、小さく賭けるだけ",
                "⚠️ ガチャは外れるかも、心の準備を",
                "⚠️ 決闘は慎重に、調子に乗らないで",
                "💰 小銭を稼いで生活を維持できます",
                "💡 推奨：軽いことだけをする"
            ]
        },
        {
            'id': 'normal',
            'name': '😐 平',
            'probability': 35,
            'color': 0x808080,
            'emoji': '😐',
            'title': '平凡な日',
            'messages': [
                "今日は普通の日、特別なことは何もありません。",
                "あなたの運勢は白湯のように平凡です。",
                "今日は普通のサラリーマンの日常です。",
                "運勢は安定、良くも悪くもなく、ただ普通です。",
                "今日のあなたはモブキャラです。",
                "今日のあなたは味付けのない白米のようです。",
                "運勢は普通、ただの平凡な一日です。",
                "今日は日常のルーティンをするのに適しています。"
            ],
            'advice': [
                "💰 普通に稼いで、普通に使う",
                "🎲 引きたければ引く、運任せ",
                "⚔️ 戦いたければ戦う、実力次第",
                "📈 株は適当、どうせ大金持ちにはならない",
                "💡 推奨：やるべきことをやる"
            ]
        },
        {
            'id': 'slightly_good',
            'name': '😊 小吉',
            'probability': 20,
            'color': 0x90EE90,
            'emoji': '😊',
            'title': 'そよ風',
            'messages': [
                "今日の運は悪くないですよ！",
                "今日は小さなサプライズがあるかもしれません。",
                "運勢上昇、チャンスを掴んで！",
                "今日のあなたは主人公オーラ付き（低スペック版）。",
                "運が良い、運試ししてみて。",
                "今日外出するとお金を拾うかも（小銭）。",
                "あなたの幸運値は今日ちゃんと出勤しています。",
                "今日は運が必要なことをするのに適しています。"
            ],
            'advice': [
                "💰 小銭を稼げます、運試ししてみて",
                "🎲 ガチャは当たりが出るチャンス",
                "⚔️ 決闘の勝率は良い",
                "📈 株式市場で試してみて",
                "💡 推奨：積極的に、チャンスを掴む"
            ]
        },
        {
            'id': 'good',
            'name': '😄 吉',
            'probability': 15,
            'color': 0x32CD32,
            'emoji': '😄',
            'title': '春風に乗る',
            'messages': [
                "今日の運勢は最高！やりたいことをやりましょう！",
                "今日のあなたは幸運のオーラ付き！",
                "今日は冒険するのに良い日です。",
                "幸運の女神が今日あなたのそばにいます。",
                "今日のあなたはチートを使ったかのようにスムーズです。",
                "運勢爆発、大胆になっていいです！",
                "今日外出すると貴人に出会うかも。",
                "あなたの幸運値は今日残業中！"
            ],
            'advice': [
                "💰 稼ぐチャンスが多い、掴んで！",
                "🎲 ガチャの排出率高い、何回か引いてもいい",
                "⚔️ 決闘必勝、他人を制裁しましょう",
                "📈 株式市場良好、大胆に投資を",
                "💡 推奨：今日は派手に行こう！"
            ]
        },
        {
            'id': 'great',
            'name': '🎉 大吉',
            'probability': 4,
            'color': 0xFFD700,
            'emoji': '🎉',
            'title': '幸運到来',
            'messages': [
                "おめでとうございます！今日はあなたのラッキーデー！",
                "今日のあなたは欧皇転生のようです！",
                "幸運の女神が今日直接あなたの家に住んでいます！",
                "今日道を歩いているだけで財布を拾うかも！",
                "今日のあなたの運勢は限界突破！",
                "今日宝くじを買うことをお勧めします、本当に。",
                "今日のあなたは無敵、向かうところ敵なし！",
                "運勢が良すぎて他の人が羨ましがります！"
            ],
            'advice': [
                "💰 今日は大金を稼ぐ日！",
                "🎲 ガチャは金確定、何回引いても問題なし",
                "⚔️ 決闘無敵、覇者になりましょう",
                "📈 株式市場急騰、All in で問題なし",
                "🎰 ギャンブル必勝、全賭けで正解",
                "💡 推奨：やりたいことを何でもやろう！"
            ]
        },
        {
            'id': 'supreme',
            'name': '✨ 極吉',
            'probability': 1,
            'color': 0xFF1493,
            'emoji': '✨',
            'title': '天に選ばれし者',
            'messages': [
                "🎊 おめでとうございます、極吉を引きました！これは万に一つの運勢です！",
                "✨ 今日のあなたは天に選ばれし者！",
                "🌟 幸運の女神が直接あなたを実の子のように育てています！",
                "💫 今日のあなたの運は人類の限界を超えています！",
                "🔥 今日のあなたは主人公オーラMAX版！",
                "⚡ 今日すべての宝くじを買うことをお勧めします！",
                "🎯 今日何をしても成功します！",
                "👑 今日のあなたはサーバー全体の王者！",
                "🌈 今日奇跡が起こるかもしれません！"
            ],
            'advice': [
                "💎 今日のあなたは伝説の欧皇！",
                "🎲 ガチャ十連必ず金二つ、出なかったら私の負け",
                "⚔️ 決闘無敵、HPは1で固定",
                "📈 株式市場は適当に買って適当に稼ぐ",
                "🎰 カジノはあなたのATM",
                "🔫 強盗必ず成功、警察もあなたを見たら道を譲る",
                "💡 推奨：全賭け！All in！一か八か！"
            ]
        }
    ]

    # 特別イベント
    SPECIAL_EVENTS = [
        "🌠 流れ星が空を横切り、あなたは願い事をしました",
        "🐱 道で黒猫に出会い、ニャーと鳴きました",
        "🍀 道端で四つ葉のクローバーを見つけました",
        "🎪 サーカスが通り過ぎ、ピエロがあなたに手を振りました",
        "🦅 鷹があなたの頭上を飛び、「贈り物」を残しました",
        "👻 奇妙な影を見ましたが、振り返ると消えていました",
        "🎭 大道芸人があなたの人相は並外れていると言いました",
        "🔮 神秘的なジプシーがあなたを一瞥しました",
        "🌙 今日の月は特に丸い",
        "☄️ 空に奇妙な雲が現れました",
        "🦊 キツネがあなたの夢に現れました",
        "🐉 自分がドラゴンに乗っている夢を見ました",
        "💀 正体不明の物体を踏みました",
        "🎰 カジノの前を通った時、誰かが大当たりした音を聞きました",
        "💰 財布の中にレシートが一枚増えていることに気づきました",
        "📱 携帯の電池残量がちょうど69%でした",
        "🚪 外出時左足から先に出ました",
        "☕ コーヒーをお気に入りの服にこぼしました",
        "🌈 雨上がりに虹を見ました",
        "⚡ 雷が鳴った時ちょうど元恋人のことを考えていました"
    ]

    @classmethod
    def get_today_fortune(cls, user_id: int) -> dict:

        fortune = cls._roll_fortune()
        special_event = random.choice(cls.SPECIAL_EVENTS) if random.random() < 0.3 else None

        cls.user_fortunes[user_id] = {
            'fortune_id': fortune['id'],
            'special_event': special_event
        }

        if user_id not in cls.fortune_history:
            cls.fortune_history[user_id] = []

        cls.fortune_history[user_id].append({
            'fortune': fortune['name'],
            'fortune_id': fortune['id']
        })

        if len(cls.fortune_history[user_id]) > 30:
            cls.fortune_history[user_id] = cls.fortune_history[user_id][-30:]

        return cls._get_fortune_data(fortune['id'], special_event)

    @classmethod
    def _roll_fortune(cls) -> dict:
        """運勢を抽選"""
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
        """運勢詳細データを取得"""
        fortune = next((f for f in cls.FORTUNE_LEVELS if f['id'] == fortune_id), cls.FORTUNE_LEVELS[3])

        return {
            'fortune': fortune,
            'message': random.choice(fortune['messages']),
            'advice': fortune['advice'],
            'special_event': special_event
        }

    @classmethod
    def get_fortune_stats(cls, user_id: int) -> dict:
        """占い統計を取得"""
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


# ==================== 占いコマンド ====================

@bot.tree.command(name="占い", description="🔮 毎日の運勢占い（完全エンタメ）")
async def daily_fortune(interaction: discord.Interaction):
    """毎日の占い"""
    user_id = interaction.user.id

    # 🆕 直接運勢を取得（クールダウンなし）
    fortune_data = FortuneSystem.get_today_fortune(user_id)
    fortune = fortune_data['fortune']
    message = fortune_data['message']
    advice = fortune_data['advice']
    special_event = fortune_data['special_event']

    # 豪華なEmbedを作成
    embed = discord.Embed(
        title=f"🔮 {interaction.user.display_name} さんの占い結果",
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
        name="💬 運勢解説",
        value=f"*{message}*",
        inline=False
    )

    if special_event:
        embed.add_field(
            name="✨ 特別な兆し",
            value=special_event,
            inline=False
        )

    advice_text = "\n".join(advice)
    embed.add_field(
        name="📝 今日のアドバイス",
        value=advice_text,
        inline=False
    )

    if fortune['id'] == 'supreme':
        embed.add_field(
            name="🎊 おめでとう！",
            value="超レアな「大大吉」を引きました！当選確率はわずか1％！",
            inline=False
        )
    elif fortune['id'] == 'catastrophe':
        embed.add_field(
            name="⚠️ 注意",
            value="運勢が非常に悪い日です…今日は無理をしないようにしましょう。",
            inline=False
        )

    # 🆕 クールダウンなしの表示
    embed.set_footer(text="💡 エンタメ目的のみ | いつでも占えます")

    await interaction.response.send_message(embed=embed)



@bot.tree.command(name="占い統計", description="📊 占い履歴統計を見る")
async def fortune_stats(interaction: discord.Interaction):
    """占い統計"""
    user_id = interaction.user.id

    stats = FortuneSystem.get_fortune_stats(user_id)

    if not stats:
        await interaction.response.send_message(
            "📊 まだ占い記録がありません！\n`/占い`を使って毎日の占いを始めましょう！",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"📊 {interaction.user.display_name} の占い統計",
        color=discord.Color.purple()
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    embed.add_field(
        name="📅 占い日数",
        value=f"**{stats['total_days']}** 日",
        inline=True
    )

    good_rate = (stats['good_days'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
    embed.add_field(
        name="🍀 幸運日数",
        value=f"**{stats['good_days']}** 日 ({good_rate:.1f}%)",
        inline=True
    )

    bad_rate = (stats['bad_days'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
    embed.add_field(
        name="💀 不運日数",
        value=f"**{stats['bad_days']}** 日 ({bad_rate:.1f}%)",
        inline=True
    )

    if stats['stats']:
        stats_text = "\n".join([f"{name}: **{count}** 回" for name, count in
                                sorted(stats['stats'].items(), key=lambda x: x[1], reverse=True)])
        embed.add_field(
            name="📈 運勢分布",
            value=stats_text,
            inline=False
        )

    if stats['most_common']:
        embed.add_field(
            name="🎯 最多運勢",
            value=f"{stats['most_common'][0]} (**{stats['most_common'][1]}** 回)",
            inline=False
        )

    if good_rate > 50:
        comment = "あなたの運は悪くないですよ！この調子で！✨"
    elif bad_rate > 50:
        comment = "最近運が良くないですね...お参りに行きますか？🙏"
    else:
        comment = "あなたの運勢はとても安定しています、ただの普通の人です。😐"

    embed.add_field(
        name="💬 総合評価",
        value=comment,
        inline=False
    )

    embed.set_footer(text="占いを続けるとより多くの統計データが蓄積されます")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="占いランキング", description="🏆 幸運ランキングを見る")
async def fortune_leaderboard(interaction: discord.Interaction):
    """占いランキング"""

    rankings = []

    for user_id in FortuneSystem.fortune_history.keys():
        stats = FortuneSystem.get_fortune_stats(user_id)
        if stats and stats['total_days'] >= 3:
            lucky_score = (stats['good_days'] - stats['bad_days']) / stats['total_days'] * 100
            rankings.append((user_id, lucky_score, stats['total_days'], stats['good_days']))

    if not rankings:
        await interaction.response.send_message(
            "🏆 現在十分な占いデータがありません！\n少なくとも3回の占い記録が必要です。",
            ephemeral=True
        )
        return

    rankings.sort(key=lambda x: x[1], reverse=True)
    rankings = rankings[:10]

    embed = discord.Embed(
        title="🏆 幸運ランキング Top 10",
        description="（幸運日数の割合に基づくランキング）",
        color=discord.Color.gold()
    )

    medals = ["🥇", "🥈", "🥉"]

    for idx, (user_id, score, total, good) in enumerate(rankings, 1):
        try:
            user = await interaction.client.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"ユーザー {user_id}"

        medal = medals[idx - 1] if idx <= 3 else f"{idx}."

        if score > 30:
            status = "✨ 欧皇"
        elif score > 10:
            status = "🍀 ラッキー"
        elif score > -10:
            status = "😐 普通の人"
        elif score > -30:
            status = "💀 アフリカ人"
        else:
            status = "😱 厄運纏う"

        embed.add_field(
            name=f"{medal} {name}",
            value=f"{status} | 幸運値：**{score:.1f}**\n占い {total} 日、幸運 {good} 日",
            inline=False
        )

    embed.set_footer(text="💡 連続占いでランキング精度が向上します")

    await interaction.response.send_message(embed=embed)


# ==================== 📖 ヘルプコマンド ====================

@bot.tree.command(name="ヘルプ", description="利用可能なコマンドを見る")
async def help_command(interaction: discord.Interaction):
    """ヘルプコマンド"""

    embed = discord.Embed(
        title="📖 コマンド説明書",
        description="以下はすべての利用可能なコマンドです、カテゴリをクリックして詳細を見てください",
        color=discord.Color.blue()
    )

    # 💰 お金システム
    embed.add_field(
        name="💰 お金システム",
        value=(
            "`/お金確認` - お金を確認（対象を指定可能）\n"
            "`/送金` - 他のプレイヤーに送金（手数料5%）\n"
            "`/個人統計` - 個人統計パネルを見る\n"
            "`/お金ランキング` - お金ランキングを見る"
        ),
        inline=False
    )

    # 🎮 ミニゲーム
    embed.add_field(
        name="🎮 ミニゲーム",
        value=(
            "`/お金稼ぎ` - 数学問題を解いてお金を稼ぐ（クールタイム5秒）\n"
            "`/数字当て` - 数字当てゲーム（1000元賭け）\n"
            "`/じゃんけん` - じゃんけん勝負（2000元賭け）\n"
            "`/サイコロ勝負` - サイコロ勝負（2000元賭け）\n"
            "`/くじ引き` - 運を試す"
        ),
        inline=False
    )

    # 🎰 ギャンブルシステム
    embed.add_field(
        name="🎰 ギャンブルシステム",
        value=(
            "`/ギャンブル` - ギャンブルで大金を稼ぐ（敷居500元）\n"
            "`/ギャンブル詳細` - オッズと勝率を見る\n"
            "`/ギャンブル神ランキング` - ギャンブル最多勝ランキングを見る"
        ),
        inline=False
    )

    # 🎲 ガチャシステム
    embed.add_field(
        name="🎲 ガチャシステム",
        value=(
            "`/単発` - 単発ガチャ（120元）\n"
            "`/10連` - 10連ガチャ（1200元）\n"
            "`/天井確認` - 天井状態を見る\n"
            "`/排出履歴` - 星5履歴を見る\n"
            "`/確率説明` - ガチャ確率を見る\n"
            "`/現在upキャラ` - UPキャラを見る\n"
            "`/ガチャランキング` - ガチャ回数ランキング\n"
            "`/天井リセット` - ガチャ記録をリセット"
        ),
        inline=False
    )

    # 🎒 アイテムシステム
    embed.add_field(
        name="🎒 アイテムシステム",
        value=(
            "`/バッグ確認` - ガチャアイテム在庫を見る\n"
            "`/アイテム売却` - アイテムを売ってお金に換える\n"
            "`/一括売却` - アイテムをまとめて売る"
        ),
        inline=False
    )

    # 📅 ログインシステム
    embed.add_field(
        name="📅 ログインシステム",
        value=(
            "`/ログイン` - 毎日ログインして報酬をもらう\n"
            "`/ログイン情報` - ログイン統計を見る\n"
            "`/ログインランキング` - ログインランキング"
        ),
        inline=False
    )

    # 📈 株式システム
    embed.add_field(
        name="📈 株式システム",
        value=(
            "`/全株式` - 株式総覧を素早く見る\n"
            "`/株式リスト` - 取引可能な株式を見る\n"
            "`/株式詳細` - 株式詳細情報を見る\n"
            "`/株式購入` - 株式を購入\n"
            "`/株式売却` - 株式を売却\n"
            "`/保有確認` - 株式保有を見る\n"
            "`/取引記録` - 取引記録を見る\n"
            "`/株式ランキング` - 株式大富豪ランキング"
        ),
        inline=False
    )

    # ⚔️ 戦闘システム
    embed.add_field(
        name="⚔️ 戦闘システム",
        value=(
            "`/決闘` - 友達と決闘\n"
            "`/強盗` - 他のプレイヤーを襲う（クールタイム3分）"
        ),
        inline=False
    )

    # 🎖️ 称号システム
    embed.add_field(
        name="🎖️ 称号システム",
        value=(
            "`/マイ称号` - 自分の称号を見る\n"
            "`/称号確認` - 他のプレイヤーの称号を見る\n"
            "`/段位ランキング` - 段位ランキング Top 10\n"
            "`/段位説明` - 段位詳細説明を見る"
        ),
        inline=False
    )

    # 🏆 実績システム
    embed.add_field(
        name="🏆 実績システム",
        value=(
            "`/マイ実績` - 実績進捗を見る\n"
            "`/実績詳細` - 特定の実績を見る\n"
            "`/実績ランキング` - 実績解除ランキング"
        ),
        inline=False
    )

    # 🏪 ショップシステム
    embed.add_field(
        name="🏪 ショップシステム",
        value=(
            "`/ショップ` - ショップ商品を見る\n"
            "`/購入` - ショップアイテムを購入\n"
            "`/マイアイテム` - 所有アイテムを見る\n"
            "`/アイテム使用` - 消費アイテムを使う"
        ),
        inline=False
    )

    # 🔮 占いシステム
    embed.add_field(
        name="🔮 占いシステム",
        value=(
            "`/占い` - 毎日の運勢占い\n"
            "`/占い統計` - 占い履歴を見る\n"
            "`/占いランキング` - 幸運ランキング"
        ),
        inline=False
    )

    # 🎵 音楽システム
    embed.add_field(
        name="🎵 音楽システム",
        value=(
            "`/参加` - ボイスチャンネルに参加\n"
            "`/再生` - 音楽を再生（URLまたはキーワード）\n"
            "`/一時停止` - 音楽を一時停止\n"
            "`/再開` - 再生を続ける\n"
            "`/スキップ` - 現在の曲をスキップ\n"
            "`/停止` - 再生を停止してキューをクリア\n"
            "`/ループ` - シングルループのオン/オフ\n"
            "`/自動再生` - 自動再生のオン/オフ\n"
            "`/再生リスト` - 再生キューを見る\n"
            "`/再生中` - 現在の曲を表示\n"
            "`/退出` - ボイスチャンネルを退出\n"
            "`/再生履歴` - 最近の再生を見る\n"
            "`/音楽履歴クリア` - 再生記録をクリア\n"
            "`/更新` - 再生リンクを再取得"
        ),
        inline=False
    )

    # 🔥 エフェクトシステム
    embed.add_field(
        name="🔥 エフェクトシステム",
        value=(
            "`/fire` - アバターに炎エフェクトを追加(SHIT)"
        ),
        inline=False
    )

    # 🛠️ 管理者コマンド
    embed.add_field(
        name="🛠️ 管理者コマンド",
        value=(
            "`/お金設定` - 指定ユーザーのお金を設定\n"
            "`/お金調整` - ユーザーのお金を増減\n"
            "`/upキャラ設定` - UPキャラを変更\n"
            "`/アバター` - ユーザーのアバターを取得\n"
            "`/バナー` - ユーザーのバナーを取得\n"
        ),
        inline=False
    )

    embed.set_footer(text="💡 一部のコマンドは特定の権限または特定のチャンネルでの使用が必要です")
    embed.timestamp = datetime.now()

    await interaction.response.send_message(embed=embed)

# ==================== 📸 アバター/バナーシステム ====================

@bot.tree.command(name="アバター", description="ユーザーのアバターを取得")
@app_commands.describe(ユーザー="見たいユーザー（デフォルトは自分）", サイズ="画像サイズ")
@app_commands.choices(サイズ=[
    app_commands.Choice(name='小 (128px)', value=128),
    app_commands.Choice(name='中 (256px)', value=256),
    app_commands.Choice(name='大 (512px)', value=512),
    app_commands.Choice(name='特大 (1024px)', value=1024),
    app_commands.Choice(name='超大 (2048px)', value=2048),
    app_commands.Choice(name='最大 (4096px)', value=4096),
])
async def get_avatar(interaction: discord.Interaction, ユーザー: discord.User = None,
                     サイズ: app_commands.Choice[int] = None):
    """アバターを取得"""
    target = ユーザー or interaction.user
    size = サイズ.value if サイズ else 1024

    avatar_url = target.display_avatar.with_size(size).url

    embed = discord.Embed(
        title=f"🖼️ {target.display_name} のアバター",
        color=discord.Color.blue()
    )
    embed.set_image(url=avatar_url)
    embed.add_field(name="📏 サイズ", value=f"{size}x{size}px", inline=True)
    embed.add_field(name="🔗 直接リンク", value=f"[ダウンロード]({avatar_url})", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="バナー", description="ユーザーのバナーを取得")
@app_commands.describe(ユーザー="見たいユーザー（デフォルトは自分）")
async def get_banner(interaction: discord.Interaction, ユーザー: discord.User = None):
    """バナーを取得"""
    target = ユーザー or interaction.user

    # バナーを取得するにはfetchが必要
    try:
        user = await bot.fetch_user(target.id)

        if user.banner:
            banner_url = user.banner.with_size(1024).url

            embed = discord.Embed(
                title=f"🎨 {target.display_name} のバナー",
                color=discord.Color.purple()
            )
            embed.set_image(url=banner_url)
            embed.add_field(name="🔗 直接リンク", value=f"[ダウンロード]({banner_url})", inline=False)

            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"❌ {target.mention} はバナーを設定していません",
                ephemeral=True
            )
    except Exception as e:
        await interaction.response.send_message(f"❌ バナー取得失敗：{e}", ephemeral=True)


@bot.tree.command(name="プロフィール", description="ユーザーの完全なプロフィールを見る")
@app_commands.describe(ユーザー="見たいユーザー（デフォルトは自分）")
async def user_profile(interaction: discord.Interaction, ユーザー: discord.User = None):
    """完全なプロフィール"""
    target = ユーザー or interaction.user

    try:
        user = await bot.fetch_user(target.id)
        member = interaction.guild.get_member(target.id)

        embed = discord.Embed(
            title=f"👤 {user.display_name} のプロフィール",
            color=user.accent_color or discord.Color.blue()
        )

        # アバター
        embed.set_thumbnail(url=user.display_avatar.with_size(256).url)

        # バナー
        if user.banner:
            embed.set_image(url=user.banner.with_size(1024).url)

        # 基本情報
        embed.add_field(
            name="📝 基本情報",
            value=(
                f"**ユーザー名：** {user.name}\n"
                f"**ID：** `{user.id}`\n"
                f"**作成日時：** <t:{int(user.created_at.timestamp())}:R>"
            ),
            inline=False
        )

        # サーバー情報
        if member:
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            embed.add_field(
                name="🏰 サーバー情報",
                value=(
                    f"**ニックネーム：** {member.display_name}\n"
                    f"**参加日時：** <t:{int(member.joined_at.timestamp())}:R>\n"
                    f"**ロール：** {' '.join(roles[:5]) if roles else 'なし'}"
                ),
                inline=False
            )

        # ゲーム統計
        money = MoneySystem.get_money(target.id)
        gacha_data = GachaSystem.get_user_pity(target.id)
        rank_data = RankingSystem.get_user_data(target.id)
        rank_info = RankingSystem.get_rank_info(rank_data['rank'])

        embed.add_field(
            name="🎮 ゲーム統計",
            value=(
                f"💰 お金：**{money:,}** 元\n"
                f"🎲 ガチャ：**{gacha_data['total_pulls']}** 回\n"
                f"🎖️ 称号：{rank_info['emoji']} **{rank_info['name']}**"
            ),
            inline=False
        )

        # ダウンロードリンク
        links = []
        links.append(f"[アバター]({user.display_avatar.with_size(4096).url})")
        if user.banner:
            links.append(f"[バナー]({user.banner.with_size(4096).url})")

        embed.add_field(
            name="🔗 ダウンロードリンク",
            value=" | ".join(links),
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ データ取得失敗：{e}", ephemeral=True)


# ==================== メインプログラムエントリーポイント ====================
if __name__ == "__main__":
    print()

    # FFmpegチェック
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        print("✅ FFmpegがインストールされています")
    except:
        print("❌ 警告：FFmpegが見つかりません！まずFFmpegをインストールしてください。")

    # 炎動画チェック
    if os.path.exists(FOREGROUND_VIDEO):
        print(f"✅ 炎動画が見つかりました：{FOREGROUND_VIDEO}")
    else:
        print(f"❌ 警告：炎動画が見つかりません：{FOREGROUND_VIDEO}")

    print()
    print("Botを起動中...")

    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\nBotをシャットダウン中...")
    finally:
        # シャットダウン前にデータを保存
        DataManager.save_data()
        print("👋 Botが安全にシャットダウンされました")
