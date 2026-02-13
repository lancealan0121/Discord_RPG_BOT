# 🎮 Discord 多功能遊戲 Bot (日本語版)

一個功能豐富的 Discord 遊戲 Bot，包含經濟系統、抽卡系統、音樂播放、PVP 對戰等多種功能。

## ✨ 主要功能

### 💰 經濟系統
- 賺錢小遊戲（數學題、猜數字、剪刀石頭布、骰子）
- 玩家間轉帳（5% 手續費）
- 每日簽到獎勵
- 個人統計面板

### 🎲 抽卡系統
- 崩壞星穹鐵道風格抽卡
- 軟保底 & 硬保底機制
- UP 角色系統
- 抽卡歷史記錄
- 道具背包管理

### 🎰 賭博系統
- 多層級賭博（小額 → 大賭局）
- 動態賠率計算
- 賭神排行榜

### 📈 股票交易
- 6 種虛擬股票
- 每分鐘價格波動
- 買賣交易系統
- 股票大亨排行榜

### ⚔️ 戰鬥系統
- **決鬥模式**：回合制戰鬥，爆笑戰鬥文本
- **搶劫系統**：高風險高回報（冷卻時間 3 分鐘）
- **段位系統**：8 個段位（青銅 → 挑戰者）

### 🎵 音樂播放
- YouTube 音樂播放
- 關鍵字搜索（互動式選單）
- 自動推薦下一首
- 播放列表管理
- 單曲循環

### 🏆 成就系統
- 15+ 種成就
- 自動解鎖
- 成就獎勵

### 🏪 商城系統
- 賭博增幅道具
- 防搶劫保護
- 復活裝置
- VIP 通行證

### 🔮 占卜系統
- 每日運勢占卜
- 8 種運勢等級
- 歷史統計

### 🔥 特效系統
- 頭像火焰特效（使用 FFmpeg）

## 📦 安裝

### 1. 前置需求

- Python 3.10+
- FFmpeg（必須）

#### 安裝 FFmpeg (Windows)
```bash
# 使用 Chocolatey
choco install ffmpeg

# 或使用 Scoop
scoop install ffmpeg
```

#### 安裝 FFmpeg (Mac)
```bash
brew install ffmpeg
```

#### 安裝 FFmpeg (Linux)
```bash
sudo apt install ffmpeg  # Ubuntu/Debian
sudo yum install ffmpeg  # CentOS/RHEL
```

### 2. 克隆專案
```bash
git clone https://github.com/your-username/discord-game-bot-jp.git
cd discord-game-bot-jp
```

### 3. 安裝依賴
```bash
pip install -r requirements.txt
```

### 4. 準備火焰影片
- 下載火焰特效影片（建議黑背景或綠幕）
- 重命名為 `fire.mp4`
- 放置在專案根目錄

