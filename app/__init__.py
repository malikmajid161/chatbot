import os

from dotenv import load_dotenv
from flask import Flask
from groq import Groq

# Initialize extensions
client = None
embedder = None

def create_app():
    global client, embedder
    
    # Load environment variables
    load_dotenv()
    
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    
    # Config
    app.config['DATA_DIR'] = "data"
    app.config['UPLOAD_DIR'] = os.path.join(app.config['DATA_DIR'], "uploads")
    app.config['HISTORY_FILE'] = os.path.join(app.config['DATA_DIR'], "chat.json")
    app.config['RAG_DIR'] = os.path.join(app.config['DATA_DIR'], "rag_index")
    app.config['FAISS_FILE'] = os.path.join(app.config['RAG_DIR'], "index.faiss")
    app.config['CHUNKS_FILE'] = os.path.join(app.config['RAG_DIR'], "chunks.json")
    app.config['LANG_STATE_FILE'] = os.path.join(app.config['DATA_DIR'], "lang_state.json")
    
    # Models config
    app.config['MODEL'] = "llama-3.1-8b-instant"
    app.config['EMBED_MODEL_NAME'] = "sentence-transformers/all-MiniLM-L6-v2"
    app.config['CHUNK_SIZE'] = 1900
    app.config['CHUNK_OVERLAP'] = 150
    app.config['TOP_K'] = 8
    
    # Initialize Groq client
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        client = Groq(api_key=api_key)
    else:
        print("WARNING: GROQ_API_KEY not found in environment")
        
    # Initialize Embedder (Optional for light deployment)
    try:
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer(app.config['EMBED_MODEL_NAME'])
        print("INFO: SentenceTransformer initialized successfully.")
    except ImportError:
        embedder = None
        print("WARNING: sentence-transformers not found. RAG features will be disabled.")
    except Exception as e:
        embedder = None
        print(f"WARNING: Failed to initialize SentenceTransformer: {e}")

    # Register routes
    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app
