import os

# Токен бери у @BotFather и клади в переменную окружения BOT_TOKEN
# (на Railway это делается во вкладке Variables проекта)
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")

# Telegram user_id администраторов бота (могут запускать/завершать ивенты с боссами)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

DB_PATH = os.getenv("DB_PATH", "crab_game.db")
