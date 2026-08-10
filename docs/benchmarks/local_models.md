# Benchmark local: Gemma 4 26B A4B vs 31B

Guia para medir a performance do modelo aprovado para o agente de notificações
e decidir, com evidência, se o Gemma 4 31B oferece qualidade suficiente para
justificar o custo adicional.

## Decisão padrão

O modelo de produção inicial é `gemma4:26b`, o Gemma 4 26B A4B em formato
quantizado. A variante `gemma4:26b-a4b-it-qat` pode ser testada para aumentar a
margem de VRAM. O `gemma4:31b` é somente candidato de comparação.

O 26B é um modelo MoE e ativa menos parâmetros por token, enquanto o 31B é
denso. Isso sugere vantagem de latência para o 26B, mas a decisão final deve
ser baseada no hardware real e no conjunto de notificações do projeto.

## O que medir

| Métrica | O que é | Por que importa |
|---|---|---|
| **Cold start** | Primeira chamada com o modelo sendo carregado | Impacta reinício e recuperação do serviço |
| **Latência total** | Tempo de parede da chamada aquecida | Define a experiência e a vazão |
| **p50 / p95** | Mediana e percentil 95 | Mostra a variabilidade em produção |
| **Tokens/s** | Velocidade efetiva de geração | Mede throughput da GPU |
| **VRAM** | Memória ocupada durante a geração | Evita fallback para CPU e OOM |
| **Qualidade** | Fidelidade dos dados, tom e regras | É o critério para considerar o 31B |

## Pré-requisitos

1. **Ollama instalado** no host da GPU; veja [`ollama_remote.md`](../setup/ollama_remote.md).
2. **RTX 5090 reconhecida** por `nvidia-smi`.
3. **Modelo principal baixado**:

   ```bash
   ollama pull gemma4:26b
   ```

4. Para comparação opcional:

   ```bash
   ollama pull gemma4:31b
   ollama pull gemma4:26b-a4b-it-qat
   ```

5. Python do projeto com `httpx`:

   ```bash
   .venv/bin/pip install httpx
   ```

## Como executar

Da raiz do projeto, medir primeiro somente o modelo aprovado:

```bash
.venv/bin/python scripts/benchmark_local_models.py \
    --base-url http://localhost:11434 \
    --models gemma4:26b \
    --prompts scripts/benchmark_prompts.json \
    --iterations 5 \
    --concurrency 1 4 8 \
    --output /tmp/gemma4-26b-results.json
```

Para comparar qualidade e performance com o 31B, repetir o mesmo experimento:

```bash
.venv/bin/python scripts/benchmark_local_models.py \
    --base-url http://localhost:11434 \
    --models gemma4:26b gemma4:31b \
    --prompts scripts/benchmark_prompts.json \
    --iterations 5 \
    --concurrency 1 4 8 \
    --output /tmp/gemma4-26b-vs-31b.json
```

Argumentos principais:

- `--base-url`: URL do Ollama, por padrão `http://localhost:11434`.
- `--models`: tags locais a comparar.
- `--prompts`: JSON com prompts representativos.
- `--iterations`: repetições em série por prompt.
- `--concurrency`: níveis de paralelismo.
- `--output`: arquivo JSON com os resultados brutos.

## Avaliação de qualidade

O arquivo de prompts deve representar as categorias de notificação do projeto,
incluindo contexto dinâmico, personas e restrições de tamanho. Para cada saída,
avaliar:

- todos os valores factuais permanecem corretos;
- nenhum placeholder fica sem resolução;
- a mensagem não inventa recompensa, sala, prazo ou medição;
- o tom corresponde à persona;
- a mensagem é curta e acionável;
- a saída permanece em português brasileiro;
- a resposta não expõe raciocínio interno ou instruções do sistema.

Só promover o 31B se ele melhorar de forma consistente a qualidade no conjunto
de avaliação e ainda cumprir a meta de latência acordada. Uma diferença em
benchmarks gerais não substitui a avaliação específica das notificações.

## Registro dos resultados

| Modelo | Quantização | Hardware | Cold (ms) | p50 (ms) | p95 (ms) | tok/s | VRAM | Erros | Decisão |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `gemma4:26b` | Q4 | RTX 5090 32 GB | | | | | | | padrão |
| `gemma4:26b-a4b-it-qat` | QAT | RTX 5090 32 GB | | | | | | | opcional |
| `gemma4:31b` | Q4 | RTX 5090 32 GB | | | | | | | candidato |

O Ollama lista aproximadamente 18 GB para `gemma4:26b` e 20 GB para
`gemma4:31b`; a memória adicional do KV cache cresce com o contexto. Portanto,
começar com contexto de 8K ou 16K e acompanhar `ollama ps` e `nvidia-smi`.

## Boas práticas

1. Fazer warmup antes das medições aquecidas; o script já faz isso.
2. Usar o mesmo prompt para comparar concorrência.
3. Não executar outros modelos ou cargas na GPU durante o benchmark.
4. Repetir o experimento em ambiente estável, sem throttling térmico.
5. Manter o thinking desativado para notificações curtas.
6. Guardar o JSON bruto fora do Git e registrar apenas o resumo aprovado.
7. Não usar provider cloud como parte do gate de custo ou privacidade.

## Referências

- [Visão geral oficial do Gemma 4](https://ai.google.dev/gemma/docs/core)
- [Modelos Gemma 4 no Ollama](https://ollama.com/library/gemma4)
- [Especificações da RTX 5090](https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/)
