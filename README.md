# Groq Chatbot with RAG

A Flask-based chatbot that uses Groq's API for responses and Retrieval-Augmented Generation (RAG) to answer questions based on uploaded documents (PDF, DOCX, TXT).

## Features

- Upload documents (PDF, DOCX, TXT) for RAG indexing
- Chat with the bot using uploaded documents as context
- Persistent chat history
- Reset documents or clear chat history
- Web UI: Premium glassmorphism design with responsive layout and animations.

## Prerequisites

- Python 3.8+
- Groq API key (mandatory - get one from [Groq Console](https://console.groq.com/))

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd groq-chatbot
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```

3. Activate the virtual environment:
   - On Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```

4. Install dependencies (mandatory):
   ```bash
   pip install -r requirements.txt
   ```

5. Create a `.env` file in the root directory and add your Groq API key (mandatory):
   ```
   GROQ_API_KEY=your_api_key_here
   ```

## Running the Application

1. Ensure the virtual environment is activated.

2. Run the Flask app:
   ```bash
   python run.py
   ```

3. Open your browser and go to `http://127.0.0.1:5000`

## Usage

- Upload a document using the "Upload" button.
- Ask questions in the chat interface.
- The bot will use the uploaded documents to provide context-aware answers.
- Use "Reset Docs" to clear all uploaded documents.
- Use "Clear Chat History" to reset the conversation.

## Project Structure

- `run.py`: Application entry point
- `app/`: Main application package
  - `routes.py`: Flask routes
  - `rag.py`: RAG logic (Vector DB, Chunking)
  - `utils.py`: Helper functions
- `templates/index.html`: Main HTML template
- `static/css/style.css`: Premium glassmorphism styles and animations
- `static/js/main.js`: Frontend logic for chat and file handling
- `data/`: Directory for storing chat history, RAG index, and uploads
- `.env`: Environment variables (API key)
- `.gitignore`: Git ignore file

## API Endpoints

- `GET /`: Home page
- `POST /upload`: Upload a document
- `POST /reset_docs`: Reset all documents
- `POST /clear_history`: Clear chat history
- `POST /chat`: Send a chat message

## Dependencies

- Flask: Web framework
- python-dotenv: Environment variable management
- groq: Groq API client
- pypdf: PDF text extraction
- docx2txt: DOCX text extraction
- faiss-cpu: Vector search
- sentence-transformers: Text embeddings
- numpy: Numerical operations
