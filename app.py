
import streamlit as st
import sqlite3
import os
import re
import json
import pandas as pd
import plotly.express as px

from pathlib import Path
from datetime import date
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Database Assistant",
    page_icon="🤖",
    layout="wide"
)


# ============================================================
# LOAD CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "students.db"
SCHEMA_PATH = BASE_DIR / "schema.md"

load_dotenv(BASE_DIR / ".env")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("Gemini API key not found. Please configure GEMINI_API_KEY.")
    st.stop()

if not DATABASE_PATH.exists():
    st.error("students.db database file not found.")
    st.stop()

if not SCHEMA_PATH.exists():
    st.error("schema.md file not found.")
    st.stop()


# ============================================================
# INITIALIZE GEMINI AND QDRANT
# ============================================================

@st.cache_resource
def initialize_services(api_key):

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=120000)
    )

    qdrant = QdrantClient(":memory:")

    with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
        schema_text = file.read()

    qdrant.create_collection(
        collection_name="student_schema",
        vectors_config=VectorParams(
            size=768,
            distance=Distance.COSINE
        )
    )

    embedding_response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=schema_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768
        )
    )

    embedding = embedding_response.embeddings[0].values

    qdrant.upsert(
        collection_name="student_schema",
        points=[
            PointStruct(
                id=1,
                vector=embedding,
                payload={
                    "text": schema_text,
                    "source": "schema.md"
                }
            )
        ]
    )

    return client, qdrant


try:
    client, qdrant = initialize_services(api_key)

except Exception as e:
    st.error(f"AI initialization failed: {e}")
    st.stop()


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_database_connection():
    return sqlite3.connect(str(DATABASE_PATH))


# ============================================================
# HEADER
# ============================================================

st.title("🤖 AI-Powered Database Assistant")

st.write(
    "Ask questions about student records in simple English. "
    "AI will generate SQL and retrieve answers from your database."
)

st.divider()


# ============================================================
# DASHBOARD STATISTICS
# ============================================================

conn = get_database_connection()
cursor = conn.cursor()

total = cursor.execute(
    "SELECT COUNT(*) FROM Students"
).fetchone()[0]

active = cursor.execute(
    "SELECT COUNT(*) FROM Students WHERE status='Active'"
).fetchone()[0]

inactive = cursor.execute(
    "SELECT COUNT(*) FROM Students WHERE status='Inactive'"
).fetchone()[0]

mca = cursor.execute(
    "SELECT COUNT(*) FROM Students WHERE course='MCA'"
).fetchone()[0]

conn.close()

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Students", total)
col2.metric("Active Students", active)
col3.metric("Inactive Students", inactive)
col4.metric("MCA Students", mca)


# ============================================================
# READ OPERATION - VIEW AND SEARCH STUDENT RECORDS
# ============================================================

st.divider()
st.header("👩‍🎓 Student Records")

st.write(
    "View, search and filter student records stored in the database."
)

read_conn = get_database_connection()

try:

    course_options = pd.read_sql_query(
        """
        SELECT DISTINCT course
        FROM Students
        WHERE course IS NOT NULL AND TRIM(course) != ''
        ORDER BY course
        """,
        read_conn
    )["course"].tolist()

    status_options = pd.read_sql_query(
        """
        SELECT DISTINCT status
        FROM Students
        WHERE status IS NOT NULL AND TRIM(status) != ''
        ORDER BY status
        """,
        read_conn
    )["status"].tolist()

finally:
    read_conn.close()


search_col, course_col, status_col = st.columns(3)

with search_col:
    search_text = st.text_input(
        "🔍 Search Student",
        placeholder="Enter name or email...",
        key="read_search"
    )

with course_col:
    selected_course = st.selectbox(
        "Filter by Course",
        options=["All Courses"] + course_options,
        key="read_course_filter"
    )

with status_col:
    selected_status = st.selectbox(
        "Filter by Status",
        options=["All Statuses"] + status_options,
        key="read_status_filter"
    )


sql = """
    SELECT
        student_id,
        name,
        email,
        course,
        status,
        joining_date,
        city
    FROM Students
    WHERE 1=1
"""

params = []

