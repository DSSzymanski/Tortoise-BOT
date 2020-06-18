import os
import logging
import traceback
from sys import stdout
from pathlib import Path

from dotenv import load_dotenv

from bot.bot import Bot
from bot.non_blocking_file_handler import NonBlockingFileHandler


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(message)s")

file_handler = NonBlockingFileHandler("log.txt", encoding="utf-8")
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

console_logger = logging.getLogger("console")
console = logging.StreamHandler(stdout)
console.setFormatter(formatter)
console_logger.addHandler(console)


# If not empty then only these will be loaded. Good for local debugging.
allowed_extensions = ()
banned_extensions = ("captcha_verification", "test")
root_logger.info(f"Banned extension: {banned_extensions}")

load_dotenv()
bot = Bot(prefix="t.")


for extension_path in Path("bot/cogs").glob("*.py"):
    extension_name = extension_path.stem

    if extension_name in banned_extensions:
        continue

    if allowed_extensions and extension_name not in allowed_extensions:
        continue

    dotted_path = f"bot.cogs.{extension_name}"

    try:
        bot.load_extension(dotted_path)
        console_logger.info(f"loaded {dotted_path}")
    except Exception as e:
        traceback_msg = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
        console_logger.info(f"Failed to load cog {dotted_path} - traceback:{traceback_msg}")

bot.run(os.getenv("BOT_TOKEN"))
