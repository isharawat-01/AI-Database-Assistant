
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient

# 1. Load API key
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 2. Connect to Qdrant
qdrant = QdrantClient(path="./qdrant_storage")

# 3. User's natural language question
question = "How many active students are there?"

print("User Question:", question)

# 4. Convert question into embedding
response = client.models.embed_content(
    model="gemini-embedding-001",
    contents=question,
    config=types.EmbedContentConfig(
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=768
    )
)

query_vector = response.embeddings[0].values

# 5. Search relevant schema in Qdrant
results = qdrant.query_points(
    collection_name="student_schema",
    query=query_vector,
    limit=1,
    with_payload=True
)

# 6. Display retrieved schema
print("\nRetrieved Schema:")

for point in results.points:
    print(point.payload["text"])

qdrant.close()
