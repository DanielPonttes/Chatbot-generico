import os
from typing import List, Dict, Any
from .vector_db import get_vector_store

def get_relevant_context(query: str, k: int = 4):
    """
    Busca no banco vetorial os K chunks mais relevantes para a query passada.
    Retorna uma string única com os conteúdos combinados.
    """
    vector_store = get_vector_store()
    
    # Faz a busca por similaridade
    docs = vector_store.similarity_search(query, k=k)
    
    if not docs:
        return ""
        
    # Combina os textos recuperados com uma separação clara
    context_chunks = [f"--- Trecho {i+1} ---\n{doc.page_content}" for i, doc in enumerate(docs)]
    return "\n\n".join(context_chunks)

def search_with_metadata(query: str, k: int = 4) -> List[Dict[str, Any]]:
    """
    Busca no banco vetorial e retorna a lista detalhada de resultados
    com os metadados (como nome do arquivo PDF original da página).
    Usado pelo frontend de visualização RAG.
    """
    vector_store = get_vector_store()
    
    # search_with_score retorna os documentos e a similaridade
    results = vector_store.similarity_search_with_score(query, k=k)
    
    formatted_results = []
    for doc, score in results:
        metadata = doc.metadata
        source = metadata.get("source", "Desconhecido")
        page = metadata.get("page", 0)
        
        # Limpa o caminho longo do arquivo se houver (para visualização)
        filename = os.path.basename(source)
            
        formatted_results.append({
            "content": doc.page_content,
            "source": filename,
            "page": page,
            "score": float(score)  # distâncias menores geralmente significam maior similaridade
        })
        
    return formatted_results

if __name__ == "__main__":
    # Teste simples
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "Regras de notificação"
    print(f"Buscando contexto para: '{query}'\n")
    context = get_relevant_context(query)
    print(context)
