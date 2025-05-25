from functools import wraps
import logging
from time import time

from prometheus_client import Counter, Gauge, Histogram

from core.models import User, Studio, YogaClass, Booking

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)


commands_counter = Counter(
    'bot_commands_total', 
    'Total number of commands processed', 
    ['command']
)
errors_counter = Counter('bot_errors_total', 'Total number of errors occurred')
database_entities = Gauge(
    'bot_database_entities',
    'Number of entities in database',
    ['entity']
)
request_duration = Histogram(
    'bot_request_duration_seconds',
    'Duration of bot requests',
    ['command']
)


def track_command(command_name):
    """Decorator for get time duration of command."""
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context):
            start_time = time()
            try:
                result = await func(update, context)
                request_duration.labels(command=command_name).observe(time() - start_time)
                return result
            except Exception as e:
                errors_counter.inc()
                logger.error(f"Error in {command_name}: {e}")
                raise
        return wrapper
    return decorator

def update_database_metrics():
    """Update database metrics."""
    try:
        database_entities.labels(entity='user').set(User.select().count())
        database_entities.labels(entity='studio').set(Studio.select().count())
        database_entities.labels(entity='yoga_class').set(YogaClass.select().count())
        database_entities.labels(entity='booking').set(Booking.select().count())
    except Exception as e:
        logger.error(f"Error updating database metrics: {e}")
