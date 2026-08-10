# SPEC-001 — Runtime local com Ollama e RTX 5090

**Status:** Draft  
**Etapa:** 1 — inferência local sem créditos de cloud  
**Data da especificação:** 2026-08-09  
**Responsável:** equipe do projeto

## 1. Objetivo

Colocar o chatbot para gerar respostas e notificações usando o `OllamaProvider`
com um modelo local executado na RTX 5090. Ao final desta etapa, o sistema deve
ser capaz de confirmar que o modelo está disponível, responder pelo endpoint de
chat e gerar uma notificação proativa sem depender de uma chave do Gemini ou de
qualquer fallback automático para um provider pago.

O primeiro modelo de referência será o `gemma4:26b`, correspondente ao Gemma 4
26B A4B em formato local. O nome deve continuar configurável por
`OLLAMA_MODEL` para permitir a comparação posterior com a variante QAT e com o
Gemma 4 31B.

## 2. Contexto atual e lacunas

O levantamento do projeto encontrou os seguintes pontos relevantes:

| Componente | Situação atual | Consequência para esta etapa |
| --- | --- | --- |
| `OllamaProvider` | Já implementado em `app/services/llm_provider.py` | A primeira execução deve validar o adapter existente antes de criar outro runtime. |
| Configuração | O código tem defaults para Ollama, mas o `.env` de desenvolvimento seleciona Google | A configuração efetiva precisa ser alterada apenas no ambiente de execução, sem versionar credenciais. |
| `GET /v1/health` | Verifica o servidor e o modelo do provider selecionado | Será o primeiro gate automatizado. |
| Benchmark | `scripts/benchmark_local_models.py` já existe | Deve produzir a evidência de latência e concorrência da RTX 5090. |
| RAG | A ingestão/embeddings atuais dependem de componentes Google | Os smoke tests desta etapa usarão `use_rag: false`; RAG local fica para uma etapa posterior. |
| Hardware no ambiente de desenvolvimento | RTX 5090/Ollama ainda não foram comprovados neste host | O host que possuir a GPU precisa executar o preflight e guardar os resultados. |

## 3. Escopo

### Incluído

- Instalação ou validação do Ollama no host da GPU.
- Download, aquecimento e seleção do modelo local.
- Configuração local ou remota do `OLLAMA_BASE_URL`.
- Smoke tests de `/v1/health`, `/v1/chat` e `/v1/chat/proactive`.
- Teste de dez gerações proativas sequenciais.
- Benchmark de cold start, latência aquecida, p50, p95, tokens por segundo e
  concorrência.
- Registro de versão do driver, Ollama, modelo, quantização e parâmetros de
  execução.
- Comparação opcional com `gemma4:31b` somente para validar se o ganho de
  qualidade justifica a maior utilização de recursos.
- Pequenos ajustes no adapter e nos testes caso a validação revele falso
  positivo de modelo, resposta vazia ou erro de configuração.

### Não incluído

- Scheduler/event router para disparar notificações automaticamente.
- Entrega por push, e-mail, WhatsApp ou outro canal.
- Integração definitiva com o backend de produção.
- Ingestão dos documentos do Drive em uma base vetorial local.
- Treinamento, fine-tuning ou criação de um modelo próprio.
- Fallback silencioso para Gemini, Hugging Face ou outro serviço externo.
- Correções de segurança e hardening que não sejam necessárias para proteger
  a porta do Ollama durante este teste.

## 4. Decisões técnicas

1. **Runtime:** Ollama, pois o projeto já possui um provider compatível e uma
   API HTTP simples.
2. **Modelo inicial:** `gemma4:26b` (Gemma 4 26B A4B, MoE, Q4). A variante
   `gemma4:26b-a4b-it-qat` será a alternativa para ganhar margem de VRAM. O
   `gemma4:31b` só será promovido se vencer o teste de qualidade definido nesta
   especificação.
3. **Localidade:** preferir Ollama no mesmo host do chatbot. Se a GPU ficar em
   outro host, usar rede privada/VPN ou túnel SSH.
