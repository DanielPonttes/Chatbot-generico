# Plano de Implementação: RAG para Gerador de Notificações com Gemini

Este documento descreve a arquitetura e os passos de implementação de um sistema **RAG (Retrieval-Augmented Generation)**. Este sistema fornecerá contexto adicional relevante e específico de domínio para o modelo LLM (Gemini) antes dele gerar notificações, garantindo respostas e alertas mais precisos, contextualizados e alinhados com regras de negócio.

---

## 1. Visão Geral da Arquitetura

O fluxo funcional do gerador de notificações equipado com RAG funcionará na seguinte ordem:

1. **Gatilho da Notificação**: Um evento ou demanda de sistema solicita a geração de uma notificação.
2. **Busca Semântica (Retrieval)**: O sistema converte o contexto deste evento em um "embedding" (vetor) e busca no Vector Database as diretrizes, históricos ou templates mais relevantes.
3. **Construção do Prompt (Augmentation)**: O sistema junta o pedido original com o contexto recuperado da base de conhecimento.
4. **Geração (Generation)**: O prompt enriquecido é enviado ao modelo do **Google Gemini** para gerar a notificação final.

---

## 2. Stack Tecnológica Sugerida

*   **LLM para Geração**: Google Gemini (Recomendado: `gemini-1.5-flash` para velocidade em de notificações, ou `gemini-1.5-pro` se exigir raciocínio complexo).
*   **Modelo de Embeddings**: `text-embedding-004` (API Gemini).
*   **Vector Database (Banco Vetorial)**: 
    *   *Opção Local / Simples:* **ChromaDB** ou **FAISS** (Roda local em arquivo/memória, fácil para começar).
    *   *Opção Nuvem / Escala:* **Pinecone**, **Qdrant** ou **Weaviate**.
*   **Orquestração (Opcional)**: LangChain ou LlamaIndex. Alternativamente, pode ser feito apenas com chamadas nativas (SDK do Google GenAI + SDK do Banco Vetorial) para manter leveza e evitar overhead.

---

## 3. Fases da Implementação

### Fase 1: Preparação e Ingestão da Base de Conhecimento
1. Coletar os documentos de referência (ex: manuais, políticas do negócio, padrões de tom de voz para mensagens, templates anteriores).
2. Processar e limpar os textos.
3. **Chunking**: Dividir os documentos em pedaços (chunks) menores (ex: 500 a 1000 tokens) para que os resultados da busca sejam cirúrgicos.
4. Gerar Embeddings através da API GenAI do Google e armazenar no Vector Database, atrelando os metadados (de onde veio aquela informação).

### Fase 2: O Motor de Busca (Retriever)
1. Criar função que receba a "intenção" da notificação que precisa ser gerada (Ex: *"Notificar o usuário que sua fatura atrasou 5 dias"*).
2. Gerar o embedding dessa intenção na hora.
3. Consultar o Vector DB em busca dos "Top K" chunks mais próximos (ex: buscando as guias de "Cobrança de Fatura" na base).
4. Retornar os textos puros desses chunks.

### Fase 3: Geração Augmentada (Gemini)
1. Criar um **System Prompt** robusto. Exemplo conceitual:
   ```text
   Você é um assistente responsável por gerar notificações para usuários.
   Siga RIGOROSAMENTE as regras declaradas no contexto abaixo.
   
   <CONTEXTO_RECUPERADO>
   {aqui_entram_os_resultados_da_busca_do_banco_vetorial}
   </CONTEXTO_RECUPERADO>
   
   Tarefa: Crie a notificação para o seguinte evento: {evento_do_usuario}
   ```
2. Realizar a chamada para a API do Gemini injetando o `prompt` construído e aguardar a resposta.
3. Inserir validação de saída e sanitização.

---

## 4. Estrutura de Diretórios Sugerida

Para manter o projeto organizado e modular, sugiro o seguinte isolamento (baseado em padrão Python/Node):

```text
/src
 ├── /rag
 │    ├── ingest.py        # Scripts para processamento de novos documnentos e geração de embeddings
 │    ├── vector_db.py     # Wrapper de conexão e busca no banco (Chroma, etc)
 │    └── retriever.py     # Lógica central para acionar embeds e a busca
 ├── /llm
 │    ├── gemini_client.py # Cliente wrapper para comunicacao com a Google AI API
 │    └── prompts.py       # Templates estáticos para os prompts
 └── notification_svc.py   # Serviço principal que orquestra tudo
```

---

## 5. Próximos Passos (Para o Desenvolvedor)

Antes de iniciar os códigos, precisamos alinhar:
1. Qual será a **Linguagem de Programação** do projeto (Python, Typescript)? O projeto `Chatbot-generico` já usa uma predominante?
2. Qual será o **Vector Database** preferido para começarmos (ChromaDB para testar localmente)?
3. Já temos material base (PDFs, txts, regras) para servirem de "conhecimento" inicial para a Ingestão?

*Por favor, aprove estas opções para prosseguirmos com a arquitetura do código real.*
