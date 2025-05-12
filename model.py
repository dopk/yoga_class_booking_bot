from dataclasses import dataclass
from datetime import date
import logging

from storage import BaseModel, BaseRepository, DatabaseManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Admin(BaseModel):
    """Teacher data model"""
    username: str
    display_name: str
    registration_date: date
    notes: str = ""
    id: int | None = None

# ... (keep all the previous imports and base classes from our original code) ...

@dataclass
class Teacher(BaseModel):
    """Teacher data model"""
    username: str
    display_name: str
    registration_date: date
    payment_end_date: date
    notes: str = ""
    id: int | None = None


@dataclass
class Studio(BaseModel):
    """Yoga halls data model"""
    name: str
    address: str
    has_shower: bool
    added_date: date
    capacity: int
    notes: str = ""
    id: int | None = None

@dataclass
class YogaClass(BaseModel):
    """Yoga class data model"""
    name: str
    studio_id: int
    teacher_id: int
    start_time: date
    duration: int # in minutes
    capacity: int
    notes: str = ""
    id: int | None = None


@dataclass
class Student(BaseModel):
    """Student data model"""
    display_name: str
    username: str
    registration_date: date
    notes: str = ""
    id: int | None = None


@dataclass
class YogaClassBooking(BaseModel):
    """Yoga class booking data model"""
    class_id: int
    student_id: int
    approved: bool = False
    canceled: bool = False
    cancel_date: date = None
    canceled_by: str = ''
    notes: str = ''
    id: int | None = None


class AdminRepository(BaseRepository):
    """Repository for admin operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "admins")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            registration_date DATE NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def add_admin(self, admin: Admin) -> int:
        """Insert a new admin with validation
        returns admin.id"""
        searched_admin = self.get_admins_by_username(admin.username)
        if searched_admin:
            logger.info("admin with username %s already exist",admin.username)
            return searched_admin.id
        return self.insert(admin.to_dict())

    def get_admins_by_username(self, username: str) -> Admin | None:
        """Get admin by username"""
        query = """
            SELECT id, username, display_name, registration_date, payment_end_date, notes FROM %s
            WHERE username = "%s"
        """ %(self.table_name, username)
        admin = self.db.execute_query(query).fetchone()
        if admin:
            return Admin.from_dict(dict(admin))
        return None


class TeacherRepository(BaseRepository):
    """Repository for teacher operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "teachers")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            registration_date DATE NOT NULL,
            payment_end_date DATE NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def add_teacher(self, teacher: Teacher) -> int:
        """Insert a new teacher with validation
        returns teacher.id"""
        searched_teacher = self.get_teachers_by_username(teacher.username)
        if searched_teacher:
            logger.info("teacher with username %s already exist",teacher.username)
            return searched_teacher.id
        return self.insert(teacher.to_dict())

    def get_teachers_by_username(self, username: str) -> Teacher | None:
        """Get teacher by username"""
        query = """
            SELECT id, username, display_name, registration_date, payment_end_date, notes FROM %s
            WHERE username = "%s"
        """ %(self.table_name, username)
        teacher = self.db.execute_query(query).fetchone()
        if teacher:
            return Teacher.from_dict(dict(teacher))
        return None

    def get_teachers_by_payment_status(self, active: bool = True) -> list[Teacher]:
        """Get teachers with active/expired payments"""
        comparison = ">=" if active else "<"
        query = f"""
            SELECT * FROM {self.table_name}
            WHERE payment_end_date {comparison} CURRENT_DATE
            ORDER BY payment_end_date DESC
        """
        cursor = self.db.execute_query(query)
        return [Teacher.from_dict(dict(row)) for row in cursor.fetchall()]


