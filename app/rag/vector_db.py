import os
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

# Caminho onde o ChromaDB salvará os dados localmente
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
os.makedirs(DB_DIR, exist_ok=True)

def get_base_embeddings():
    """
    Retorna o modelo de embeddings do Google Generative AI.
    Usaremos o modelo padrão text-embedding-004 se a chave estiver disponível.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = os.getenv("GOOGLE_API_KEY") # fallback common in langchain
        
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=api_key
    )

def get_vector_store(collection_name: str = "notifications_knowledge"):
    """
    Inicializa e retorna o Vector Store do Chroma persistente.
    """
    embeddings = get_base_embeddings()
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=DB_DIR
    )
