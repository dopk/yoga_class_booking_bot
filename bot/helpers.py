import re
from telegram import Update

from config import ADMINS
from core.models import User
from core.services import UserService
from config import logger


async def get_user(update: Update) -> User:
    """Get or create user in database."""
    if not update.effective_user:
        raise ValueError("Effective user not found")

    user = update.effective_user
    db_user, created = UserService.get_or_create(
        messenger_id=user.id,
        display_name=user.full_name,
        username=user.username)

    if created:
        logger.info("New user registered: %s", user.id)
    return db_user


async def get_user_from_query(query) -> User:
    """Получение пользователя из callback query."""
    return await get_user(query.update)


def is_admin(user: User) -> bool:
    """Ceck is user admin."""
    return user.messenger_id in ADMINS

def check_yes(entered_str: str) -> bool:
    """Check string contains yes"""
    words = re.findall(r'\w+', str(entered_str).lower())
    return any(word in {"да", "yes", "true", "1"} for word in words)

def check_no(entered_str: str) -> bool:
    """Check string contains no"""
    words = re.findall(r'\w+', str(entered_str).lower())
    return any(word in {"нет", "no", "false", "0"} for word in words)


def main():
    pass

if __name__ == "__main__":
    main()
