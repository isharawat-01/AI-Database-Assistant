
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "students.db"


def migrate_database():
    connection = sqlite3.connect(str(DATABASE_PATH))

    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        cursor = connection.cursor()

        cursor.execute("BEGIN")

        # Check whether migration has already been completed
        student_columns = [
            row[1] for row in cursor.execute(
                "PRAGMA table_info(Students)"
            ).fetchall()
        ]

        if "course_id" in student_columns:
            print("Students table is already migrated.")
            connection.rollback()
            return

        if "course" not in student_columns:
            raise Exception(
                "Old Students.course column was not found."
            )

        # 1. Create Courses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Courses (
                course_id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_name TEXT NOT NULL UNIQUE
            )
        """)

        # 2. Copy existing course names into Courses
        cursor.execute("""
            INSERT OR IGNORE INTO Courses (course_name)
            SELECT DISTINCT
                COALESCE(NULLIF(TRIM(course), ''), 'Not Specified')
            FROM Students
        """)

        # 3. Rename old Students table
        cursor.execute("""
            ALTER TABLE Students RENAME TO Students_old
        """)

        # 4. Create new Students table with Foreign Key
        cursor.execute("""
            CREATE TABLE Students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                course_id INTEGER NOT NULL,
                status TEXT,
                joining_date DATE,
                city TEXT,
                FOREIGN KEY (course_id)
                    REFERENCES Courses(course_id)
            )
        """)

        # 5. Transfer existing student records
        cursor.execute("""
            INSERT INTO Students (
                student_id,
                name,
                email,
                course_id,
                status,
                joining_date,
                city
            )
            SELECT
                old.student_id,
                old.name,
                old.email,
                courses.course_id,
                old.status,
                old.joining_date,
                old.city
            FROM Students_old AS old
            JOIN Courses AS courses
                ON courses.course_name =
                   COALESCE(
                       NULLIF(TRIM(old.course), ''),
                       'Not Specified'
                   )
        """)

        # 6. Remove old table
        cursor.execute("DROP TABLE Students_old")

        # 7. Create Fees table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Fees (
                fee_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                receipt_number TEXT,
                amount REAL CHECK (amount > 0),
                payment_date DATE,
                payment_mode TEXT,
                FOREIGN KEY (student_id)
                    REFERENCES Students(student_id)
                    ON DELETE CASCADE
            )
        """)

        connection.commit()

        # Enable foreign key enforcement
        cursor.execute("PRAGMA foreign_keys = ON")

        # Verify foreign key integrity
        errors = cursor.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if errors:
            raise Exception(f"Foreign key errors: {errors}")

        print("Database migration completed successfully!")

        print(
            "Courses:",
            cursor.execute(
                "SELECT COUNT(*) FROM Courses"
            ).fetchone()[0]
        )

        print(
            "Students:",
            cursor.execute(
                "SELECT COUNT(*) FROM Students"
            ).fetchone()[0]
        )

        print(
            "Fees:",
            cursor.execute(
                "SELECT COUNT(*) FROM Fees"
            ).fetchone()[0]
        )

    except Exception as error:
        connection.rollback()
        print("Migration failed:", error)

    finally:
        connection.close()


if __name__ == "__main__":
    migrate_database()
