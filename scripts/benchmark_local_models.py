"""
Benchmark de modelos LLM locais via Ollama.

Mede para cada (modelo, prompt):
- TTFT (time to first token) - latencia percebida
- Latencia total
- Tokens/s de geracao
- Pre-warm (latencia com modelo ja carregado)
- Cold-start (latencia com modelo sendo carregado pela primeira vez)

Tambem roda carga concorrente para medir throughput.

Uso:
    .venv/bin/python scripts/benchmark_local_models.py \\
        --base-url http://localhost:11434 \\
        --models gemma4:26b gemma4:31b \\
        --prompts scripts/benchmark_prompts.json \\
        --iterations 5 \\
        --concurrency 1 4 8

Saida:
- Tabela formatada no stdout
- JSON detalhado em --output (default: benchmark_results.json)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx


@dataclass
class PromptSample:
    name: str
    prompt: str
    persona: str = "motivador"
    system: str | None = None


@dataclass
class RunResult:
    model: str
    prompt_name: str
    iteration: int
    cold_start: bool
    total_ms: float
    load_ms: float
    prompt_eval_ms: float
    eval_ms: float
    prompt_tokens: int
    eval_tokens: int
    eval_tokens_per_sec: float
    success: bool
    error: str | None = None


@dataclass
class ModelSummary:
    model: str
    cold_start_ms: float | None
    pre_warm_samples: int
    avg_total_ms: float
    p50_total_ms: float
    p95_total_ms: float
    avg_tokens_per_sec: float
    avg_eval_tokens: float
    concurrency_results: dict[int, dict[str, float]] = field(default_factory=dict)


def load_prompts(path: Path) -> list[PromptSample]:
    """Carrega prompts de um JSON com lista {name, prompt, persona, system?}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"O arquivo {path} deve conter uma lista de prompts")
    return [PromptSample(**item) for item in data]


async def warmup_model(client: httpx.AsyncClient, base_url: str, model: str) -> None:
    """Forca o carregamento do modelo com uma chamada curta."""
    try:
        await client.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ok"}],
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=120.0,
        )
    except httpx.HTTPError:
        pass


async def run_one(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    sample: PromptSample,
    iteration: int,
    cold_start: bool,
) -> RunResult:
    """Executa uma chamada e mede tempos."""
    messages: list[dict[str, Any]] = []
    if sample.system:
        messages.append({"role": "system", "content": sample.system})
    messages.append({"role": "user", "content": sample.prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": 200,
            "temperature": 0.7,
        },
    }

    t_start = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=180.0,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return RunResult(
            model=model,
            prompt_name=sample.name,
            iteration=iteration,
            cold_start=cold_start,
            total_ms=(time.perf_counter() - t_start) * 1000,
            load_ms=0,
            prompt_eval_ms=0,
            eval_ms=0,
            prompt_tokens=0,
            eval_tokens=0,
            eval_tokens_per_sec=0,
            success=False,
            error=str(exc),
        )

    total_ms = (time.perf_counter() - t_start) * 1000
    load_ms = data.get("load_duration", 0) / 1e6
    prompt_eval_ms = data.get("prompt_eval_duration", 0) / 1e6
    eval_ms = data.get("eval_duration", 0) / 1e6
    prompt_tokens = data.get("prompt_eval_count", 0)
    eval_tokens = data.get("eval_count", 0)
    eval_tokens_per_sec = (eval_tokens / (data.get("eval_duration", 1) / 1e9)) if data.get("eval_duration", 0) else 0.0

    return RunResult(
        model=model,
        prompt_name=sample.name,
        iteration=iteration,
        cold_start=cold_start,
        total_ms=total_ms,
        load_ms=load_ms,
        prompt_eval_ms=prompt_eval_ms,
        eval_ms=eval_ms,
        prompt_tokens=prompt_tokens,
        eval_tokens=eval_tokens,
        eval_tokens_per_sec=eval_tokens_per_sec,
        success=True,
    )


async def run_concurrent(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    sample: PromptSample,
    concurrency: int,
    iterations: int,
) -> list[RunResult]:
    """Roda `concurrency` chamadas em paralelo, `iterations` vezes cada."""
    results: list[RunResult] = []
    for it in range(iterations):
        tasks = [
            run_one(client, base_url, model, sample, it, cold_start=False)
            for _ in range(concurrency)
        ]
        results.extend(await asyncio.gather(*tasks))
    return results


def summarize(model: str, results: list[RunResult]) -> ModelSummary:
    """Agrega resultados em metricas resumo."""
    successful = [r for r in results if r.success]
    cold = next((r.total_ms for r in results if r.success and r.cold_start), None)
    pre_warm = [r for r in successful if not r.cold_start]
    totals = [r.total_ms for r in pre_warm]
    tokens_per_sec = [r.eval_tokens_per_sec for r in pre_warm if r.eval_tokens_per_sec > 0]
    eval_tokens = [r.eval_tokens for r in pre_warm]

    return ModelSummary(
        model=model,
        cold_start_ms=cold,
        pre_warm_samples=len(pre_warm),
        avg_total_ms=statistics.mean(totals) if totals else 0,
        p50_total_ms=statistics.median(totals) if totals else 0,
        p95_total_ms=_percentile(totals, 95) if totals else 0,
        avg_tokens_per_sec=statistics.mean(tokens_per_sec) if tokens_per_sec else 0,
        avg_eval_tokens=statistics.mean(eval_tokens) if eval_tokens else 0,
    )


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = (len(sorted_v) - 1) * (p / 100)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_v) - 1)
    return sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (idx - lo)


