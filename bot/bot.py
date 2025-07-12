from datetime import datetime

from prometheus_client import start_http_server
from telegram import Update, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from config import BOT_TOKEN, logger
from core.models import Booking
from core.services import UserService, YogaClassService
from monitoring import *
from .helpers import (
    get_user,
    is_admin,
    create_reply_keyboard,
    create_inline_keyboard
)
from .conversations import *
from .handlers import *






# bot start
def setup_handlers(application):
    """Настройка обработчиков команд и сообщений."""
    # Обработчик команды /start
    logger.info("Setting up handlers...")
    application.add_handler(CommandHandler("start", start))
    logger.info("Added start handler")


    # Обработчики для добавления студии
    studio_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^🏟️ Добавить студию$"), start_adding_studio)
        ],
        states={
            ENTER_STUDIO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_name)],
            ENTER_STUDIO_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_address)],
            ENTER_STUDIO_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_capacity)],
            ENTER_STUDIO_HAS_SHOWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_has_shower)]
        },
        fallbacks=[CommandHandler('cancel', cancel_adding_studio)],
        conversation_timeout=1200
    )

    # Обработчики для создания занятия
    class_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📅 Добавить занятие$"), start_creating_yoga_class)
        ],
        states={
            ENTER_CLASS_STUDIO: [
                CallbackQueryHandler(select_studio, pattern=r"^select_studio_\d+$"),
                CallbackQueryHandler(handle_pagination, pattern=r"^(studio_next_page|studio_prev_page)$")
            ],
            ENTER_CLASS_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_time)],
            ENTER_CLASS_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_duration)],
            ENTER_CLASS_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_capacity)],
            ENTER_CLASS_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_name)]
        },
        fallbacks=[CommandHandler('cancel', cancel_creating_yoga_class)],
        conversation_timeout=1200
    )

    # Основные обработчики сообщений и callback-запросов
    application.add_handler(studio_conversation)
    application.add_handler(class_conversation)
    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок."""
    logger.error(f"Update {update} caused error {context.error}")


def start_bot():
    # Создание и настройка приложения бота
    application = Application.builder().token(BOT_TOKEN).build()
    setup_handlers(application)
    logger.info("Bot started successfully")
    # Запуск бота
    application.run_polling()