if search_text.strip():
    sql += " AND (name LIKE ? OR email LIKE ?)"
    search_value = f"%{search_text.strip()}%"
    params.extend([search_value, search_value])

if selected_course != "All Courses":
    sql += " AND course = ?"
    params.append(selected_course)

if selected_status != "All Statuses":
    sql += " AND status = ?"
    params.append(selected_status)

sql += " ORDER BY student_id DESC"

read_conn = get_database_connection()

try:
    students_df = pd.read_sql_query(
        sql,
        read_conn,
        params=params
    )
finally:
    read_conn.close()


st.metric("Matching Student Records", len(students_df))

if not students_df.empty:
    st.dataframe(
        students_df,
        width="stretch",
        hide_index=True
    )
else:
    st.info("No student records found. Try changing your search or filters.")


# ============================================================
# UPDATE OPERATION - EDIT EXISTING STUDENT RECORDS
# ============================================================

st.divider()
st.header("✏️ Update Student Details")

st.write(
    "Select an existing student and update their information."
)

update_conn = get_database_connection()

try:
    update_students = pd.read_sql_query(
        """
        SELECT student_id, name, email
        FROM Students
        ORDER BY student_id
        """,
        update_conn
    )
finally:
    update_conn.close()


# Function to display student name with ID
def format_student_option(student_id):

    student_name = update_students.loc[
        update_students["student_id"] == student_id,
        "name"
    ].iloc[0]

    return f"ID: {student_id} - {student_name}"


if update_students.empty:

    st.info("No student records available to update.")

else:

    student_ids = update_students["student_id"].tolist()

    selected_student_id = st.selectbox(
        "Select Student to Update",
        options=student_ids,
        format_func=format_student_option,
        key="update_student_selection"
    )

    update_conn = get_database_connection()

    try:
        selected_student = update_conn.execute(
            """
            SELECT
                student_id,
                name,
                email,
                course,
                status,
                joining_date,
                city
            FROM Students
            WHERE student_id = ?
            """,
            (selected_student_id,)
        ).fetchone()

    finally:
        update_conn.close()

    if selected_student:

        (
            student_id,
            old_name,
            old_email,
            old_course,
            old_status,
            old_joining_date,
            old_city
        ) = selected_student

        st.info(f"Editing Student ID: {student_id}")

        status_values = ["Active", "Inactive"]

        current_status = (
            old_status
            if old_status in status_values
            else "Active"
        )

        with st.form(key=f"update_student_form_{student_id}"):

            edit_name = st.text_input(
                "Student Name",
                value=old_name or ""
            )

            edit_email = st.text_input(
                "Email Address",
                value=old_email or ""
            )

            edit_course = st.text_input(
                "Course",
                value=old_course or ""
            )

            edit_status = st.selectbox(
                "Student Status",
                options=status_values,
                index=status_values.index(current_status)
            )

            edit_joining_date = st.text_input(
                "Joining Date (YYYY-MM-DD)",
                value=old_joining_date or "",
                placeholder="2026-07-15"
            )

            edit_city = st.text_input(
                "City",
                value=old_city or ""
            )

            update_button = st.form_submit_button(
                "💾 Update Student",
                type="primary"
            )

        if update_button:

            if not edit_name.strip():
                st.error("Student name is required.")

            elif not edit_email.strip():
                st.error("Email address is required.")

            elif not re.match(
                r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                edit_email.strip()
            ):
                st.error("Please enter a valid email address.")

            else:

                try:

                    if edit_joining_date.strip():
                        date.fromisoformat(edit_joining_date.strip())

                    update_conn = get_database_connection()

                    try:

                        update_conn.execute(
                            """
                            UPDATE Students
                            SET
                                name = ?,
                                email = ?,
                                course = ?,
                                status = ?,
                                joining_date = ?,
                                city = ?
                            WHERE student_id = ?
                            """,
                            (
                                edit_name.strip(),
                                edit_email.strip(),
                                edit_course.strip(),
                                edit_status,
                                edit_joining_date.strip() or None,
                                edit_city.strip(),
                                student_id
                            )
                        )

                        update_conn.commit()

                    finally:
                        update_conn.close()

                    st.session_state.update_message = (
                        f"Student {edit_name.strip()} updated successfully!"
                    )

                    st.rerun()

                except ValueError:
                    st.error(
                        "Invalid joining date. Use YYYY-MM-DD format."
                    )

                except sqlite3.IntegrityError:
                    st.error(
                        "This email already belongs to another student."
                    )

                except sqlite3.Error as e:
                    st.error(f"Database error: {e}")

                except Exception as e:
                    st.error(f"Something went wrong: {e}")


