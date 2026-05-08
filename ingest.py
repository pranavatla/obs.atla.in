import chromadb
import time

# Connect to your existing memory folder
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="user_memory")

# Read the file you just created
with open("company_info.txt", "r") as f:
    data = f.read()

# Add it to the permanent memory
collection.add(
    documents=[data],
    ids=[f"manual_{time.time()}"]
)

print("✅ Knowledge Ingested Successfully!")