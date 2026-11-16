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
# CONFIGURATION
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
# GEMINI AND QDRANT
# ============================================================

@st.cache_resource
def initialize_services(key):
    gemini_client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=120000)
    )

    vector_db = QdrantClient(":memory:")

    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    vector_db.create_collection(
        collection_name="student_schema",
        vectors_config=VectorParams(size=768, distance=Distance.COSINE)
    )

    embedding_response = gemini_client.models.embed_content(
        model="gemini-embedding-001",
        contents=schema,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768
        )
    )

    vector_db.upsert(
        collection_name="student_schema",
        points=[
            PointStruct(
                id=1,
                vector=embedding_response.embeddings[0].values,
                payload={"text": schema, "source": "schema.md"}
            )
        ]
    )
    return gemini_client, vector_db


try:
    client, qdrant = initialize_services(api_key)
except Exception as error:
    st.error(f"AI initialization failed: {error}")
    st.stop()


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_database_connection():
    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_course_rows():
    connection = get_database_connection()
    try:
        return connection.execute(
            "SELECT course_id, course_name FROM Courses ORDER BY course_name"
        ).fetchall()
    finally:
        connection.close()


def get_schema_context(question):
    embedding = client.models.embed_content(
        model="gemini-embedding-001",
        contents=question,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768
        )
    )
    result = qdrant.query_points(
        collection_name="student_schema",
        query=embedding.embeddings[0].values,
        limit=1,
        with_payload=True
    )
    if not result.points:
        raise ValueError("No database schema found.")
    return result.points[0].payload["text"]


def generate_sql(question):
    schema = get_schema_context(question)
    prompt = f"""
You are an expert SQLite SQL query generator.
Database schema:
{schema}

User question:
{question}

Rules:
1. Generate exactly one valid SQLite SELECT query.
2. Use only tables and columns in the schema.
3. Use JOINs when the question needs related table information.
4. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE or other write queries.
5. Return SQL only, without markdown or explanation.
"""
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0)
    )
    if not response.text:
        raise ValueError("Gemini returned an empty SQL response.")

    sql_query = re.sub(
        r"^```(?:sql)?\s*|\s*```$",
        "",
        response.text.strip(),
        flags=re.IGNORECASE
    ).strip()

    if not re.match(r"^SELECT\b", sql_query, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    return sql_query


def execute_read_only_query(sql_query):
    connection = get_database_connection()
    allowed_actions = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE
    }

    def read_only_authorizer(action, arg1, arg2, database_name, trigger):
        if action in allowed_actions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    try:
        connection.set_authorizer(read_only_authorizer)
        cursor = connection.execute(sql_query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        connection.close()


def display_query_result(question):
    with st.spinner("AI is understanding your question and generating SQL..."):
        sql_query = generate_sql(question)

    st.subheader("📝 Generated SQL Query")
    st.code(sql_query, language="sql")

    with st.spinner("Executing query safely..."):
        result_df = execute_read_only_query(sql_query)

    st.subheader("📊 Query Result")
    if result_df.empty:
        st.info("No records found.")
    else:
        st.success("Query executed successfully!")
        st.dataframe(result_df, width="stretch", hide_index=True)


def extract_json_from_response(response):
    if not response.text:
        raise ValueError("Gemini returned an empty response.")
    data = json.loads(response.text)
    if not isinstance(data, dict):
        raise ValueError("AI returned an invalid data structure.")
    return data


# ============================================================
# HEADER
# ============================================================

st.title("🤖 AI-Powered Database Assistant")
st.write(
    "Ask questions about student and fee records in English or Hinglish. "
    "AI generates safe SQL queries and retrieves answers from SQLite."
)
st.divider()


# ============================================================
# DATABASE STRUCTURE CHECK
# ============================================================

try:
    connection = get_database_connection()
    table_names = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    connection.close()

    required_tables = {"Students", "Courses", "Fees"}
    if not required_tables.issubset(table_names):
        st.error(
            "Database migration is not complete. Please run "
            "`python migrate_database.py` after confirming your backup."
        )
        st.stop()
except sqlite3.Error as error:
    st.error(f"Database error: {error}")
    st.stop()


# ============================================================
# DASHBOARD STATISTICS
# ============================================================

connection = get_database_connection()
total_students = connection.execute(
    "SELECT COUNT(*) FROM Students"
).fetchone()[0]
active_students = connection.execute(
    "SELECT COUNT(*) FROM Students WHERE status='Active'"
).fetchone()[0]
inactive_students = connection.execute(
    "SELECT COUNT(*) FROM Students WHERE status='Inactive'"
).fetchone()[0]
mca_students = connection.execute(
    """
    SELECT COUNT(*)
    FROM Students s
    JOIN Courses c ON s.course_id = c.course_id
    WHERE LOWER(c.course_name) = 'mca'
    """
).fetchone()[0]
total_fee_collection = connection.execute(
    "SELECT COALESCE(SUM(amount), 0) FROM Fees"
).fetchone()[0]
connection.close()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Students", total_students)
col2.metric("Active Students", active_students)
col3.metric("Inactive Students", inactive_students)
col4.metric("MCA Students", mca_students)
col5.metric("Fee Collection", f"₹{total_fee_collection:,.0f}")


# ============================================================
# STUDENT RECORDS - READ, SEARCH AND FILTER
# ============================================================

st.divider()
st.header("👩‍🎓 Student Records")
st.write("View, search and filter student records stored in the database.")

connection = get_database_connection()
course_rows = connection.execute(
    "SELECT course_id, course_name FROM Courses ORDER BY course_name"
).fetchall()
status_options = [
    row[0] for row in connection.execute(
        """
        SELECT DISTINCT status FROM Students
        WHERE status IS NOT NULL AND TRIM(status) != ''
        ORDER BY status
        """
    ).fetchall()
]
connection.close()

course_name_by_id = {row[0]: row[1] for row in course_rows}
course_id_by_name = {row[1]: row[0] for row in course_rows}
course_names = list(course_id_by_name.keys())

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
        ["All Courses"] + course_names,
        key="read_course_filter"
    )
