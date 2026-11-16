
import streamlit as st
import sqlite3
import os
import re
import pandas as pd
import plotly.express as px

from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient

# ---------------- PAGE CONFIG ----------------

st.set_page_config(
    page_title="AI Database Assistant",
    page_icon="🤖",
    layout="wide"
)

# ---------------- LOAD CONFIGURATION ----------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("Gemini API key not found. Please check your .env file.")
    st.stop()

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=120000)
)

# ---------------- QDRANT CONNECTION ----------------

qdrant = QdrantClient(path="./qdrant_storage")

# ---------------- HEADER ----------------

st.title("🤖 AI-Powered Database Assistant")

st.write(
    "Ask questions about student records in simple English. "
    "AI will generate SQL and retrieve answers from your database."
)

st.divider()

# ---------------- DASHBOARD STATISTICS ----------------

conn = sqlite3.connect("students.db")
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


# ---------------- COURSE-WISE ANALYSIS ----------------

st.subheader("📚 Course-wise Student Distribution")

chart_conn = sqlite3.connect("students.db")

course_data = pd.read_sql_query(
    """
    SELECT course, COUNT(*) AS total_students
    FROM Students
    GROUP BY course
    ORDER BY total_students DESC
    """,
    chart_conn
)

chart_conn.close()

st.bar_chart(
    course_data,
    x="course",
    y="total_students",
    x_label="Course",
    y_label="Number of Students"
)

# ---------------- CITY-WISE ANALYSIS ----------------

st.subheader("🌍 City-wise Student Distribution")

city_conn = sqlite3.connect("students.db")

city_data = pd.read_sql_query(
    """
    SELECT city, COUNT(*) AS total_students
    FROM Students
    GROUP BY city
    ORDER BY total_students DESC
    """,
    city_conn
)

city_conn.close()

st.bar_chart(
    city_data,
    x="city",
    y="total_students",
    x_label="City",
    y_label="Number of Students"
)


# ---------------- STUDENT STATUS ANALYSIS ----------------

st.subheader("📊 Active vs Inactive Students")

status_conn = sqlite3.connect("students.db")

status_data = pd.read_sql_query(
    """
    SELECT status, COUNT(*) AS total_students
    FROM Students
    GROUP BY status
    """,
    status_conn
)

status_conn.close()

fig = px.pie(
    status_data,
    names="status",
    values="total_students",
    title="Student Status Distribution",
    hole=0.4
)

st.plotly_chart(fig, use_container_width=True)


st.divider()

# ---------------- QUESTION INPUT ----------------

st.subheader("💬 Ask Your Database")

question = st.text_input(
    "Enter your question:",
    placeholder="Example: How many students are enrolled in MCA?"
)

# ---------------- PROCESS QUESTION ----------------

if st.button("Generate Answer", type="primary"):

    if not question.strip():
        st.warning("Please enter a question first.")

    else:
        try:
            with st.spinner("Understanding your question..."):

                # STEP 1: Generate query embedding

                embedding_response = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=question,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY",
                        output_dimensionality=768
                    )
                )

                query_vector = embedding_response.embeddings[0].values

                # STEP 2: Retrieve schema from Qdrant

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

                # STEP 3: Generate SQL using Gemini

                prompt = f"""
You are an expert SQLite SQL generator.

Use only the following database schema:

{schema}

User Question:
{question}

Instructions:
1. Generate only one valid SQLite SELECT query.
2. Do not generate INSERT, UPDATE, DELETE, DROP or other modification queries.
3. Use only tables and columns present in the schema.
4. Return only SQL without explanations or markdown.

SQL Query:
"""

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0
                    )
                )

                sql_query = response.text.strip()

                sql_query = re.sub(
                    r"^```(?:sql)?\s*|\s*```$",
                    "",
                    sql_query,
                    flags=re.IGNORECASE
                ).strip()

            # STEP 4: Display generated SQL

            st.subheader("📝 Generated SQL Query")

            st.code(sql_query, language="sql")

            # STEP 5: Execute SQL safely

            st.subheader("📊 Query Result")

            if not sql_query.upper().startswith("SELECT"):
                st.error("Only SELECT queries are allowed.")
                st.stop()

            database = sqlite3.connect("students.db")

            allowed_actions = {
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_RECURSIVE
            }

            def read_only_authorizer(
                action, arg1, arg2, database_name, trigger
            ):
                if action in allowed_actions:
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            database.set_authorizer(read_only_authorizer)

            result = database.execute(sql_query).fetchall()

            columns = [
                description[0]
                for description in database.execute(
                    sql_query
                ).description
            ]

            database.close()

            if result:
                st.success("Query executed successfully!")
                st.dataframe(
                    [dict(zip(columns, row)) for row in result],
                    use_container_width=True
                )
            else:
                st.info("No records found.")

        except Exception as e:
            st.error(f"Something went wrong: {e}")

# ---------------- FOOTER ----------------

st.divider()

st.caption(
    "AI Database Assistant | Powered by Gemini, Qdrant, SQLite and Streamlit"
)
