
import sqlite3
import random
from datetime import date, timedelta

# Connect to SQLite database
conn = sqlite3.connect("students.db")
cursor = conn.cursor()

# Create Students table
cursor.execute("""
CREATE TABLE IF NOT EXISTS Students (
    student_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    course TEXT,
    status TEXT,
    joining_date DATE,
    city TEXT
)
""")

# Insert records only if table is empty
cursor.execute("SELECT COUNT(*) FROM Students")
count = cursor.fetchone()[0]

if count == 0:
    first_names = [
        "Isha", "Priya", "Rahul", "Neha", "Harshit",
        "Nandita", "Ananya", "Anmol", "Sneha", "Arjun",
        "Aarav", "Karan", "Pooja", "Vikas", "Simran"
    ]

    last_names = [
        "Rawat", "Verma", "Singh", "Gupta", "Lohani",
        "Roy", "Joshi", "Tyagi", "Rana", "Das"
    ]

    courses = ["MCA", "BCA", "BBA", "MBA", "B.Tech"]
    cities = ["Delhi", "Haldwani", "Dehradun", "Noida", "Jaipur"]

    records = []
    today = date.today()

    for i in range(1, 201):
        name = random.choice(first_names) + " " + random.choice(last_names)
        email = f"student{i}@example.com"
        course = random.choice(courses)
        status = random.choice(["Active", "Inactive"])

        days_ago = random.randint(0, 730)
        joining_date = today - timedelta(days=days_ago)

        city = random.choice(cities)

        records.append((
            i, name, email, course,
            status, joining_date.isoformat(), city
        ))

    cursor.executemany("""
    INSERT INTO Students
    (student_id, name, email, course, status, joining_date, city)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, records)

    conn.commit()
    print("200 student records inserted successfully!")

else:
    print(f"Database already contains {count} students.")

# Display total records
cursor.execute("SELECT COUNT(*) FROM Students")
print("Total Students:", cursor.fetchone()[0])

# Display sample records
cursor.execute("SELECT * FROM Students LIMIT 5")

for row in cursor.fetchall():
    print(row)

conn.close()
