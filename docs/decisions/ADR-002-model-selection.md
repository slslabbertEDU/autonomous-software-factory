# ADR-002: Model Selection (Qwen3-Coder + DeepSeek-R1)

**Date:** 2026-06-20  
**Status:** Accepted  
**Author:** Shane Louis Slabbert

---

## Context

The factory requires two distinct model capabilities: high-throughput code generation (sustained inference for skeleton + implementation generation) and deep reasoning (hostile audit passes, formal verification assistance, complex debugging). These are different workloads with different hardware requirements and different invocation frequencies.

## Decision

**Primary model (code generation):** Qwen3-Coder-30B-A3B-AWQ  
**Reasoning model (audit + verification):** DeepSeek-R1-Distill-Qwen-32B

## Rationale

### Qwen3-Coder-30B-A3B-AWQ

- 92.1% HumanEval pass@1 — state of the art among open-weight models at this parameter count
- Mixture-of-Experts architecture: 30B total parameters, 3B active per forward pass — inference cost of a 3B model with quality of a 30B model
- Native 128K context window (32K used in pipeline)
- Fits A10 24GB VRAM at AWQ 4-bit quantization (~24GB total: 18GB weights + 6GB KV cache)
- Tool call support via Hermes parser — required for structured output in the agent loop

**Critical note on quantization:** At FP16, this model requires ~60GB VRAM — exceeding the A10's capacity. AWQ 4-bit is mandatory, not optional. The AWQ variant (`Qwen3-Coder-30B-A3B-AWQ`) is used directly from HuggingFace.

### DeepSeek-R1-Distill-Qwen-32B

- Chain-of-thought reasoning model — produces explicit reasoning traces before output
- Significantly better at finding subtle logic errors, race conditions, and specification drift than standard code models
- Used exclusively for: hostile audit passes, formal verification reasoning, complex debugging escalations
- Invoked on-demand (once per module) — A100 40GB provisioned per-invocation

## Alternatives Considered

| Model | Reason Not Selected |
|---|---|
| GPT-4o via API | Requires internet dependency, per-token cost at scale, data leaves local infrastructure |
| Claude 3.5 Sonnet via API | Same concerns as GPT-4o |
| Llama 3.1 70B | Lower HumanEval scores, requires A100 for sustained inference |
| CodeLlama 34B | Superseded by Qwen3-Coder on all code benchmarks |
| Qwen3-Coder-7B | Insufficient capability for complex multi-file generation |

## Consequences

- Qwen3-Coder runs persistently on A10 (always-on inference server via vLLM)
- DeepSeek-R1 runs on-demand on A100 (Temporal activity provisions and deprovisions)
- Both models run locally — no external API dependencies, no per-token cost after grant allocation
- Model endpoints exposed on private Oracle VPC only — not public internet
