import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS_STR = os.getenv("ADMINS")
ADMINS = [int(x) for x in ADMINS_STR.split(",")] if ADMINS_STR else []