with status_col:
    selected_status = st.selectbox(
        "Filter by Status",
        ["All Statuses"] + status_options,
        key="read_status_filter"
    )

student_sql = """
SELECT s.student_id, s.name, s.email, c.course_name AS course,
       s.status, s.joining_date, s.city
FROM Students s
JOIN Courses c ON s.course_id = c.course_id
WHERE 1=1
"""
student_params = []

if search_text.strip():
    student_sql += " AND (s.name LIKE ? OR s.email LIKE ?)"
    search_value = f"%{search_text.strip()}%"
    student_params.extend([search_value, search_value])

if selected_course != "All Courses":
    student_sql += " AND c.course_name = ?"
    student_params.append(selected_course)

if selected_status != "All Statuses":
    student_sql += " AND s.status = ?"
    student_params.append(selected_status)

student_sql += " ORDER BY s.student_id DESC"

connection = get_database_connection()
students_df = pd.read_sql_query(student_sql, connection, params=student_params)
connection.close()

st.metric("Matching Student Records", len(students_df))
if not students_df.empty:
    st.dataframe(students_df, width="stretch", hide_index=True)
else:
    st.info("No student records found. Try changing your search or filters.")


# ============================================================
# UPDATE STUDENT
# ============================================================

st.divider()
st.header("✏️ Update Student Details")

connection = get_database_connection()
update_students = pd.read_sql_query(
    "SELECT student_id, name FROM Students ORDER BY student_id",
    connection
)
connection.close()

if update_students.empty:
    st.info("No student records available to update.")
