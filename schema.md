
# Student Database Schema

## Database Name
students.db

## Table 1: Courses

Stores information about available courses.

| Column Name | Data Type | Description |
|---|---|---|
| course_id | INTEGER | Primary Key |
| course_name | TEXT | Unique course name |

## Table 2: Students

Stores student personal and academic information.

| Column Name | Data Type | Description |
|---|---|---|
| student_id | INTEGER | Primary Key |
| name | TEXT | Student full name |
| email | TEXT | Unique email address |
| course_id | INTEGER | Foreign Key referencing Courses(course_id) |
| status | TEXT | Active or Inactive |
| joining_date | DATE | Admission date |
| city | TEXT | Student city |

## Table 3: Fees

Stores student fee receipt information.

| Column Name | Data Type | Description |
|---|---|---|
| fee_id | INTEGER | Primary Key |
| student_id | INTEGER | Foreign Key referencing Students(student_id) |
| receipt_number | TEXT | Fee receipt number |
| amount | REAL | Fee amount |
| payment_date | DATE | Payment date |
| payment_mode | TEXT | Mode of payment |

## Relationships

1. One Course can have multiple Students.
2. Each Student belongs to one Course.
3. One Student can have multiple Fees records.
4. Each Fees record belongs to one Student.

## Business Rules

1. Each student has a unique student_id.
2. Each email address must be unique.
3. Each course has a unique course_id.
4. Student status can be Active or Inactive.
5. Students.course_id references Courses.course_id.
6. Fees.student_id references Students.student_id.
7. Fee amount must be greater than zero.

## Example Queries

1. Count all students.
2. Count active students.
3. Count inactive students.
4. Count students course-wise.
5. Find students city-wise.
6. Find students who joined in the last 6 months.
7. Display students with their course names using JOIN.
8. Find total fees paid by each student.
9. Calculate total fee collection.
10. Find students who have not paid any fees.