4. **Seleção de provider:** `LLM_PROVIDER=ollama` explícito. Uma falha do
   Ollama deve produzir erro observável, nunca uma chamada cloud implícita.
5. **RAG:** desativado nos smoke tests (`use_rag=false`) porque a cadeia de
   embeddings atual ainda não é local.
6. **Segurança de rede:** não publicar a porta `11434` na internet. No mesmo
   host, manter o bind em loopback; em host separado, restringir firewall aos
   IPs da aplicação ou usar túnel SSH.

Fluxo esperado:

```text
[Chatbot API] --HTTP privado--> [Ollama :11434] --> [RTX 5090]
       |                              |
       +-- /v1/health                 +-- modelo gemma4:26b
       +-- /v1/chat
       +-- /v1/chat/proactive
```

## 5. Contrato de configuração

O ambiente de execução deve possuir pelo menos:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:26b
# Preencher somente se o gateway remoto exigir Basic Auth.
OLLAMA_USERNAME=
OLLAMA_PASSWORD=
```

Quando o Ollama estiver em outro host, a URL muda. Se houver um proxy
protegido, informe também as credenciais somente no `.env` real do backend:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=https://ollama.seu-dominio.example
OLLAMA_USERNAME=usuario-do-gateway
OLLAMA_PASSWORD=segredo-do-gateway
OLLAMA_MODEL=gemma4:26b
```

Para uma conexão privada sem autenticação, pode ser usada uma URL como
`http://HOST_PRIVADO_DA_GPU:11434`, mantendo `OLLAMA_USERNAME` e
`OLLAMA_PASSWORD` vazios. Nunca versionar valores reais nem enviar a senha ao
frontend.

Regras:

- Nunca colocar chaves, senhas ou endereços públicos sensíveis no arquivo de
  exemplo ou no Git.
- O `.env` real deve continuar fora do controle de versão.
- O modelo solicitado pela aplicação deve existir exatamente no catálogo do
  Ollama antes de iniciar o smoke test. Não usar `gemma4:31b-cloud`.
- A aplicação deve informar no health o provider e o modelo efetivamente
  selecionados.

## 6. Plano de implementação

### T1 — Preflight do host da GPU

**Objetivo:** confirmar que o host da RTX 5090 está pronto antes de mexer na
configuração do chatbot.

Executar no host que contém a GPU:

```bash
nvidia-smi
ollama --version
ollama ps
curl --fail http://127.0.0.1:11434/api/tags
```

Registrar:

- modelo da GPU, versão do driver e memória disponível;
- versão do Ollama;
- sistema operacional e arquitetura;
- modelos instalados;
- se o chatbot e o Ollama estão no mesmo host ou separados;
- URL privada usada entre os dois serviços.

**Saída:** preflight aprovado ou lista objetiva de bloqueios. Se `nvidia-smi`
não mostrar a GPU, parar a validação de performance e corrigir o host antes de
prosseguir.

### T2 — Instalar e configurar o Ollama

Caso o serviço não exista, instalar conforme o procedimento operacional do
host. Confirmar que ele inicia como serviço e que a API fica acessível apenas
no escopo de rede definido em T1.

No host da GPU:

```bash
ollama pull gemma4:26b
ollama run gemma4:26b "Responda em uma frase: o runtime local está ativo?"
ollama ps
```

O `ollama ps` deve ser consultado durante uma geração para comprovar que o
modelo foi carregado e está utilizando a GPU. Se o host for remoto, testar a
mesma URL a partir da máquina do chatbot antes de subir a aplicação.

### T3 — Configurar o chatbot para o provider local

Aplicar a configuração do item 5 no ambiente de execução. Não alterar
credenciais de banco, backend ou admin como parte desta etapa.

Confirmar no código e em testes que:

- `get_llm_provider()` cria `OllamaProvider` quando `LLM_PROVIDER=ollama`;
- `model_override`, quando usado, não troca o provider nem envia a aplicação
  para cloud;
- erro de conexão, timeout e modelo ausente retornam erro explícito;
- a configuração não exige `GEMINI_API_KEY` para chat sem RAG;
- o health não exibe um modelo de outro provider quando a configuração local
  falha.

