# Comparativo de runtimes LLM: Ollama vs llama.cpp vs vLLM vs LM Studio

Guia para escolher o servidor/embalagem do modelo local. O projeto suporta Ollama nativamente e qualquer servidor compativel com OpenAI (vLLM, LM Studio, llama.cpp server) via adapter.

## Resumo executivo

| Aspecto               | Ollama          | llama.cpp          | vLLM                | LM Studio        |
|-----------------------|-----------------|--------------------|---------------------|------------------|
| Manutencao            | Ativa           | Muito ativa        | Muito ativa         | Ativa (propriet.)|
| Interface             | CLI + REST      | CLI + servidor HTTP| CLI + servidor HTTP| GUI desktop + API|
| API padrao            | Proprietaria    | OpenAI-compat      | OpenAI-compat       | OpenAI-compat    |
| Suporte a modelos     | Curado (Ollama) | Amplo (HF + GGUF)  | Amplo (HF)          | GUI (GGUF)      |
| Performance GPU       | Boa             | Excelente          | Maxima (PagedAttn)  | Boa             |
| Performance CPU       | Boa             | Excelente          | Fraco (foco GPU)    | Boa             |
| Instalacao            | 1 comando       | Binario ou build   | Python pip          | GUI             |
| Config remoto (SSH)   | Trivial         | Trivial            | Trivial             | Trabalhoso      |
| Headless (server)     | Sim             | Sim (`llama-server`)| Sim                | Possivel (REST)  |
| Modelo recomendado    | qwen3.5:4b      | gguf do HF         | HF direto           | gguf do HF       |

## Ollama (recomendado para o projeto)

**O que e**: runtime embalado que usa llama.cpp por baixo, com model registry, CLI e API REST propria.

- Prós: instalacao em 1 comando (`curl ... | sh`); catalogo de modelos ja quantizados (qwen3.5:4b, gemma4:e4b etc); API simples; suporte a multimodal e thinking mode; OLLAMA_NUM_PARALLEL para concorrencia.
- Contras: API proprietaria (mas existe OpenAI-compat opcional em `/v1/chat/completions`); limitado aos modelos do catalogo; menos flexivel que llama.cpp puro.
- **Atracao para o projeto**: ja existe um `OllamaProvider` em `app/services/llm_provider.py` consumindo a API do Ollama — zero trabalho para trocar de modelo.
- Quando usar: primeira opcao, especialmente se o modelo esta no catalogo do Ollama.

## llama.cpp

**O que e**: implementacao C/C++ de inferencia LLM; base tecnologica de Ollama, LM Studio e outros.

- Prós: maxima portabilidade (CPU, CUDA, Metal, Vulkan, ROCm); suporta o maior numero de arquiteturas; quantizacao customizada; standalone; `llama-server` expoe OpenAI-compat.
- Contras: sem model registry; precisa baixar/quantizar GGUF manualmente; instalacao via build em algumas plataformas.
- Quando usar: precisa rodar em hardware exotico (CPU antigo, Apple Silicon, sem GPU NVIDIA); precisa de uma configuracao de quantizacao especifica; quer controle total.

## vLLM

**O que e**: servidor de inferencia em Python focado em throughput maximo (PagedAttention, continuous batching).

- Prós: maior throughput para cenarios de alta concorrencia; OpenAI-compat 100%; speculative decoding; quantizacao avancada (FP8, MXFP8, NVFP4); recomendado oficialmente por varios autores de modelos (incluindo Qwen) para producao; integracao nativa com modelos HuggingFace.
- Contras: requer GPU NVIDIA (nao roda bem em CPU); instalacao Python mais pesada; curva de configuracao maior; complexo para tuning.
- Quando usar: precisa de **throughput maximo** (centenas de requests simultaneos); ja tem GPU NVIDIA; cenarios de producao pesados.
- **Para o chatbot**: nao necessario — a carga e baixa (10-100 notificacoes/min). vLLM brilha em cargas muito maiores.

## LM Studio

**O que e**: aplicacao desktop (Electron) com GUI para baixar modelos e conversar; tambem expoe servidor local OpenAI-compat.

- Prós: GUI amigavel para descobrir/baixar modelos; bom para experimentar localmente sem CLI; serve modelos via REST.
- Contras: GUI desktop — nao ideal para servidores; instalacao pesada (Electron); sem instalacao headless em servidor Linux padrao; focado em uso pessoal.
- Quando usar: experimentacao local em desktop; desenvolvimento rapido sem configurar CLI. Nao recomendado para o deploy do chatbot (que e headless).

## Recomendacao para o projeto Chatbot

**Use Ollama**. Motivos:

1. **Ja integrado**: o `OllamaProvider` em `app/services/llm_provider.py` consome a API do Ollama. Trocar de modelo (ex: `gemma4:e4b` → `qwen3.5:4b`) e so mudar `OLLAMA_MODEL` no `.env`.
2. **Instalacao trivial**: `curl -fsSL https.ollama.com/install.sh | sh` em qualquer Linux/macOS/WSL; configuracao em uma linha no `.env` do projeto.
3. **Modelo alvo no catalogo**: `qwen3.5:4b` (3.4GB, q4_K_M) ja esta no Ollama, com 256K de contexto.
4. **10+ notificacoes/min e folgado** numa RTX 5090 — Ollama e llama.cpp tem throughput equivalente nesse caso, e vLLM so compensa em cargas muito maiores.
5. **Operacao via SSH facil**: monitorar com `ollama ps`, baixar modelos com `ollama pull`, ajustar concorrencia com `OLLAMA_NUM_PARALLEL` e `OLLAMA_NUM_GPU` no systemd.
6. **OpenAI-compat disponivel** (`:11434/v1/chat/completions`): se no futuro quiser trocar para vLLM/LM Studio/llama.cpp-server, basta criar um `OpenAIProvider` que implemente a mesma interface `LLMProvider` do projeto.

## Quando migrar para vLLM

Considere trocar o backend para vLLM somente se:
- A carga subir para centenas de requests/segundo
- A latencia de p99 virar problema (vLLM tem continuous batching mais sofisticado)
- Vocé ja tiver um cluster de GPUs NVIDIA gerenciado via Kubernetes

Para o caso atual do chatbot, Ollama e mais que suficiente e mais simples de operar.
