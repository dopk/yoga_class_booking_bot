from apscheduler.schedulers.background import BackgroundScheduler

from bot.bot import *
from core.models import initialize_db

def main():
    """Основная функция запуска бота."""
    try:
        # Инициализация метрик Prometheus
        start_http_server(8000)
        logger.info("Prometheus metrics server started on port 8000")

        # Инициализация планировщика задач
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=update_database_metrics,
            trigger='interval',
            minutes=15
        )
        scheduler.start()

        # Инициализация базы данных
        initialize_db()
        # Запуск бота
        start_bot()
    except Exception as e:
        errors_counter.inc()
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
