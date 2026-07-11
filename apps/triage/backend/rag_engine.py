import os

# Set up paths
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
GUIDELINES_DIR = os.path.join(DATA_DIR, 'guidelines')
CHROMA_DB_DIR = os.path.join(DATA_DIR, 'chromadb_v2')

def _get_client():
    import chromadb
    import shutil
    try:
        return chromadb.PersistentClient(path=CHROMA_DB_DIR)
    except Exception as e:
        print(f"ChromaDB client error: {e}. Recreating directory...")
        if os.path.exists(CHROMA_DB_DIR):
            shutil.rmtree(CHROMA_DB_DIR)
        return chromadb.PersistentClient(path=CHROMA_DB_DIR)

def get_chroma_collection():
    import chromadb
    import shutil
    from chromadb.utils import embedding_functions
    
    def _try_get_collection():
        client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        sentence_transformer_ef = embedding_functions.DefaultEmbeddingFunction()
        return client.get_or_create_collection(
            name="ed_guidelines",
            embedding_function=sentence_transformer_ef
        )
    
    try:
        return _try_get_collection()
    except Exception as e:
        print(f"ChromaDB collection error: {e}. Recreating directory...")
        if os.path.exists(CHROMA_DB_DIR):
            shutil.rmtree(CHROMA_DB_DIR)
        return _try_get_collection()

def initialize_knowledge_base():
    """Reads all guidelines text files, chunks them by paragraph, and stores them in ChromaDB."""
    if not os.path.exists(GUIDELINES_DIR):
        print(f"Guidelines directory not found at {GUIDELINES_DIR}")
        return

    import chromadb
    import shutil
    from chromadb.utils import embedding_functions
    
    try:
        client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        client.delete_collection("ed_guidelines")
    except Exception as e:
        print(f"Failed to delete collection, recreating db dir: {e}")
        if os.path.exists(CHROMA_DB_DIR):
            shutil.rmtree(CHROMA_DB_DIR)
        client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        
    sentence_transformer_ef = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name="ed_guidelines",
        embedding_function=sentence_transformer_ef
    )

    print("Initializing knowledge base from guidelines directory...")
    
    documents = []
    ids = []
    metadatas = []
    
    global_index = 0
    
    for filename in os.listdir(GUIDELINES_DIR):
        if not filename.endswith('.txt'):
            continue
            
        filepath = os.path.join(GUIDELINES_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Simple chunking by paragraph
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        # Ignore the title line
        paragraphs = [p for p in paragraphs if not p.startswith('**EMERGENCY DEPARTMENT')]

        for para in paragraphs:
            documents.append(para)
            ids.append(f"guideline_{global_index}")
            global_index += 1
            
            # Extract title from the bold text if present
            title = "General Guideline"
            if para.startswith('**') and '**' in para[2:]:
                title = para.split('**')[1].strip()
            metadatas.append({"source": filename, "topic": title})

    if documents:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Successfully loaded {len(documents)} guidelines into ChromaDB.")

def retrieve_guidelines(query: str, n_results: int = 2):
    """Retrieves the most relevant clinical guidelines for the given query."""
    collection = get_chroma_collection()
    
    if collection.count() == 0:
        # Failsafe: if the database is empty, try to initialize it first
        initialize_knowledge_base()
        collection = get_chroma_collection()
        
    if collection.count() == 0:
        return ""

    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )

    if not results or not results['documents'] or not results['documents'][0]:
        return ""

    retrieved_texts = results['documents'][0]
    
    formatted_guidelines = "### RETRIEVED CLINICAL GUIDELINES ###\n"
    for i, text in enumerate(retrieved_texts):
        formatted_guidelines += f"[{i+1}] {text}\n\n"
        
    return formatted_guidelines