if st.session_state.get("update_message"):

    st.success(st.session_state.update_message)
    del st.session_state.update_message


# ============================================================
# DELETE OPERATION - DELETE STUDENT RECORD
# ============================================================

st.divider()
st.header("🗑️ Delete Student Record")

st.write(
    "Select a student record that you want to delete."
)

delete_conn = get_database_connection()

try:
    delete_students = pd.read_sql_query(
        """
        SELECT student_id, name, email
        FROM Students
        ORDER BY student_id
        """,
        delete_conn
    )
finally:
    delete_conn.close()


if delete_students.empty:

    st.info("No student records available to delete.")

else:

    delete_student_ids = delete_students["student_id"].tolist()

    def format_delete_student_option(student_id):

        student_name = delete_students.loc[
            delete_students["student_id"] == student_id,
            "name"
        ].iloc[0]

        return f"ID: {student_id} - {student_name}"

    selected_delete_id = st.selectbox(
        "Select Student to Delete",
        options=delete_student_ids,
        format_func=format_delete_student_option,
        key="delete_student_selection"
    )

    selected_delete_student = delete_students[
        delete_students["student_id"] == selected_delete_id
    ].iloc[0]

    st.warning(
        f"You have selected: {selected_delete_student['name']} "
        f"(ID: {selected_delete_id})"
    )

    confirm_delete = st.checkbox(
        "I confirm that I want to permanently delete this student.",
        key="confirm_delete_student"
    )

    if st.button(
        "🗑️ Delete Student",
        type="primary",
        disabled=not confirm_delete,
        key="delete_student_button"
    ):

        delete_conn = get_database_connection()

        try:

            delete_conn.execute(
                "DELETE FROM Students WHERE student_id = ?",
                (selected_delete_id,)
            )

            delete_conn.commit()

            st.session_state.delete_message = (
                f"Student {selected_delete_student['name']} "
                "deleted successfully!"
            )

            st.rerun()

        except sqlite3.Error as e:

            st.error(f"Database error: {e}")

        finally:
            delete_conn.close()


if st.session_state.get("delete_message"):

    st.success(st.session_state.delete_message)
    del st.session_state.delete_message

# ============================================================
# COURSE-WISE ANALYSIS
# ============================================================

st.divider()
st.subheader("📚 Course-wise Student Distribution")

chart_conn = get_database_connection()

try:
    course_data = pd.read_sql_query(
        """
        SELECT course, COUNT(*) AS total_students
        FROM Students
        GROUP BY course
        ORDER BY total_students DESC
        """,
        chart_conn
    )
finally:
    chart_conn.close()

st.bar_chart(
    course_data,
    x="course",
    y="total_students",
    x_label="Course",
    y_label="Number of Students"
)


# ============================================================
# CITY-WISE ANALYSIS
# ============================================================

st.subheader("🌍 City-wise Student Distribution")

city_conn = get_database_connection()

try:
    city_data = pd.read_sql_query(
        """
        SELECT city, COUNT(*) AS total_students
        FROM Students
        GROUP BY city
        ORDER BY total_students DESC
        """,
        city_conn
    )
finally:
    city_conn.close()

st.bar_chart(
    city_data,
    x="city",
    y="total_students",
    x_label="City",
    y_label="Number of Students"
)


# ============================================================
# STUDENT STATUS ANALYSIS
# ============================================================

st.subheader("📊 Active vs Inactive Students")

status_conn = get_database_connection()

try:
    status_data = pd.read_sql_query(
        """
        SELECT status, COUNT(*) AS total_students
        FROM Students
        GROUP BY status
        """,
        status_conn
    )
finally:
    status_conn.close()

fig = px.pie(
    status_data,
    names="status",
    values="total_students",
    title="Student Status Distribution",
    hole=0.4
)

