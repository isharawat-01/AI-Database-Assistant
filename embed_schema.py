
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# 1. Load API key from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("Gemini API key not found in .env file!")

# 2. Connect to Gemini
client = genai.Client(api_key=api_key)

# 3. Read schema.md
with open("schema.md", "r", encoding="utf-8") as file:
    schema_text = file.read()

print("Schema file loaded successfully!")

# 4. Generate embedding using Gemini
response = client.models.embed_content(
    model="gemini-embedding-001",
    contents=schema_text,
    config=types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=768
    )
)

embedding = response.embeddings[0].values

print("Embedding generated successfully!")
print("Vector dimensions:", len(embedding))

# 5. Connect to local Qdrant
qdrant = QdrantClient(path="./qdrant_storage")

collection_name = "student_schema"

# 6. Create collection if it does not exist
if not qdrant.collection_exists(collection_name):
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=768,
            distance=Distance.COSINE
        )
    )
    print("Qdrant collection created!")

# 7. Store embedding in Qdrant
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

print("Schema embedding stored in Qdrant successfully!")

qdrant.close()