else:
    def format_student_option(student_id):
        row = update_students.loc[
            update_students["student_id"] == student_id
        ].iloc[0]
        return f"ID: {student_id} - {row['name']}"

    selected_student_id = st.selectbox(
        "Select Student to Update",
        update_students["student_id"].tolist(),
        format_func=format_student_option,
        key="update_student_selection"
    )

    connection = get_database_connection()
    selected_student = connection.execute(
        """
        SELECT s.student_id, s.name, s.email, s.course_id,
               s.status, s.joining_date, s.city
        FROM Students s WHERE s.student_id = ?
        """,
        (selected_student_id,)
    ).fetchone()
    connection.close()

    if selected_student:
        (
            student_id, old_name, old_email, old_course_id,
            old_status, old_joining_date, old_city
        ) = selected_student

        current_course_index = 0
        course_ids = [row[0] for row in course_rows]
        if old_course_id in course_ids:
            current_course_index = course_ids.index(old_course_id)

        status_values = ["Active", "Inactive"]
        current_status = old_status if old_status in status_values else "Active"

        with st.form(key=f"update_student_form_{student_id}"):
            edit_name = st.text_input("Student Name", value=old_name or "")
            edit_email = st.text_input("Email Address", value=old_email or "")
            edit_course_name = st.selectbox(
                "Course",
                options=course_names,
                index=current_course_index
            )
            edit_status = st.selectbox(
                "Student Status",
                status_values,
                index=status_values.index(current_status)
            )
            edit_joining_date = st.text_input(
                "Joining Date (YYYY-MM-DD)",
                value=old_joining_date or "",
                placeholder="2026-07-15"
            )
            edit_city = st.text_input("City", value=old_city or "")
            update_button = st.form_submit_button(
                "💾 Update Student", type="primary"
            )

        if update_button:
            if not edit_name.strip():
                st.error("Student name is required.")
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", edit_email.strip()):
                st.error("Please enter a valid email address.")
            else:
                try:
                    if edit_joining_date.strip():
                        date.fromisoformat(edit_joining_date.strip())

                    connection = get_database_connection()
                    connection.execute(
                        """
                        UPDATE Students
                        SET name=?, email=?, course_id=?, status=?,
                            joining_date=?, city=?
                        WHERE student_id=?
                        """,
                        (
                            edit_name.strip(), edit_email.strip(),
                            course_id_by_name[edit_course_name], edit_status,
                            edit_joining_date.strip() or None,
                            edit_city.strip(), student_id
                        )
                    )
                    connection.commit()
                    connection.close()
                    st.success(f"Student {edit_name.strip()} updated successfully!")
                    st.rerun()
                except ValueError:
                    st.error("Invalid joining date. Use YYYY-MM-DD format.")
                except sqlite3.IntegrityError:
                    st.error("This email already belongs to another student.")
                except sqlite3.Error as error:
                    st.error(f"Database error: {error}")


# ============================================================
# DELETE STUDENT
# ============================================================

st.divider()
st.header("🗑️ Delete Student Record")

connection = get_database_connection()
delete_students = pd.read_sql_query(
    "SELECT student_id, name FROM Students ORDER BY student_id",
    connection
)
connection.close()

if delete_students.empty:
    st.info("No student records available to delete.")