class StudioRepository(BaseRepository):
    """Repository for studio operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "studios")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            address TEXT NOT NULL,
            has_shower BOOLEAN NOT NULL DEFAULT 0,
            added_date DATE NOT NULL,
            capacity INT NOT NULL DEFAULT 0,
            notes TEXT DEFAULT ''
        """)

    def get_studio_by_name(self, name: str) -> Studio | None:
        """Get studio by name"""
        query = f"""
            SELECT id, name, address, has_shower, added_date, capacity, notes FROM {self.table_name}
            WHERE name = "{name}"
        """
        studio = self.db.execute_query(query).fetchone()
        if studio:
            return Studio.from_dict(dict(studio))
        return None

    def add_studio(self, studio: Studio) -> int:
        """Insert a new studio with validation
        returns studio.id"""
        searched_studio = self.get_studio_by_name(studio.name)
        if searched_studio:
            logger.info("Studio with name %s already exist", studio.name)
            return searched_studio.id
        return self.insert(studio.to_dict())

    def get_studios_with_showers(self) -> list[Studio]:
        """Get studios that have showers"""
        query = f"SELECT * FROM {self.table_name} WHERE has_shower = 1"
        cursor = self.db.execute_query(query)
        return [Studio.from_dict(dict(row)) for row in cursor.fetchall()]


class YogaClassRepository(BaseRepository):
    """Repository for yoga-classes operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "classes")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            studio_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            start_time DATE NOT NULL,
            duration INTEGER NOT NULL,
            capacity INTEGER NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def get_classes_by_teacher_id(self, teacher_id: int) -> list[YogaClass]:
        query = """
            SELECT id, name, studio_id, teacher_id, start_time, duration, capacity, notes FROM %s
            WHERE teacher_id = "%s"
            AND start_time >= CURRENT_DATE
            ORDER BY start_time
        """ %(self.table_name, teacher_id)
        cursor = self.db.execute_query(query)
        return [YogaClass.from_dict(dict(row)) for row in cursor.fetchall()]

    def add_yoga_class(self, yoga_class: YogaClass) -> int:
        """Insert a new yoga class with validation
        returns yoga class id"""
        teacher_yoga_classes = self.get_classes_by_teacher_id(yoga_class.teacher_id)
        for teacher_yoga_class in teacher_yoga_classes:
            if yoga_class.start_time == teacher_yoga_class.start_time:
                logger.info("yoga class on %s already exist", yoga_class.start_time)
                return teacher_yoga_class.id
        return self.insert(yoga_class.to_dict())

    def get_class_by_studio_id(self, studio_id: int) -> list[YogaClass]:
        query = """
            SELECT id, name, studio_id, teacher_id, start_time, duration, capacity, notes FROM %s
            WHERE studio_id = "%s"
            AND start_time >= CURRENT_DATE
            ORDER BY start_time
        """ %(self.table_name, studio_id)
        cursor = self.db.execute_query(query)
        return [YogaClass.from_dict(dict(row)) for row in cursor.fetchall()]


class StudentRepository(BaseRepository):
    """Repository for student operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "students")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            registration_date DATE NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def get_student_by_username(self, username: str) -> Student | None:
        """Get student by username"""
        query = """
            SELECT id, username, display_name, registration_date, notes FROM %s
            WHERE username = "%s"
        """ %(self.table_name, username)
        student = self.db.execute_query(query).fetchone()
        if student:
            return Student.from_dict(dict(student))
        return None

    def add_student(self, student: Student) -> int:
        """Insert a new student with validation
        returns student.id"""
        searched_student = self.get_student_by_username(student.username)
        if searched_student:
            logger.info("student with username %s already exist",student.username)
            return searched_student.id
        return self.insert(student.to_dict())

    def get_recent_students(self, days: int = 30) -> list[Student]:
        """Get students registered in last N days"""
        query = f"""
            SELECT * FROM {self.table_name}
            WHERE registration_date >= date('now', '-{days} days')
        """
        cursor = self.db.execute_query(query)
        return [Student.from_dict(dict(row)) for row in cursor.fetchall()]