st.plotly_chart(fig, width="stretch")

st.divider()


# ============================================================
# AI DATABASE QUESTION INPUT
# ============================================================

st.subheader("💬 Ask Your Database")

question = st.text_input(
    "Enter your question:",
    placeholder="Example: How many students are enrolled in MCA?"
)


# ============================================================
# PROCESS DATABASE QUESTION
# ============================================================

if st.button("Generate Answer", type="primary"):

    if not question.strip():

        st.warning("Please enter your question first.")

    else:

        try:

            with st.spinner("Understanding your question..."):

                embedding_response = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=question,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY",
                        output_dimensionality=768
                    )
                )

                query_vector = embedding_response.embeddings[0].values

                search_result = qdrant.query_points(
                    collection_name="student_schema",
                    query=query_vector,
                    limit=1,
                    with_payload=True
                )

                if not search_result.points:
                    st.error("No database schema found in Qdrant.")
                    st.stop()

                schema = search_result.points[0].payload["text"]

                prompt = f"""
You are an expert SQLite SQL query generator.

Database Schema:
{schema}

User Question:
{question}

Instructions:
1. Generate only one valid SQLite SELECT query.
2. Use only existing tables and columns.
3. Never generate INSERT, UPDATE, DELETE, DROP,
   ALTER, CREATE or other modification queries.
4. Return only SQL without explanation or markdown.

SQL Query:
"""

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0
                    )
                )

                if not response.text:
                    raise ValueError("Gemini returned an empty SQL response.")

                sql_query = response.text.strip()

                sql_query = re.sub(
                    r"^```(?:sql)?\s*|\s*```$",
                    "",
                    sql_query,
                    flags=re.IGNORECASE
                ).strip()

            st.subheader("📝 Generated SQL Query")
            st.code(sql_query, language="sql")

            st.subheader("📊 Query Result")

            if not re.match(r"^SELECT\b", sql_query, re.IGNORECASE):
                st.error("Only SELECT queries are allowed.")
                st.stop()

            database = get_database_connection()

            allowed_actions = {
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_RECURSIVE
            }

            def read_only_authorizer(
                action,
                arg1,
                arg2,
                database_name,
                trigger
            ):
                if action in allowed_actions:
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            try:
                database.set_authorizer(read_only_authorizer)

                result_cursor = database.execute(sql_query)
                result = result_cursor.fetchall()

                columns = [
                    description[0]
                    for description in result_cursor.description
                ]

            finally:
                database.close()

            if result:

                st.success("Query executed successfully!")

                result_df = pd.DataFrame(
                    result,
                    columns=columns
                )

                st.dataframe(result_df, width="stretch")

            else:
                st.info("No records found.")

        except Exception as e:
            st.error(f"Something went wrong: {e}")


# ============================================================
# AI IMAGE TO STUDENT FORM
# ============================================================

st.divider()
st.title("📝 AI Student Registration")

st.write(
    "Upload a student form image. AI will extract "
    "the details and automatically fill the registration form."
)


# ============================================================
# SUCCESS MESSAGE AFTER SAVING
# ============================================================

if st.session_state.get("student_save_message"):

    st.success(st.session_state.student_save_message)
    st.balloons()

    del st.session_state.student_save_message


# ============================================================
# IMAGE UPLOAD
# ============================================================

st.subheader("Step 1: Upload Student Image")

uploaded_image = st.file_uploader(
    "Upload Student Form Image",
    type=["png", "jpg", "jpeg"],
    key="student_image"
)


# ============================================================
# IMAGE PREVIEW
# ============================================================

if uploaded_image is not None:

    st.image(
        uploaded_image,
        caption="Uploaded Student Form",
        width=350
    )


# ============================================================
# EXTRACT STUDENT DATA USING GEMINI VISION
# ============================================================