else:
    def format_delete_student_option(student_id):
        row = delete_students.loc[
            delete_students["student_id"] == student_id
        ].iloc[0]
        return f"ID: {student_id} - {row['name']}"

    selected_delete_id = st.selectbox(
        "Select Student to Delete",
        delete_students["student_id"].tolist(),
        format_func=format_delete_student_option,
        key="delete_student_selection"
    )
    selected_delete_student = delete_students[
        delete_students["student_id"] == selected_delete_id
    ].iloc[0]

    st.warning(
        f"Selected: {selected_delete_student['name']} "
        f"(ID: {selected_delete_id}). Related fee records will also be deleted."
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
        connection = get_database_connection()
        try:
            connection.execute(
                "DELETE FROM Students WHERE student_id=?",
                (selected_delete_id,)
            )
            connection.commit()
            st.success("Student and linked fee records deleted successfully.")
            st.rerun()
        except sqlite3.Error as error:
            st.error(f"Database error: {error}")
        finally:
            connection.close()


# ============================================================
# COURSE, CITY AND STATUS ANALYSIS
# ============================================================

st.divider()
st.subheader("📚 Course-wise Student Distribution")

connection = get_database_connection()
course_data = pd.read_sql_query(
    """
    SELECT c.course_name AS course, COUNT(s.student_id) AS total_students
    FROM Courses c
    LEFT JOIN Students s ON s.course_id = c.course_id
    GROUP BY c.course_id, c.course_name
    ORDER BY total_students DESC
    """,
    connection
)
city_data = pd.read_sql_query(
    """
    SELECT city, COUNT(*) AS total_students
    FROM Students GROUP BY city ORDER BY total_students DESC
    """,
    connection
)
status_data = pd.read_sql_query(
    """
    SELECT status, COUNT(*) AS total_students
    FROM Students GROUP BY status
    """,
    connection
)
connection.close()

if not course_data.empty:
    st.bar_chart(
        course_data, x="course", y="total_students",
        x_label="Course", y_label="Number of Students"
    )

st.subheader("🌍 City-wise Student Distribution")
if not city_data.empty:
    st.bar_chart(
        city_data, x="city", y="total_students",
        x_label="City", y_label="Number of Students"
    )

st.subheader("📊 Active vs Inactive Students")
if not status_data.empty:
    status_fig = px.pie(
        status_data, names="status", values="total_students",
        title="Student Status Distribution", hole=0.4
    )
    st.plotly_chart(status_fig, width="stretch")


# ============================================================
# FEES RECORDS
# ============================================================

st.divider()
st.header("💰 Fee Records")

connection = get_database_connection()
fees_df = pd.read_sql_query(
    """
    SELECT f.fee_id, s.student_id, s.name AS student_name,
           f.receipt_number, f.amount, f.payment_date, f.payment_mode
    FROM Fees f
    JOIN Students s ON s.student_id = f.student_id
    ORDER BY f.fee_id DESC
    """,
    connection
)
connection.close()

if fees_df.empty:
    st.info("No fee receipts have been added yet.")
else:
    st.dataframe(fees_df, width="stretch", hide_index=True)


# ============================================================
# ASK YOUR DATABASE - ENGLISH AND HINGLISH
# ============================================================

st.divider()
st.header("💬 Ask Your Database")
st.caption(
    "Examples: How many students are in MCA? | MCA ke kitne students hain? "
    "| Rahul ki fees kitni hai?"
)

question = st.text_input(
    "Enter your question:",
    placeholder="MCA ke kitne students hain?",
    key="typed_database_question"
)

if st.button("Generate Answer", type="primary", key="typed_query_button"):
    if not question.strip():
        st.warning("Please enter your question first.")
    else:
        try:
            display_query_result(question.strip())
        except Exception as error:
            st.error(f"Unable to process the question: {error}")


# ============================================================
# VOICE-TO-TEXT DATABASE QUERY
# ============================================================

st.divider()
st.header("🎙️ Ask Your Database by Voice")
st.write(
    "Record your question in English or Hinglish. Gemini will understand "
    "the speech, generate a read-only SQL query and show the database result."
)

audio_value = st.audio_input("Record your database question")

if audio_value is not None:
    st.audio(audio_value)
    if st.button("🤖 Process Voice Question", type="primary"):
        try:
            with st.spinner("AI is listening to your question..."):
                audio_part = types.Part.from_bytes(
                    data=audio_value.getvalue(),
                    mime_type="audio/wav"
                )
                voice_prompt = """
Listen to the attached audio. It contains a user asking a question about
a student and fee database, possibly in English or Hinglish.
Return valid JSON only with this structure:
{
  "transcription": "exact words spoken",
  "question_in_english": "same question expressed clearly in English"
}
Do not invent information. If speech is unclear, say so in the transcription.
"""
                voice_response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[voice_prompt, audio_part],
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json"
                    )
                )
                voice_data = extract_json_from_response(voice_response)

            transcript = str(voice_data.get("transcription", "")).strip()
            interpreted_question = str(
                voice_data.get("question_in_english", "")
            ).strip()

            st.subheader("🗣️ Voice Transcription")
            st.write(transcript or "No clear speech detected.")

            if interpreted_question:
                st.subheader("🔎 Understood Question")
                st.write(interpreted_question)
                display_query_result(interpreted_question)
            else:
                st.warning("Could not understand the voice question. Please record again.")
        except Exception as error:
            st.error(f"Voice processing failed: {error}")


# ============================================================
# AI STUDENT REGISTRATION - IMAGE EXTRACTION
# ============================================================

st.divider()
st.title("📝 AI Student Registration")
st.write(
    "Upload a student form image. AI extracts the details, and you can "
    "review them before saving the student."
)

if st.session_state.get("student_save_message"):
    st.success(st.session_state.student_save_message)
    del st.session_state.student_save_message

st.subheader("Step 1: Upload Student Form Image")
uploaded_image = st.file_uploader(
    "Upload Student Form Image",
    type=["png", "jpg", "jpeg"],
    key="student_image"
)

