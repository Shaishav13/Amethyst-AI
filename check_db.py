import os
import chromadb

def inspect_chromadb():
    # 1. Point Chroma to the database folder
    if "AMETHYST_HOME" in os.environ:
        amethyst_dir = os.environ["AMETHYST_HOME"]
    else:
        amethyst_dir = os.path.join(os.path.expanduser("~"), ".amethyst")
    db_path = os.path.join(amethyst_dir, "chroma_db")
    
    if not os.path.exists(db_path):
        print(f"Database folder not found at {db_path}.")
        print("This means you haven't attached any documents in Amethyst yet!")
        return

    print("Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path=db_path)

    # 2. Get the default collection (where Langchain stores the chunks)
    try:
        collection = client.get_collection("langchain")
    except Exception as e:
        print("The 'langchain' collection does not exist yet. No documents have been fully indexed.")
        return

    # 3. View the stats
    count = collection.count()
    print(f"\n✅ SUCCESS: Found Database!")
    print(f"📊 Total Document Chunks in Database: {count}")

    # 4. Peek at the first 3 chunks of text it has memorized
    if count > 0:
        print("\nHere is a sneak peek at the first 3 chunks of memory:")
        print("-" * 50)
        results = collection.peek(limit=3)
        if results and "documents" in results:
            for i, doc in enumerate(results["documents"]):
                print(f"CHUNK {i+1} SOURCE: {results['metadatas'][i].get('source', 'Unknown')}")
                # Print just the first 150 characters so it doesn't flood the terminal
                preview = doc[:150].replace('\n', ' ') + "..." if len(doc) > 150 else doc
                print(f"TEXT: {preview}")
                print("-" * 50)

if __name__ == "__main__":
    inspect_chromadb()
