import chromadb
import time
import os

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="user_memory")

KNOWLEDGE_DIR = "./knowledge_base"

# Loop through every file in your folder
for filename in os.listdir(KNOWLEDGE_DIR):
    if filename.endswith(".txt"):  # We'll start with text files
        file_path = os.path.join(KNOWLEDGE_DIR, filename)
        
        with open(file_path, "r") as f:
            content = f.read()
            
        # Add to ChromaDB
        collection.add(
            documents=[content],
            ids=[f"{filename}_{time.time()}"]
        )
        print(f"✅ Ingested: {filename}")

print("\n🚀 All documents are now in the AI's memory!")