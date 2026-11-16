# AI Database Assistant – Project Demonstration

**Opening**

Good morning Sir.

Today, I am going to demonstrate my project, AI Database Assistant.

This project is designed to simplify student database management using Artificial Intelligence. It allows users to extract information from student forms and fee receipts, manage relational student records, and ask database questions in natural language.

**1. Dashboard**

First, this is the main dashboard.

It displays important student statistics such as total students, active students, inactive students, course-wise information, and fee collection.

**2. Student Form Image Extraction**

Now, I will demonstrate AI-based student registration.

Instead of manually entering every detail, I can upload a student registration form image.

Gemini AI extracts the student's name, email, course, status, joining date, and city.

The extracted information is automatically filled into the registration form, where the user can review it before saving.

**3. Fee Receipt Extraction**

Next, I will upload a fee receipt image.

The AI extracts the receipt number, student name, payment date, payment mode, and total amount.

The user can review the extracted details before saving.

**4. Student and Fee Database Relationship**

When I save the student and fee receipt together, the application inserts the student record first and obtains its actual database ID.

The fee record is then linked to that student using the Foreign Key relationship.

This maintains data consistency.

**5. Fee Records**

Here, I can view fee records associated with students.

**6. Ask Your Database**

One of the main features is natural language database querying.

Instead of writing SQL manually, I can ask questions in English or Hinglish.

For example:

- How many students are in MCA?
- Isha Rawat ki fees kitni hai?
- Show student names with their course names.

The AI generates a SQL query, executes it in read-only mode, and displays the result.

**7. Voice-Based Database Query**

The application also provides voice-based querying.

Users can record their questions instead of typing them.

The speech is processed, converted into a database question, and used to generate SQL.

**8. Database Relationships**

The project contains three relational tables: Courses, Students, and Fees.

Students are connected to Courses through course_id, while Fees are connected to Students through student_id.

I have also tested SQL JOIN and LEFT JOIN queries to verify these relationships.

**Closing**

This project combines AI-based information extraction, relational database management, and natural language interaction in a single application.

Thank you.