Se necessário, os ajustes esperados ficam limitados a:

- tornar a checagem de modelo do `OllamaProvider` precisa para a tag escolhida;
- tratar resposta vazia como falha observável;
- corrigir o campo `model` do health para usar o modelo do provider ativo;
- adicionar testes unitários sem necessidade de Ollama real.

### T4 — Smoke test do serviço Ollama

Antes de testar a aplicação, validar diretamente a API:

```bash
curl --fail http://127.0.0.1:11434/api/tags

curl --fail http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma4:26b",
    "messages": [{"role": "user", "content": "Escreva uma notificação curta em português sobre economia de energia."}],
    "stream": false
  }'
```

Critérios deste teste:

- HTTP 200;
- campo `message.content` não vazio;
- nenhuma chamada a provider externo;
- modelo carregado na GPU, confirmado por `ollama ps` e `nvidia-smi`.

### T5 — Smoke test da aplicação

Subir a API na máquina do chatbot usando o `.env` preparado:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal, executar:

```bash
curl --fail http://127.0.0.1:8000/v1/health

curl --fail -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "spec-001-chat",
    "message": "Explique em duas frases por que vale a pena desligar uma luz sem uso."
  }'

curl --fail -X POST http://127.0.0.1:8000/v1/chat/proactive \
  -H 'Content-Type: application/json' \
  -d '{
    "persona_id": "motivador",
    "target_profile_id": "engajado",
    "notification_type_id": "reengajamento_streak",
    "notification_context": {
      "streak_days": 14,
      "hours_remaining": 4
    },
    "use_rag": false
  }'
```

Validar nos três retornos:

- health com `status=healthy`, `provider=ollama`, modelo esperado e
  `provider_available=true`;
- chat com HTTP 200, `provider=ollama`, modelo esperado e resposta não vazia;
- proativa com HTTP 200, contexto resumido coerente, resposta sem placeholders
  literais como `{streak_days}` e registro salvo como pendente para revisão;
- logs sem erro de conexão, timeout ou tentativa de inicializar Gemini.

### T6 — Teste de repetição e falhas controladas

Executar dez chamadas proativas sequenciais usando `use_rag=false`. O teste
deve guardar somente métricas e IDs técnicos, sem conteúdo que contenha dados
reais de usuários.

Depois, verificar de forma controlada:

| Cenário | Resultado esperado |
| --- | --- |
| Ollama parado | `/v1/health` degradado e chat HTTP 503, com erro `provider_unavailable`. |
| Modelo não instalado | health indisponível e chat HTTP 503, com erro `model_not_found` ou mensagem equivalente. |
| URL inválida | erro explícito de conexão; nenhum fallback cloud. |
| Ollama restaurado | health volta a saudável e uma nova chamada funciona. |
| RAG desligado e sem chave Google | chat e proativa continuam funcionando. |

Após cada cenário, restaurar o serviço e repetir o health. Não apagar bancos,
notificações ou dados externos para executar este teste.

### T7 — Benchmark na RTX 5090

Com o modelo aquecido, executar o script existente a partir da raiz do projeto:

```bash
.venv/bin/python scripts/benchmark_local_models.py \
  --base-url http://127.0.0.1:11434 \
  --models gemma4:26b \
  --prompts scripts/benchmark_prompts.json \
  --iterations 5 \
  --concurrency 1 4 8 \
  --output /tmp/spec-001-ollama.json
```

Durante o benchmark, acompanhar `nvidia-smi` e `ollama ps`. Registrar no
relatório:

- cold start;
- média, p50 e p95 da latência aquecida;
- tokens por segundo;
- throughput e latência em concorrência 1, 4 e 8;
- memória da GPU, utilização e eventual fallback para CPU;
- temperatura, throttling ou erros de memória;
- tamanho/quantização do modelo e contexto utilizado.

O alvo inicial, sujeito a revisão após a primeira medição real, é p95 aquecido
menor ou igual a 3 segundos para uma notificação curta e dez execuções
sequenciais sem erro. O gate obrigatório é não haver fallback para CPU durante
o cenário aprovado; números abaixo do alvo devem gerar decisão registrada, não
ser mascarados.