class YogaClassBookingRepository(BaseRepository):
    """Repository for Book place on class for student"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "class_booking")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            approved BOOLEAN NOT NULL DEFAULT 0,
            canceled BOOLEAN NOT NULL DEFAULT 0,
            cancel_date DATE DEFAULT NULL,
            canceled_by TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        """)


    def add_booking(self, booking: YogaClassBooking) -> int:
        """Insert booiking, return bookig id"""
        student_booking = self.get_all_yoga_class_students(booking.class_id)
        if booking.student_id in student_booking.keys():
            logger.info("booking on class id: %s student with id: %s is already exist", booking.class_id, booking.student_id)
            return student_booking[booking.student_id]
        return self.insert(booking.to_dict())        
    
    def approve_student_to_class(self, booking: YogaClassBooking) -> int:
        #TODO: update row about booking, approve
        student_id = booking.student_id
        yoga_class_id = booking.class_id
        query = """
            UPDATE SET approve = 1
            WHERE class_id = "%s" AND student_id = "%s"
        """ %(yoga_class_id, student_id)
        cursor = self.db.execute_query(query)
        return cursor.lastrowid

    def get_all_unaproved_on_yoga_class_students(self, yoga_class_id: int):
        """Get all unaproved on yoga class students"""
        query = f"""
            SELECT class_id, student_id, approved, canceled, cancel_date, canceled_by, notes, id
            WHERE class_id = "{yoga_class_id}"
        """
        cursor = self.db.execute_query(query)
        return [YogaClassBooking.from_dict(dict(row)) for row in cursor.fetchall()]

    def get_all_yoga_class_students(self, yoga_class_id) -> dict[int: int]:
        """
        Return: dict of {stufetn_id: booking_id}
        """
        # TODO: write function get_all_yoga_class_students
        return {yoga_class_id: 1}



def example_usage():
    """Demonstration of how to use these classes"""
    with DatabaseManager("yoga_booking.db") as db:
        # Initialize repositories
        teacher_repo = TeacherRepository(db)
        studio_repo = StudioRepository(db)
        student_repo = StudentRepository(db)

        # Add sample data
        teacher_id = teacher_repo.add_teacher(Teacher(
            username="anna_ballerina",
            display_name="Anna Petrova",
            registration_date=date(2023, 1, 15),
            payment_end_date=date(2024, 1, 15),
            notes="Ballet specialist"
        ))

        teacher2_id = teacher_repo.add_teacher(Teacher(
            username="kate_ballerina",
            display_name="Kate Petrova",
            registration_date=date(2023, 1, 15),
            payment_end_date=date(2030, 1, 15),
            notes="Ballet specialist"
        ))

        studio_id = studio_repo.add_studio(Studio(
            name="Grand Ballet Hall 5",
            address="123 Dance Street",
            has_shower=True,
            capacity = 23,
            added_date=date.today(),
            notes = "Main studio with mirrors"
        ))

        student_id = student_repo.add_student(Student(
            username="little_dancer 5",
            display_name="Maria Ivanova",
            registration_date=date.today()
        ))

        yoga_class_repo = YogaClassRepository(db)
        yoga_class_id = yoga_class_repo.add_yoga_class(YogaClass(
            name = "KD yoga class",
            studio_id = 1,
            teacher_id = 1,
            start_time = date(year=2025, month=12, day=12),
            duration = 90,
            capacity = 12
        ))


        yoga_class_booking_repo = YogaClassBookingRepository(db)
        yoga_class_booking_id = yoga_class_booking_repo.add_booking(YogaClassBooking(
            class_id = 1,
            student_id = 1
        ))
        yoga_class_booking_repo.approve_student_to_class(YogaClassBooking(
            class_id = 1,
            student_id = 1
        ))


        # Retrieve data
        active_teachers = teacher_repo.get_teachers_by_payment_status()
        anna_petrova = teacher_repo.get_teachers_by_username("anna_ballerina")
        studios_with_showers = studio_repo.get_studios_with_showers()
        new_students = student_repo.get_recent_students(7)

        print(f"Active teachers: {active_teachers}")
        print(f"Studios with showers: {studios_with_showers}")
        print(f"New students: {new_students}")
        if anna_petrova:
            print("Teacher by username:", anna_petrova.username)
        print(f"Yoga class id: {yoga_class_id}")
        print(f"Yoga class booking id: {yoga_class_booking_id}")

if __name__ == "__main__":
    example_usage()
