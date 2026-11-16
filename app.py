
import streamlit as st
import sqlite3
import os
import re
import pandas as pd
import plotly.express as px

from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)

# ---------------- PAGE CONFIG ----------------

st.set_page_config(
    page_title="AI Database Assistant",
    page_icon="🤖",
    layout="wide"
)

# ---------------- LOAD CONFIGURATION ----------------

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "students.db"
SCHEMA_PATH = BASE_DIR / "schema.md"

load_dotenv(BASE_DIR / ".env")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error(
        "Gemini API key not found. "
        "Please configure GEMINI_API_KEY in Streamlit Secrets."
    )
    st.stop()

if not DATABASE_PATH.exists():
    st.error("students.db database file not found.")
    st.stop()

if not SCHEMA_PATH.exists():
    st.error("schema.md file not found.")
    st.stop()


# ---------------- INITIALIZE AI AND QDRANT ----------------

@st.cache_resource
def initialize_services(api_key):

    # Initialize Gemini
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=120000)
    )

    # Initialize in-memory Qdrant
    qdrant = QdrantClient(":memory:")

    collection_name = "student_schema"

    # Read database schema
    with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
        schema_text = file.read()

    # Create Qdrant collection
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=768,
            distance=Distance.COSINE
        )
    )

    # Generate schema embedding
    embedding_response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=schema_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768
        )
    )

    embedding = embedding_response.embeddings[0].values

    # Store schema embedding in Qdrant
    qdrant.upsert(
        collection_name=collection_name,
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


# ---------------- DATABASE CONNECTION ----------------

def get_database_connection():
    return sqlite3.connect(str(DATABASE_PATH))


# ---------------- HEADER ----------------

st.title("🤖 AI-Powered Database Assistant")

st.write(
    "Ask questions about student records in simple English. "
    "AI will generate SQL and retrieve answers from your database."
)

st.divider()


# ---------------- DASHBOARD STATISTICS ----------------

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


# ---------------- COURSE-WISE ANALYSIS ----------------

st.subheader("📚 Course-wise Student Distribution")

chart_conn = get_database_connection()

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

city_conn = get_database_connection()

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

status_conn = get_database_connection()

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

st.plotly_chart(
    fig,
    width="stretch"
)

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

        st.warning("Please enter your question first.")

    else:

        try:

            with st.spinner("Understanding your question..."):

                # STEP 1: Generate question embedding

                embedding_response = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=question,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY",
                        output_dimensionality=768
                    )
                )

                query_vector = embedding_response.embeddings[0].values

                # STEP 2: Retrieve relevant schema from Qdrant

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
                    raise ValueError(
                        "Gemini returned an empty SQL response."
                    )

                sql_query = response.text.strip()

                # Remove markdown formatting if present

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

            if not re.match(
                r"^SELECT\b",
                sql_query,
                re.IGNORECASE
            ):
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
                action, arg1, arg2, database_name, trigger
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

                st.dataframe(
                    result_df,
                    width="stretch"
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
