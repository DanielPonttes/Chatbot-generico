# Ollama em outra máquina (acesso via rede)

Este guia mostra como rodar o Ollama em uma máquina dedicada (por exemplo, um PC com GPU como uma RTX 5090) e apontar o chatbot para ele. O Ollama escuta em `http://HOST:11434` por padrao; o chatbot consome via HTTP.

## 1. Instalar o Ollama na maquina remota

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

O servico inicia automaticamente e escuta em `0.0.0.0:11434`. Confirme com:

```bash
ollama --version
curl http://localhost:11434/api/tags
```

## 2. Baixar o modelo

Tags uteis (escolha uma):

| Tag                       | Tamanho | Contexto | Observacao                                                |
|---------------------------|---------|----------|-----------------------------------------------------------|
| gemma4:e4b                | 9.6 GB  | 128k     | **Gemma 4 E4B** (4.5B effective + PLE) - recomendado      |
| gemma4:e4b-it-qat         | 6.1 GB  | 128k     | Gemma 4 E4B quantizado QAT - mais leve                   |
| gemma4:e4b-it-q8_0        | 12 GB   | 128k     | Gemma 4 E4B q8 - mais qualidade, mais VRAM                |
| qwen2.5:7b                | 4.7 GB  | 32k      | Otimo em PT-BR, mais leve que o Gemma 4                  |
| llama3.1:8b               | 4.9 GB  | 128k     | Generalista muito capaz                                   |

Exemplo com Gemma 4 E4B:

```bash
ollama pull gemma4:e4b
ollama run gemma4:e4b "ola, voce funciona?"   # teste rapido
```

## 3. Liberar o acesso na rede (firewall / bind)

O Ollama escuta em `0.0.0.0:11434` por padrao, entao ja aceita conexoes externas. Se houver firewall, libere a porta 11434.

No `ufw` (Ubuntu):

```bash
sudo ufw allow 11434/tcp
```

Se quiser restringir o acesso por IP, troque o `bind` editando o servico systemd:

```bash
sudo systemctl edit ollama
# Adicione:
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

## 4. Apontar o chatbot para a maquina remota

Na maquina onde o chatbot roda, edite o `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://IP_DA_MAQUINA_OLLAMA:11434
OLLAMA_MODEL=gemma4:e4b
```

Para evitar expor o Ollama na internet, mantenha as duas maquinas na mesma rede privada/VPN.

## 5. Testar via tunel SSH (sem expor a porta)

Se a maquina com o Ollama nao tem IP acessivel diretamente, use um tunel SSH a partir da maquina do chatbot:

```bash
ssh -L 11434:localhost:11434 usuario@IP_DA_MAQUINA_OLLAMA
```

Mantenha o terminal aberto. O chatbot continua usando `OLLAMA_BASE_URL=http://localhost:11434` porque o tunel encaminha para a maquina remota. Ideal para testes sem mexer em firewall.

## 6. Validar a conexao

Suba o chatbot e chame `/v1/health`:

```bash
curl http://localhost:8000/v1/health
```

O campo `provider` deve ser `ollama` e `provider_available` deve ser `true`. Em caso de erro:

- Conexao recusada: firewall bloqueando ou Ollama nao subiu
- Timeout: maquina do chatbot nao alcança a URL configurada
- Modelo nao encontrado: rode `ollama pull gemma4:e4b` na maquina remota

## 7. Estimativa de vazao (Gemma 4 E4B em RTX 5090)

| Carga                                    | Tempo estimado |
|------------------------------------------|----------------|
| 1 notificacao curta (~150 tokens)        | <1 s           |
| 10 notificacoes em sequencia             | 5-10 s         |
| 10 notificacoes em paralelo (workers)    | 1-2 s          |

A RTX 5090 entrega tipicamente 150+ tokens/s para modelos 4B-effective em quantizacao q4_K_M, sobrando bastante folga para 10+ notificacoes/min. O gargalo geralmente e a concorrencia de chamadas no Ollama, nao o modelo. Ajuste `OLLAMA_NUM_PARALLEL` (padrao 1) se precisar de mais concorrencia, e `RATE_LIMIT_PER_MINUTE` no `.env` do chatbot se for servir varios clientes.
