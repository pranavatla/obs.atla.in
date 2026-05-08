import chromadb

# Initialize the local database (it saves as a folder in your project)
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="user_info")

# "Remembering" a fact
collection.add(
    documents=["The user's name is Pranav and he works at Accenture."],
    ids=["user_1"]
)

# "Retrieving" the fact
result = collection.query(
    query_texts=["What is the user's name?"],
    n_results=1
)

print(f"Memory Retrieval: {result['documents'][0][0]}")