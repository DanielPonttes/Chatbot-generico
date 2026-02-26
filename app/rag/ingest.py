import os
import argparse
import time
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .vector_db import get_vector_store

def ingest_pdfs(pdf_paths: list[str]):
    """
    Processa uma lista de caminhos de PDFs, os divide em chunks menores, e os ingere no ChromaDB.
    """
    print(f"Iniciando ingestão de {len(pdf_paths)} documentos...")
    vector_store = get_vector_store()
    
    # Text splitter otimizado para não perder muito contexto (overlap)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    
    for path in pdf_paths:
        if not os.path.exists(path):
            print(f"Erro: Arquivo não encontrado: {path}")
            continue
            
        print(f"Processando: {path}")
        try:
            loader = PyPDFLoader(path)
            documents = loader.load()
            
            # Cortar em chunks
            chunks = text_splitter.split_documents(documents)
            total_chunks = len(chunks)
            print(f"  -> Dividido em {total_chunks} chunks. Inserindo no ChromaDB em batches...")
            
            # Batching para evitar RESOURCE_EXHAUSTED (Limite tier grátis Google: ~2k RPM ou 15 RPM dependendo do modelo)
            # Para gemini-embedding-001 o limite é 100 requisições por minuto.
            batch_size = 50
            for i in range(0, total_chunks, batch_size):
                batch = chunks[i:i + batch_size]
                current_batch_num = (i // batch_size) + 1
                total_batches = (total_chunks + batch_size - 1) // batch_size
                
                print(f"    -> Enviando batch {current_batch_num}/{total_batches} ({len(batch)} chunks)...")
                vector_store.add_documents(batch)
                
                # Se não for o último batch, esperar para não estourar a cota de 100 requisições por minuto
                if i + batch_size < total_chunks:
                    print("    -> Aguardando 65 segundos para respeitar a cota da API (Tier Grátis)...")
                    time.sleep(65)
            
            print(f"  -> Concluído: {path}")
        except Exception as e:
            print(f"Erro ao processar {path}: {e}")
            
    print("Ingestão finalizada com sucesso!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingestão de dados (PDFs) no banco vetorial RAG.")
    parser.add_argument("pdfs", nargs="+", help="Caminhos dos arquivos PDF para ingestão")
    args = parser.parse_args()
    
    ingest_pdfs(args.pdfs)
