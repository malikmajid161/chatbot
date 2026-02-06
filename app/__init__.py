import os
from flask import Flask
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer

# Initialize extensions
client = None
embedder = None

def create_app():
    global client, embedder
    
    # Load environment variables
    load_dotenv()
    
    app = Flask(__name__)
    
    # Config
    app.config['DATA_DIR'] = "data"
    app.config['UPLOAD_DIR'] = os.path.join(app.config['DATA_DIR'], "uploads")
    app.config['HISTORY_FILE'] = os.path.join(app.config['DATA_DIR'], "chat.json")
    app.config['RAG_DIR'] = os.path.join(app.config['DATA_DIR'], "rag_index")
    app.config['FAISS_FILE'] = os.path.join(app.config['RAG_DIR'], "index.faiss")
    app.config['CHUNKS_FILE'] = os.path.join(app.config['RAG_DIR'], "chunks.json")
    
    # Models config
    app.config['MODEL'] = "llama-3.1-8b-instant"
    app.config['EMBED_MODEL_NAME'] = "sentence-transformers/all-MiniLM-L6-v2"
    app.config['CHUNK_SIZE'] = 1900
    app.config['CHUNK_OVERLAP'] = 150
    app.config['TOP_K'] = 6
    
    # Initialize Groq client
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        client = Groq(api_key=api_key)
    else:
        print("WARNING: GROQ_API_KEY not found in environment")
        
    # Initialize Embedder
    # Lazy loading in routes if needed, but here is fine for now
    embedder = SentenceTransformer(app.config['EMBED_MODEL_NAME'])

    # Register routes
    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app
