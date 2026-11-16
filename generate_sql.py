
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient

print("Step 1: Starting program...", flush=True)

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("Gemini API key not found!")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=120000)
)

question = "How many active students are there?"

print("Step 2: Generating question embedding...", flush=True)

embedding_response = client.models.embed_content(
    model="gemini-embedding-001",
    contents=question,
    config=types.EmbedContentConfig(
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=768
    )
)

query_vector = embedding_response.embeddings[0].values

print("Step 3: Connecting to Qdrant...", flush=True)

qdrant = QdrantClient(path="./qdrant_storage")

results = qdrant.query_points(
    collection_name="student_schema",
    query=query_vector,
    limit=1,
    with_payload=True
)

qdrant.close()

if not results.points:
    raise ValueError("No schema found in Qdrant!")

retrieved_schema = results.points[0].payload["text"]

print("Step 4: Schema retrieved successfully!", flush=True)
print("Step 5: Sending question to Gemini...", flush=True)

prompt = f"""
You are an expert SQLite SQL query generator.

Database Schema:
{retrieved_schema}

User Question:
{question}

Rules:
1. Generate only one valid SQLite SELECT query.
2. Use only existing tables and columns.
3. Never generate INSERT, UPDATE, DELETE or DROP.
4. Return only SQL. No explanation or markdown.
"""

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=prompt,
    config=types.GenerateContentConfig(temperature=0)
)

print("\nGenerated SQL Query:", flush=True)
print(response.text, flush=True)

client.close()