if uploaded_image is not None:
    st.image(uploaded_image, caption="Uploaded Student Form", width=350)

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
Extract only visible student information from this form.
Return valid JSON only:
{
  "name": "",
  "email": "",
  "course": "",
  "status": "",
  "joining_date": "",
  "city": ""
}
Rules:
- Never invent missing values.
- Use empty string if a value is missing or unclear.
- Format dates as YYYY-MM-DD where possible.
- Status must be Active or Inactive, otherwise empty.
"""
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[extraction_prompt, image_part],
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json"
                    )
                )
                extracted = extract_json_from_response(response)

            for field in ["name", "email", "course", "status", "joining_date", "city"]:
                extracted[field] = str(extracted.get(field) or "").strip()

            if extracted["status"].lower() == "active":
                extracted["status"] = "Active"
            elif extracted["status"].lower() == "inactive":
                extracted["status"] = "Inactive"
            else:
                extracted["status"] = "Select Status"

            st.session_state.student_form_data = extracted
            st.session_state.student_extraction_done = True

            st.session_state.student_name = extracted["name"]
            st.session_state.student_email = extracted["email"]
            st.session_state.student_status = extracted["status"]
            st.session_state.student_joining_date = extracted["joining_date"]
            st.session_state.student_city = extracted["city"]

            matching_course = next(
                (
                    name for name in course_names
                    if name.strip().casefold() == extracted["course"].strip().casefold()
                ),
                None
            )
            st.session_state.student_course = (
                matching_course if matching_course else "-- Select a course --"
            )
            st.success("Student details extracted successfully!")
            if extracted["course"] and not matching_course:
                st.warning(
                    f"AI extracted course '{extracted['course']}', but it does not "
                    "match a course in the Courses table. Please select the correct "
                    "course manually; AI has not selected a different course."
                )
        except Exception as error:
            st.error(f"Image extraction failed: {error}")


# ============================================================
# FEE RECEIPT EXTRACTION
# ============================================================

st.subheader("Step 2: Upload Fee Receipt (Optional)")
uploaded_receipt = st.file_uploader(
    "Upload Fee Receipt Image",
    type=["png", "jpg", "jpeg"],
    key="fee_receipt_image"
)

if uploaded_receipt is not None:
    st.image(uploaded_receipt, caption="Uploaded Fee Receipt", width=350)

if st.button("🧾 Extract Fee Receipt Details"):
    if uploaded_receipt is None:
        st.warning("Please upload a fee receipt first.")
    else:
        try:
            with st.spinner("AI is reading fee receipt details..."):
                receipt_part = types.Part.from_bytes(
                    data=uploaded_receipt.getvalue(),
                    mime_type=uploaded_receipt.type
                )
                receipt_prompt = """
