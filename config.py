import os

# Токен бери у @BotFather и клади в переменную окружения BOT_TOKEN
# (на Amvera Cloud это делается в разделе "Переменные и секреты" проекта)
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")

# Telegram user_id администраторов бота (могут запускать/завершать ивенты с боссами)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# На Amvera постоянное хранилище примонтировано в /data (см. amvera.yaml,
# persistenceMount) — всё, что не там, стирается при каждой пересборке.
# DB_PATH можно переопределить переменной окружения, если понадобится.
DB_PATH = os.getenv("DB_PATH", "/data/crab_game.db")
