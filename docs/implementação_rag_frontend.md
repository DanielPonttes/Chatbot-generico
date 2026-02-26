# Plano de Implementação: Visualizador do RAG (Frontend)

O usuário solicitou uma forma de visualizar como o RAG está funcionando e que informações ele possui. Para isso, criaremos um "RAG Dashboard" integrado à aplicação principal.

## User Review Required

Nenhum alerta crítico. Adicionaremos uma nova página sem quebrar nenhuma página existente. O RAG requer que a chave da API do Gemini esteja configurada no `.env` para responder às buscas.

## Proposed Changes

### Backend (FastAPI e Serviços)

- **[NEW] Endpoint de Busca Manual**:
  Criaremos um endpoint `/api/rag/search` (via POST ou GET) em `app/api/routes.py` que receberá uma requisição de busca (query string e quantidade `k`) e retornará um JSON contendo os trechos (chunks) mais semelhantes no ChromaDB, com a similaridade calculada.

- **[MODIFY] `app/rag/retriever.py`**:
  Vamos adicionar uma função `search_with_metadata(query, k)` para retornar não apenas a string combinada (usada no gerador), mas uma lista estruturada de dicionários com:
  - `content`: O trecho de texto.
  - `source`: O arquivo de origem.
  - `page`: A página do PDF original.

- **[MODIFY] `app/main.py`**:
  Adicionar a rota `@app.get("/rag")` que servirá o arquivo estático da nova tela `rag.html`.

### Frontend (User Interface)

- **[NEW] `app/static/rag.html`**:
  Uma página nova, no mesmo estilo visual TailwindCSS "Dark/Glass", contendo:
  1. Barra Superior com Navigation.
  2. Barra de Busca principal.
  3. Área de exibição exibindo "Cards" de conteúdo, onde cada card representa um pedaço de texto retornado pelo sistema vetorial.
  
- **[MODIFY] `app/static/index.html` e `app/static/notifications.html`**:
  Adicionar um link "Base de Conhecimento" ou "Visualizador RAG" no menu/cabeçalho para permitir a navegação simples.

## Verification Plan

### Manual Verification
1. Abrir a aplicação com `uvicorn app.main:app --reload`.
2. Navegar para a página principal e clicar no botão de "Visualizador RAG".
3. Digitar um tema relacionado às dissertações (ex: "Políticas de eficiência" ou "Sustentabilidade").
4. Clicar em buscar e verificar se:
   - Os cards de resultado aparecem na tela de forma agradável.
   - Os resultados mostram o nome do arquivo original e qual trecho foi puxado.
   - O tempo de busca é razoável.