def print_table(summaries: list[ModelSummary]) -> None:
    """Imprime tabela comparativa."""
    header = (
        f"{'Modelo':<22} {'Cold (ms)':>10} {'Avg (ms)':>10} "
        f"{'p50 (ms)':>10} {'p95 (ms)':>10} {'tok/s':>10} {'tokens':>8}"
    )
    print()
    print("=" * len(header))
    print("  RESUMO COMPARATIVO (pre-warm, latencia media por chamada)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f"{s.model:<22} "
            f"{s.cold_start_ms:>10.0f} "
            f"{s.avg_total_ms:>10.0f} "
            f"{s.p50_total_ms:>10.0f} "
            f"{s.p95_total_ms:>10.0f} "
            f"{s.avg_tokens_per_sec:>10.1f} "
            f"{s.avg_eval_tokens:>8.1f}"
        )
    print()


def print_concurrency(summaries: list[ModelSummary], concurrency_data: dict[str, dict[int, list[RunResult]]]) -> None:
    """Imprime tabela de throughput por concorrencia."""
    if not any(concurrency_data.values()):
        return
    concurrencies = sorted({c for data in concurrency_data.values() for c in data.keys()})
    if not concurrencies:
        return
    print()
    print("=" * 80)
    print("  THROUGHPUT POR CONCORRENCIA (pre-warm, 1 prompt, N chamadas em paralelo)")
    print("=" * 80)
    header = f"{'Modelo':<22}" + "".join(f" {f'c={c}':>16}" for c in concurrencies)
    print(header)
    print("-" * len(header))
    for s in summaries:
        row = f"{s.model:<22}"
        for c in concurrencies:
            results = concurrency_data.get(s.model, {}).get(c, [])
            if not results:
                row += f" {'-':>16}"
                continue
            successful = [r for r in results if r.success]
            if not successful:
                row += f" {'(falhas)':>16}"
                continue
            total_tokens = sum(r.eval_tokens for r in successful)
            wall = max(r.total_ms for r in successful) / 1000  # tempo de parede = a chamada mais lenta
            throughput = total_tokens / wall if wall > 0 else 0
            avg_latency = statistics.mean(r.total_ms for r in successful)
            row += f" {avg_latency:>7.0f}ms/{throughput:>5.1f}"
        print(row)
    print()
    print("Formato: <latencia_media_ms>/<tokens_por_segundo_agregado>")
    print()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark de modelos locais via Ollama")
    parser.add_argument("--base-url", default="http://localhost:11434", help="URL do Ollama")
    parser.add_argument("--models", nargs="+", required=True, help="Nomes dos modelos a testar (ex: gemma4:26b)")
    parser.add_argument("--prompts", type=Path, required=True, help="JSON com lista de prompts")
    parser.add_argument("--iterations", type=int, default=3, help="Iteracoes por (modelo, prompt) em serie")
    parser.add_argument("--concurrency", nargs="*", type=int, default=[1, 4], help="Niveis de concorrencia a testar")
    parser.add_argument("--concurrency-iterations", type=int, default=2, help="Repeticoes por nivel de concorrencia")
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.json"), help="Arquivo JSON de saida")
    args = parser.parse_args()

    prompts = load_prompts(args.prompts)
    print(f"Modelos: {args.models}")
    print(f"Prompts: {len(prompts)}")
    print(f"Iteracoes (serie): {args.iterations} | Concorrencias: {args.concurrency}")

    all_results: list[RunResult] = []
    concurrency_data: dict[str, dict[int, list[RunResult]]] = {m: {} for m in args.models}

    async with httpx.AsyncClient() as client:
        for model in args.models:
            print(f"\n>>> {model}")
            print(f"    warmup...")
            await warmup_model(client, args.base_url, model)

            print(f"    warmup ok. rodando bateria sequencial...")
            for sample in prompts:
                # Cold start na primeira iteracao
                first = await run_one(client, args.base_url, model, sample, 0, cold_start=True)
                all_results.append(first)
                if first.success:
                    print(f"      cold [{sample.name}]: {first.total_ms:.0f}ms ({first.eval_tokens_per_sec:.1f} tok/s)")

                # Pre-warm (ja carregado)
                for it in range(1, args.iterations):
                    r = await run_one(client, args.base_url, model, sample, it, cold_start=False)
                    all_results.append(r)
                    if r.success:
                        print(f"      pre-warm [{sample.name}] #{it}: {r.total_ms:.0f}ms ({r.eval_tokens_per_sec:.1f} tok/s)")

            # Bateria de concorrencia
            for c in args.concurrency:
                print(f"    concorrencia={c}...")
                sample = prompts[0]  # usa o primeiro prompt para concorrencia
                results = await run_concurrent(client, args.base_url, model, sample, c, args.concurrency_iterations)
                concurrency_data[model][c] = results
                all_results.extend(results)

    # Sumariza
    summaries = [summarize(m, [r for r in all_results if r.model == m]) for m in args.models]
    print_table(summaries)
    print_concurrency(summaries, concurrency_data)

    # Salva JSON
    output = {
        "config": {
            "base_url": args.base_url,
            "models": args.models,
            "iterations": args.iterations,
            "concurrency": args.concurrency,
            "concurrency_iterations": args.concurrency_iterations,
        },
        "summaries": [asdict(s) for s in summaries],
        "results": [asdict(r) for r in all_results],
        "concurrency": {m: {str(c): [asdict(r) for r in rs] for c, rs in data.items()} for m, data in concurrency_data.items()},
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Resultados salvos em {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
