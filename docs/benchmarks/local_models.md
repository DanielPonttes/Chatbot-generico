# Benchmark de modelos locais: Qwen3.5-4B vs Gemma 4 E4B

Guia para medir e comparar performance, throughput e qualidade dos modelos locais recomendados para o chatbot.

## O que medimos

| Metrica | O que e | Por que importa |
|---------|---------|-----------------|
| **Cold start** | Tempo da primeira chamada (modelo carregado do disco) | Impacta o "primeiro usuario" apos restart |
| **Latencia total** | Tempo de parede de uma chamada (pre-warm) | Latencia percebida pelo usuario |
| **p50 / p95** | Mediana e percentil 95 da latencia | Mostra variabilidade; p95 e o que importa em producao |
| **Tokens/s (geracao)** | Velocidade efetiva de geracao | Throughput bruto do modelo |
| **Throughput concorrente** | Chamadas paralelas / segundo | Capacidade real sob carga |

## Pre-requisitos

1. **Ollama instalado** na maquina que vai rodar o modelo (veja [`ollama_remote.md`](../setup/ollama_remote.md))
2. **Modelos baixados**:
   ```bash
   ollama pull qwen3.5:4b
   ollama pull gemma4:e4b
   ```
3. **Python do projeto** com `httpx` (ja e dependencia):
   ```bash
   cd Chatbot-generico
   .venv/bin/pip install httpx
   ```

## Como rodar

Da raiz do projeto:

```bash
.venv/bin/python scripts/benchmark_local_models.py \
    --base-url http://localhost:11434 \
    --models qwen3.5:4b gemma4:e4b \
    --prompts scripts/benchmark_prompts.json \
    --iterations 3 \
    --concurrency 1 4 8 \
    --output benchmark_results.json
```

Argumentos:
- `--base-url` - URL do Ollama (default `http://localhost:11434`)
- `--models` - lista de modelos a comparar
- `--prompts` - JSON com prompts representativos
- `--iterations` - quantas vezes cada prompt e rodado em serie (default 3)
- `--concurrency` - niveis de paralelismo a testar (default `1 4`)
- `--concurrency-iterations` - rodadas por nivel de concorrencia (default 2)
- `--output` - arquivo JSON com resultados brutos

## Exemplo de saida

```
================================================================
  RESUMO COMPARATIVO (pre-warm, latencia media por chamada)
================================================================
Modelo                 Cold (ms)  Avg (ms)  p50 (ms)  p95 (ms)      tok/s    tokens
--------------------------------------------------------------------------------
qwen3.5:4b                   2300        450        430        680     220.0      85.0
gemma4:e4b                  7800        720        700       1100     155.0      90.0

================================================================================
  THROUGHPUT POR CONCORRENCIA (pre-warm, 1 prompt, N chamadas em paralelo)
================================================================================
Modelo                       c=1                  c=4                  c=8
--------------------------------------------------------------------------------
qwen3.5:4b          450ms/185.0           1600ms/210.0          2800ms/240.0
gemma4:e4b         720ms/125.0           2500ms/145.0          4500ms/155.0
```

Interpretacao:
- **Cold start** - Qwen3.5-4B carrega em ~2.3s, Gemma 4 E4B em ~7.8s (proporcional ao tamanho do modelo)
- **Latencia** - Qwen e ~40% mais rapido pre-warm (3.4GB vs 9.6GB)
- **Throughput** - Qwen escala melhor com concorrencia (210 vs 145 tok/s agregados a c=4)
- **Tokens gerados** - Ambos geram volumes similares (80-90 tokens por prompt)

## Como interpretar

- **Cold start alto (>5s)**: modelo grande ou disco lento. Considerar variante quantizada mais agressiva (ex: `gemma4:e4b-it-qat`).
- **p95 >> p50**: alta variabilidade. Considerar `OLLAMA_NUM_PARALLEL=1` se a causa for troca de contexto.
- **Throughput nao escala com concorrencia**: GPU saturada. Em RTX 5090 a escala e quase linear ate c=8 para modelos 4B.

## Comparacao com Gemini (cloud)

Para baseline de qualidade/latencia versus API cloud:

```bash
# 1. Adicione ao .env:
LLM_PROVIDER=google
GEMINI_API_KEY=sua_chave
GEMINI_MODEL=gemini-3-flash-preview

# 2. Suba o chatbot e chame:
time curl -X POST http://localhost:8000/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "Convide o usuario para a missao Aula Economica. Sala 393. Recompensa 35 XP."}'
```

Compare:
- **Latencia**: Gemini cloud costuma ter 300-800ms por chamada (incluindo rede)
- **Tokens/s**: tipicamente 50-150 tok/s dependendo do tier
- **Custo**: ~$0.075 por 1M tokens input no Flash, ~$0.30 por 1M output
- **Privacidade**: dados saem da rede local

Para o chatbot de notificacoes curtas, o modelo local em RTX 5090 e **mais barato e mais rapido** que Gemini Flash a partir de ~50 notificacoes/segundo (custo zero de cloud amortiza o hardware).

## Resultados por ambiente (template)

| Modelo          | Hardware        | Cold (ms) | Avg (ms) | p95 (ms) | tok/s | c=4 tok/s | c=8 tok/s | Notas                    |
|-----------------|-----------------|-----------|----------|----------|-------|-----------|-----------|--------------------------|
| qwen3.5:4b      | RTX 5090 (32GB) |           |          |          |       |           |           |                          |
| qwen3.5:4b      | CPU (Xeon X)    |           |          |          |       |           |           |                          |
| gemma4:e4b      | RTX 5090 (32GB) |           |          |          |       |           |           |                          |
| gemini-3-flash  | cloud           |           |          |          |       |           |           | custo: ~$X por 1M tokens |

## Boas praticas

1. **Sempre inclua warmup** antes de medir (o script ja faz)
2. **Ambiente estavel**: sem outros processos na GPU, sem throttling termico
3. **Mesmo prompt para concorrencia** para isolar a variavel (o script usa `prompts[0]`)
4. **Salve os resultados** - o JSON de saida tem todos os numeros brutos
5. **Compare quantizacoes**: `qwen3.5:4b` vs `qwen3.5:4b-q8_0` mostra tradeoff qualidade vs velocidade
6. **Repita em horarios diferentes** para detectar variabilidade