if st.button("🤖 Extract Student Details", type="primary"):

    if uploaded_image is None:

        st.warning("Please upload a student image first.")

    else:

        try:

            with st.spinner("AI is reading student information..."):

                image_part = types.Part.from_bytes(
                    data=uploaded_image.getvalue(),
                    mime_type=uploaded_image.type
                )

                extraction_prompt = """
You are an AI assistant that extracts student
information from uploaded student forms or registers.

Extract the following fields:

{
    "name": "",
    "email": "",
    "course": "",
    "status": "",
    "joining_date": "",
    "city": ""
}

Instructions:
1. Carefully read the uploaded student image.
2. Extract only information visible in the image.
3. Never invent missing information.
4. If a field is missing or unclear, return an empty string.
5. Convert dates into YYYY-MM-DD format if possible.
6. Status must be Active or Inactive only.
7. Return valid JSON only.
"""

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[
                        extraction_prompt,
                        image_part
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json"
                    )
                )

                if not response.text:
                    raise ValueError("Gemini returned an empty response.")

                extracted_data = json.loads(response.text)

                if not isinstance(extracted_data, dict):
                    raise ValueError("AI returned an invalid data structure.")

                required_fields = [
                    "name",
                    "email",
                    "course",
                    "status",
                    "joining_date",
                    "city"
                ]

                for field in required_fields:

                    if extracted_data.get(field) is None:
                        extracted_data[field] = ""

                    extracted_data[field] = str(
                        extracted_data.get(field, "")
                    ).strip()

                extracted_status = extracted_data["status"].lower()

                if extracted_status == "active":
                    extracted_data["status"] = "Active"

                elif extracted_status == "inactive":
                    extracted_data["status"] = "Inactive"

                else:
                    extracted_data["status"] = "Select Status"

                st.session_state.student_form_data = extracted_data
                st.session_state.student_extraction_done = True

                for field in required_fields:
                    st.session_state["student_" + field] = extracted_data[field]

            st.success("Student details extracted successfully!")

        except json.JSONDecodeError:
            st.error("AI returned invalid JSON. Please try again.")

        except Exception as e:
            st.error(f"Image extraction failed: {e}")


# ============================================================
# STUDENT REGISTRATION FORM - CREATE OPERATION
# ============================================================

if st.session_state.get("student_extraction_done", False):

    st.divider()
    st.subheader("Step 2: Preview and Edit Student Details")

    st.info(
        "AI has extracted the following information. "
        "Please review and correct it before saving."
    )

    with st.form("student_registration_form"):

        name = st.text_input(
            "Student Name",
            key="student_name"
        )

        email = st.text_input(
            "Email Address",
            key="student_email"
        )

        course = st.text_input(
            "Course",
            key="student_course"
        )

        status = st.selectbox(
            "Student Status",
            options=["Select Status", "Active", "Inactive"],
            key="student_status"
        )

        joining_date = st.text_input(
            "Joining Date (YYYY-MM-DD)",
            key="student_joining_date",
            placeholder="2026-07-15"
        )

        city = st.text_input(
            "City",
            key="student_city"
        )

        save_student = st.form_submit_button(
            "💾 Save Student to Database",
            type="primary"
        )

    if save_student:

        if not name.strip():
            st.error("Student name is required.")

        elif not email.strip():
            st.error("Email address is required.")

        elif not re.match(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
            email.strip()
        ):
            st.error("Please enter a valid email address.")

        elif status == "Select Status":
            st.error("Please select student status.")

        else:

            try:

                if joining_date.strip():
                    date.fromisoformat(joining_date.strip())

                database = get_database_connection()

                try:

                    database.execute(
                        """
                        INSERT INTO Students
                        (
                            name,
                            email,
                            course,
                            status,
                            joining_date,
                            city
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            name.strip(),
                            email.strip(),
                            course.strip(),
                            status,
                            joining_date.strip() or None,
                            city.strip()
                        )
                    )

                    database.commit()

                finally:
                    database.close()

                st.session_state.student_save_message = (
                    f"Student {name.strip()} added successfully!"
                )

                st.session_state.student_extraction_done = False
                st.session_state.student_form_data = {}

                st.rerun()

            except ValueError:
                st.error(
                    "Invalid joining date. Please use YYYY-MM-DD format."
                )

            except sqlite3.IntegrityError:
                st.error("This email already exists in the database.")

            except sqlite3.Error as e:
                st.error(f"Database error: {e}")

            except Exception as e:
                st.error(f"Something went wrong: {e}")


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "AI Database Assistant | Powered by Gemini, Qdrant, SQLite and Streamlit"
)
