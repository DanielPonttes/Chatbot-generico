# Ollama em outra máquina (acesso via rede)

Este guia mostra como rodar o Ollama em uma máquina dedicada (por exemplo, um PC com GPU como uma RTX 5090) e apontar o chatbot para ele. O Ollama escuta em `http://HOST:11434` por padrao; o chatbot consome via HTTP.

## 1. Instalar o Ollama na maquina remota

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

O serviço inicia automaticamente. Confirme a versão e a API local com:

```bash
ollama --version
curl http://localhost:11434/api/tags
```

## 2. Baixar o modelo

Tags uteis (escolha uma):

| Tag                         | Tamanho | Contexto | Uso no projeto                                      |
|-----------------------------|---------|----------|----------------------------------------------------|
| `gemma4:26b`                | 18 GB   | 256K     | **Modelo principal** — Gemma 4 26B A4B, Q4         |
| `gemma4:26b-a4b-it-qat`     | 16 GB   | 256K     | Alternativa com mais margem de VRAM                |
| `gemma4:31b`                | 20 GB   | 256K     | Comparação de qualidade; não é o padrão             |
| `gemma4:31b-it-qat`         | 19 GB   | 256K     | Comparação quantizada; exige benchmark              |

Modelo aprovado para a primeira etapa:

```bash
ollama pull gemma4:26b
ollama run gemma4:26b "Responda em uma frase: o runtime local está ativo?"
```

O 26B A4B é um modelo Mixture-of-Experts: ele ativa menos parâmetros por
token, mas todos os pesos precisam estar carregados. Não confunda isso com um
modelo de 4 GB; acompanhe o uso real com `ollama ps` e `nvidia-smi`.

## 3. Liberar o acesso na rede (firewall / bind)

Não exponha a porta `11434` na internet. No mesmo host, prefira loopback. Em
um host remoto, use rede privada/VPN e permita apenas o IP do chatbot no
firewall.

No `ufw` (Ubuntu), libere somente para o IP privado da máquina do chatbot:

```bash
sudo ufw allow from IP_PRIVADO_DO_CHATBOT to any port 11434 proto tcp
```

Para habilitar escuta remota, configure o bind no serviço systemd. Prefira o
IP privado da GPU; `0.0.0.0` escuta em todas as interfaces e só deve ser usado
quando firewall e VPN já estiverem restringindo o acesso:

```bash
sudo systemctl edit ollama
```

No editor, adicione o drop-in abaixo:

```ini
[Service]
Environment="OLLAMA_HOST=IP_PRIVADO_DA_GPU:11434"
```

Use `OLLAMA_HOST=0.0.0.0:11434` somente com firewall restrito e VPN:

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

## 4. Apontar o chatbot para a maquina remota

Na maquina onde o chatbot roda, edite o `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://IP_DA_MAQUINA_OLLAMA:11434
OLLAMA_MODEL=gemma4:26b
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
- Modelo nao encontrado: rode `ollama pull gemma4:26b` na maquina remota

## 7. Benchmark do Gemma 4 26B A4B

Não usar estimativas genéricas como critério de aceite. Medir cold start,
latência aquecida, p50, p95, tokens/s, concorrência e VRAM no hardware real.
O contexto de 256K é o limite do modelo, não uma recomendação para cada
notificação; começar com 8K ou 16K reduz o custo do KV cache.

Após o baseline, ajustar `OLLAMA_NUM_PARALLEL` e o limite de requisições do
chatbot. Para mensagens curtas, manter o thinking desativado e avaliar a
variante QAT somente se a margem de VRAM ou throughput for insuficiente.

## 8. Escolhendo o runtime (Ollama vs llama.cpp vs vLLM vs LM Studio)

Ollama e a opcao recomendada para este projeto (já integrado, instalação em 1
comando e `gemma4:26b` no catálogo). Para uma comparação completa, vantagens e
quando migrar, veja [`llm_runtimes.md`](llm_runtimes.md).
