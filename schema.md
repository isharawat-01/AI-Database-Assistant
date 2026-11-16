
# Student Database Schema

## Database Name
students.db

## Table Name
Students

## Table Description
The Students table stores information about students,
including their personal details, course information,
current status, joining date, and city.

## Columns

| Column Name | Data Type | Description |
|---|---|---|
| student_id | INTEGER | Unique ID of each student. Primary Key. |
| name | TEXT | Full name of the student. |
| email | TEXT | Unique email address of the student. |
| course | TEXT | Course enrolled by the student. |
| status | TEXT | Current student status: Active or Inactive. |
| joining_date | DATE | Date when the student joined. |
| city | TEXT | City where the student belongs. |

## Business Rules

1. Each student has a unique student_id.
2. Each email address must be unique.
3. Student status can be Active or Inactive.
4. Joining date represents the admission date.

## Example Queries

1. Count all students.
2. Count active students.
3. Count inactive students.
4. Find students who joined in the last 6 months.
5. Count students course-wise.
6. Find students city-wise.