Read the uploaded fee receipt. Return valid JSON only:
{
  "receipt_number": "",
  "student_name": "",
  "student_reference": "",
  "course": "",
  "payment_date": "",
  "payment_mode": "",
  "tuition_fee": "",
  "development_fee": "",
  "library_fee": "",
  "total_amount": ""
}
Rules:
- Extract only information visible on the receipt.
- Never invent missing information.
- Amounts must be numeric values without currency symbols or commas.
- Date should be YYYY-MM-DD if possible.
- student_reference is only a printed reference; it is NOT the database student_id.
- If a value is unclear or absent, return an empty string.
"""
                receipt_response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[receipt_prompt, receipt_part],
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json"
                    )
                )
                receipt_data = extract_json_from_response(receipt_response)

            st.session_state.fee_receipt_data = receipt_data
            st.session_state.fee_receipt_number = str(
                receipt_data.get("receipt_number") or ""
            )
            st.session_state.fee_payment_date = str(
                receipt_data.get("payment_date") or ""
            )
            st.session_state.fee_payment_mode = str(
                receipt_data.get("payment_mode") or ""
            )
            st.session_state.fee_total_amount = str(
                receipt_data.get("total_amount") or ""
            )
            st.success("Fee receipt details extracted. Please review them below.")
            st.json(receipt_data)
        except Exception as error:
            st.error(f"Fee receipt extraction failed: {error}")


# ============================================================
# REVIEW AND SAVE STUDENT + FEE IN ONE TRANSACTION
# ============================================================

if st.session_state.get("student_extraction_done", False):
    st.divider()
    st.subheader("Step 3: Review and Save Student Details")
    st.info(
        "Review the extracted information. If a fee receipt is attached, "
        "the student and fee record will be saved together."
    )

    with st.form("student_registration_form"):
        name = st.text_input("Student Name", key="student_name")
        email = st.text_input("Email Address", key="student_email")

        course_options = ["-- Select a course --"] + course_names
        saved_course = st.session_state.get(
            "student_course", "-- Select a course --"
        )
        if saved_course not in course_options:
            saved_course = "-- Select a course --"

        course = st.selectbox(
            "Course",
            options=course_options,
            index=course_options.index(saved_course),
            key="student_course"
        )

        status = st.selectbox(
            "Student Status",
            ["Select Status", "Active", "Inactive"],
            key="student_status"
        )
        joining_date = st.text_input(
            "Joining Date (YYYY-MM-DD)",
            key="student_joining_date",
            placeholder="2026-07-15"
        )
        city = st.text_input("City", key="student_city")

        st.markdown("**Fee receipt information (optional)**")
        receipt_number = st.text_input(
            "Receipt Number", key="fee_receipt_number"
        )
        fee_amount = st.text_input(
            "Total Fee Amount", key="fee_total_amount"
        )
        payment_date = st.text_input(
            "Payment Date (YYYY-MM-DD)", key="fee_payment_date"
        )
        payment_mode = st.text_input(
            "Payment Mode", key="fee_payment_mode"
        )

        save_student = st.form_submit_button(
            "💾 Save Student and Fee Receipt",
            type="primary"
        )

    if save_student:
        if not name.strip():
            st.error("Student name is required.")
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
            st.error("Please enter a valid email address.")
        elif course == "-- Select a course --":
            st.error("Please select a valid course from the Courses table.")
        elif status == "Select Status":
            st.error("Please select student status.")
        else:
            try:
                if joining_date.strip():
                    date.fromisoformat(joining_date.strip())

                fee_amount_value = None
                if fee_amount.strip():
                    fee_amount_value = float(
                        fee_amount.strip().replace(",", "").replace("₹", "")
                    )
                    if fee_amount_value <= 0:
                        raise ValueError("Fee amount must be greater than zero.")

                if fee_amount_value is not None and payment_date.strip():
                    date.fromisoformat(payment_date.strip())

                if fee_amount_value is not None and not receipt_number.strip():
                    raise ValueError("Receipt number is required when saving a fee record.")

                connection = get_database_connection()
                try:
                    with connection:
                        cursor = connection.execute(
                            """
                            INSERT INTO Students
                                (name, email, course_id, status, joining_date, city)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                name.strip(),
                                email.strip(),
                                course_id_by_name[course],
                                status,
                                joining_date.strip() or None,
                                city.strip()
                            )
                        )
                        new_student_id = cursor.lastrowid

                        if fee_amount_value is not None:
                            connection.execute(
                                """
                                INSERT INTO Fees
                                    (student_id, receipt_number, amount,
                                     payment_date, payment_mode)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    new_student_id,
                                    receipt_number.strip(),
                                    fee_amount_value,
                                    payment_date.strip() or None,
                                    payment_mode.strip() or None
                                )
                            )
                finally:
                    connection.close()

                st.session_state.student_save_message = (
                    f"Student {name.strip()} saved successfully"
                    + (" with fee receipt!" if fee_amount_value is not None else "!")
                )
                st.session_state.student_extraction_done = False
                st.session_state.student_form_data = {}
                st.session_state.fee_receipt_data = {}
                for key in [
                    "student_name", "student_email", "student_course",
                    "student_status", "student_joining_date", "student_city",
                    "fee_receipt_number", "fee_total_amount",
                    "fee_payment_date", "fee_payment_mode"
                ]:
                    st.session_state.pop(key, None)
                st.rerun()

            except ValueError as error:
                st.error(f"Please check the entered values: {error}")
            except sqlite3.IntegrityError:
                st.error("This email already exists or the selected relationship is invalid.")
            except sqlite3.Error as error:
                st.error(f"Database error: {error}")
            except Exception as error:
                st.error(f"Something went wrong: {error}")


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(
    "AI Database Assistant | Powered by Gemini, Qdrant, SQLite and Streamlit"
)