Se a comparação for necessária, baixar também `gemma4:31b` e repetir o mesmo
conjunto de prompts. O 31B só será escolhido se melhorar de forma mensurável a
fidelidade dos dados, o tom e o cumprimento das regras sem ultrapassar o limite
de latência acordado.

### T8 — Handoff da etapa

Atualizar a especificação para `Accepted` somente depois de:

- anexar o resumo do benchmark ou indicar o caminho do artefato não versionado;
- registrar modelo, versão do Ollama e driver usados;
- documentar a topologia de rede aprovada;
- confirmar os smoke tests e o teste de falhas controladas;
- atualizar o exemplo de configuração e o guia operacional, se algum comando
  tiver mudado;
- registrar pendências para a etapa seguinte.

## 7. Critérios de aceite

A SPEC-001 será aceita quando todos os itens a seguir forem verdadeiros:

- [ ] `nvidia-smi` identifica a RTX 5090 no host de inferência.
- [ ] Ollama responde em `/api/tags` e contém a tag `gemma4:26b` ou a variante
      QAT aprovada.
- [ ] Uma chamada direta a `/api/chat` retorna conteúdo não vazio.
- [ ] `/v1/health` retorna `healthy`, `provider=ollama` e
      `provider_available=true`.
- [ ] `/v1/chat` gera uma resposta em português sem chave Google.
- [ ] `/v1/chat/proactive` gera e salva uma notificação pendente com
      `use_rag=false`.
- [ ] Dez notificações proativas consecutivas terminam sem erro 5xx.
- [ ] Nenhum output aprovado contém placeholder não resolvido.
- [ ] O modelo aparece como carregado na GPU durante a geração.
- [ ] O p95 aquecido atende o alvo definido no T7 ou existe uma decisão
      registrada aprovando uma meta revisada.
- [ ] A porta `11434` não está exposta publicamente.
- [ ] Não existe fallback automático para um serviço com cobrança.

## 8. Testes automatizados a preparar

Os testes não devem depender de uma RTX ou de um Ollama rodando no CI.

1. Teste unitário da seleção de provider com `LLM_PROVIDER=ollama`.
2. Teste do `OllamaProvider` com `httpx.MockTransport` para resposta normal,
   timeout, conexão recusada, HTTP 404 e resposta vazia.
3. Teste do health confirmando o modelo do provider ativo em caso de erro.
4. Teste do endpoint proativo com provider mockado e `use_rag=false`, incluindo
   a ausência de placeholders.
5. Smoke test real separado, marcado como `ollama` ou `gpu`, executado somente
   no host de validação.

## 9. Rollback

O rollback é apenas de configuração e serviço:

1. parar a aplicação;
2. restaurar o `.env` anterior do ambiente, sem versionar ou imprimir
   segredos;
3. iniciar a aplicação com a configuração anterior explicitamente escolhida;
4. verificar `/v1/health` e registrar que o runtime local foi desativado.

Se o Gemma 4 26B exceder a memória ou apresentar latência inviável, testar
`gemma4:26b-a4b-it-qat` como primeira alternativa. O `gemma4:31b` é uma opção
de qualidade, não um fallback de performance. Qualquer troca deve registrar o
motivo, a quantização e os resultados comparativos.

## 10. Saída esperada e próxima etapa

Entregáveis da etapa:

- ambiente Ollama operacional na RTX 5090;
- configuração reproduzível e sem segredo;
- evidência de health, chat, geração proativa e falhas controladas;
- relatório de benchmark;
- lista de pendências técnicas.

A etapa seguinte só deve começar depois deste gate. Ela tratará a adaptação dos
documentos e do RAG para execução local, seguida pelo contrato de eventos que
transformará contexto operacional em notificações dinâmicas.

## 11. Referências técnicas

- [Visão geral oficial do Gemma 4](https://ai.google.dev/gemma/docs/core)
- [Guia oficial de seleção do Gemma 4](https://ai.google.dev/gemma/docs/get_started)
- [Modelos Gemma 4 no Ollama](https://ollama.com/library/gemma4)
- [Especificações da RTX 5090](https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/)