推薦下載網站：
- [Pixabay Videos](https://pixabay.com/videos/search/fire/)
- [Pexels Videos](https://www.pexels.com/search/videos/fire/)

### 5. 設定 Bot Token
1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)
2. 創建應用程式 → Bot → 複製 Token
3. 在 `discord_bot_jp.py` 第 16 行替換：
```python
TOKEN = '你的_Bot_Token'
```

### 6. Bot 權限設定
在 Discord Developer Portal 啟用以下權限：
- ✅ Presence Intent
- ✅ Server Members Intent
- ✅ Message Content Intent

## 🚀 啟動 Bot
```bash
python discord_bot_jp.py
```

看到以下訊息表示成功：
```
✅ FFmpegがインストールされています
✅ 炎動画が見つかりました：./fire.mp4
🔥 Botが[Bot名]としてログインしました
✅ X個のコマンドを同期しました
```

## 📖 指令列表

### 💰 經濟
```
/お金を見る        - 查看金錢
/送金            - 轉帳給其他玩家
/個人統計         - 個人統計面板
/お金ランキング    - 金錢排行榜
```

### 🎮 小遊戲
```
/お金を稼ぐ       - 數學題賺錢（冷卻 5 秒）
/数当て          - 猜數字（賭注 1000）
/じゃんけん       - 剪刀石頭布（賭注 2000）
/サイコロ勝負     - 擲骰子（賭注 2000）
```

### 🎲 抽卡
```
/単発            - 單抽（120 元）
/10連            - 十連抽（1200 元）
/天井確認         - 查看保底狀態
/履歴            - 五星歷史
```

### 🎰 賭博
```
/ギャンブル       - 賭博（最低 500 元）
/ギャンブル詳細   - 查看賠率說明
```

### 📈 股票
```
/全株式          - 快速查看所有股票
/株購入          - 購買股票
/株売却          - 賣出股票
/保有株          - 查看持股
```

### ⚔️ 戰鬥
```
/デュエル         - 與朋友決鬥
/強盗            - 搶劫玩家（冷卻 3 分鐘）
```

### 🎵 音樂
```
/参加            - 加入語音頻道
/再生 <關鍵字>    - 播放音樂
/スキップ         - 跳過當前歌曲
/キュー          - 查看播放列表
/退出            - 離開語音
```

### 🎖️ 段位
```
/マイランク       - 查看自己段位
/ランクランキング  - 段位排行榜
```

### 🏆 成就
```
/マイ実績         - 查看成就進度
/実績ランキング    - 成就排行榜
```

### 🏪 商城
```
/ショップ         - 查看商品
/購入            - 購買道具
/マイアイテム     - 查看持有道具
```

### 🔮 占卜
```
/占い            - 每日運勢占卜
/占い統計         - 占卜歷史統計
```

### 🔥 特效
```
/fire [@用戶]     - 生成火焰頭像特效
```

### 🛠️ 管理員
```
/お金設定         - 設定玩家金錢
/お金調整         - 增減玩家金錢
/upキャラ設定     - 修改 UP 角色
```

## 📁 檔案結構
```
discord-game-bot-jp/
├── discord_bot_jp.py      # Bot 主程式
├── fire.mp4               # 火焰特效影片
├── requirements.txt       # Python 依賴
├── bot_data.json         # 資料檔案（自動生成）
├── backups/              # 備份資料夾（自動生成）
└── README.md             # 說明文件
```

## ⚙️ 配置選項

### 冷卻時間調整
在 `discord_bot_jp.py` 中修改：
```python
# 賺錢冷卻（第 15 行）
EARN_MONEY_COOLDOWN = 5  # 秒

# 搶劫冷卻（第 2558 行）
ROB_COOLDOWN = 180  # 秒

# 占卜冷卻（第 4329 行）
FORTUNE_COOLDOWN = 43200  # 秒（預設 12 小時）
```

## 🐛 常見問題

### Q: Bot 無法播放音樂
**A:** 確認已安裝 FFmpeg 並加入系統 PATH

### Q: `/fire` 指令無法使用
**A:** 確認 `fire.mp4` 檔案存在於專案根目錄

### Q: Bot 離線後資料遺失
**A:** Bot 每 5 分鐘自動儲存，可在 `backups/` 資料夾找到備份

### Q: Token 無效
**A:** 重新生成 Token，並確認啟用所有必要的 Intents

## 🔐 安全提醒

⚠️ **永遠不要將 Bot Token 上傳到 GitHub！**

建議使用環境變數：
```python
import os
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
```

然後在終端設定：
```bash
# Windows
set DISCORD_BOT_TOKEN=你的Token

# Mac/Linux
export DISCORD_BOT_TOKEN=你的Token
```

## 📊 資料備份

Bot 會自動：
- ✅ 每 5 分鐘自動儲存
- ✅ 保留最近 5 個備份
- ✅ 儲存位置：`backups/` 資料夾

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request！

## 📝 授權

MIT License

## 👨‍💻 作者

Made with ❤️ by yulun

## 🙏 致謝

- [discord.py](https://github.com/Rapptz/discord.py)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- FFmpeg

---

⭐ 如果覺得有用，請給個星星！
