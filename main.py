
import os
import sqlite3
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient

# 1. Load API key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("Gemini API key not found!")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=120000)
)

# 2. Take question from user
question = input("\nAsk your database question: ")

# 3. Generate question embedding
print("\nGenerating question embedding...")

embedding_response = client.models.embed_content(
    model="gemini-embedding-001",
    contents=question,
    config=types.EmbedContentConfig(
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=768
    )
)

query_vector = embedding_response.embeddings[0].values

# 4. Retrieve schema from Qdrant
print("Retrieving database schema...")

qdrant = QdrantClient(path="./qdrant_storage")

results = qdrant.query_points(
    collection_name="student_schema",
    query=query_vector,
    limit=1,
    with_payload=True
)

qdrant.close()

if not results.points:
    raise ValueError("No relevant schema found!")

retrieved_schema = results.points[0].payload["text"]

# 5. Generate SQL using Gemini
print("Generating SQL query...")

prompt = f"""
You are an SQLite SQL expert.

Database schema:
{retrieved_schema}

User question:
{question}

Rules:
1. Generate only one SELECT query.
2. Use only existing tables and columns.
3. Never generate INSERT, UPDATE, DELETE or DROP.
4. Return only SQL without explanations or markdown.
"""

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=prompt,
    config=types.GenerateContentConfig(temperature=0)
)

sql_query = response.text.strip()

# Remove optional markdown code fences
if sql_query.startswith("```"):
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

print("\nGenerated SQL:")
print(sql_query)

# 6. Execute SQL safely in read-only mode
print("\nExecuting SQL...")

conn = sqlite3.connect("students.db")
cursor = conn.cursor()

# Allow only read operations
allowed_actions = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE
}

def read_only_authorizer(action, arg1, arg2, database, trigger):
    if action in allowed_actions:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY

conn.set_authorizer(read_only_authorizer)

try:
    if not sql_query.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed!")

    cursor.execute(sql_query)

    rows = cursor.fetchall()

    print("\nQuery Result:")

    for row in rows:
        print(row)

    if not rows:
        print("No records found.")

except Exception as error:
    print("SQL execution error:", error)

finally:
    conn.close()
    client.close()

print("\nTask completed!")
