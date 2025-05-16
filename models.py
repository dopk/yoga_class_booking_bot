from datetime import datetime, timedelta
import logging
from peewee import *
from config import ADMINS

logger = logging.getLogger(__name__)

db = SqliteDatabase('yoga.db')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    telegram_id = IntegerField(unique=True)
    username = CharField(null=True)
    display_name = CharField(null=True)
    is_teacher = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.now)
    notes = CharField(default='')

    @property
    def role(self):
        if self.telegram_id in ADMINS:
            return "admin"
        return "teacher" if self.is_teacher else "student"

class Studio(BaseModel):
    name = CharField(unique=True)
    address = CharField()
    capacity = IntegerField()
    has_shower = BooleanField()
    created_by = ForeignKeyField(User, backref='studios')
    created_at = DateTimeField(default=datetime.now)

class YogaClass(BaseModel):
    name = CharField()
    studio = ForeignKeyField(Studio, backref='classes')
    teacher = ForeignKeyField(User, backref='classes')
    start_time = DateTimeField()
    duration = IntegerField()  # in minutes
    capacity = IntegerField()
    created_at = DateTimeField(default=datetime.now)

    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration)

class Booking(BaseModel):
    user = ForeignKeyField(User, backref='bookings')
    yoga_class = ForeignKeyField(YogaClass, backref='bookings')
    status = CharField(choices=['pending', 'confirmed', 'canceled'], default='pending')
    created_at = DateTimeField(default=datetime.now)

def initialize_db():
    with db:
        db.create_tables([User, Studio, YogaClass, Booking])
        logger.info("Database tables created")
