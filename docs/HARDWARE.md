# Hardware Requirements

## Why Specific GPU Hardware Is Required

This is not a project that can run on CPU or consumer hardware. The compute requirements are driven by two specific model VRAM footprints that have no lower-cost equivalent.

---

## Required Instances

### VM.GPU.A10.1 — Primary Inference (Persistent)

**GPU:** NVIDIA A10  
**VRAM:** 24GB  
**Use:** Sustained inference for Qwen3-Coder-30B-A3B-AWQ

**Why this specific GPU:**

Qwen3-Coder-30B-A3B is a 30-billion parameter mixture-of-experts model. At 4-bit AWQ quantization:
- Weight memory: ~18GB
- KV cache for 32K context: ~6GB
- Total VRAM required: ~24GB

The A10's 24GB VRAM is the minimum viable configuration. At 16-bit (FP16), the model requires ~60GB VRAM — exceeding the A10's capacity. AWQ quantization is therefore required, not optional.

**Deployment command:**
```bash
vllm serve Qwen/Qwen3-Coder-30B-A3B-AWQ \
  --quantization awq \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.95
```

**Why persistent:** Module generation (Months 3-4) requires sustained inference throughput for 50 generation runs. On-demand provisioning introduces cold-start latency incompatible with the pipeline's Temporal workflow timeouts.

---

### BM.GPU4.8 — Reasoning Model (On-Demand, 200 Hours)

**GPU:** NVIDIA A100  
**VRAM:** 40GB  
**Use:** Hostile audit passes (DeepSeek-R1-Distill-Qwen-32B)

**Why this specific GPU:**

DeepSeek-R1-Distill-Qwen-32B is a 32-billion parameter dense reasoning model. At 4-bit AWQ quantization:
- Weight memory: ~20GB
- KV cache for 32K context reasoning pass: ~16GB
- Total VRAM required: ~36GB minimum, 40GB practical

The A100 40GB is the minimum viable configuration. This model is invoked once per module (hostile audit pass + formal verification reasoning) — approximately 50-100 total invocations at ~1-2 hours GPU time each.

**Deployment command:**
```bash
vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-32B \
  --quantization awq \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.95
```

**Why on-demand:** The reasoning model runs infrequently. Persistent allocation would be wasteful. On-demand provisioning via Temporal activity with a startup timeout is sufficient.

---

### ARM VM — Orchestration (Always-Free)

**Specification:** 4 cores, 24GB RAM  
**Use:** Temporal orchestrator, ChromaDB, Archivist Agent, CLI, all pipeline coordination

**Cost:** $0 (Oracle always-free tier)

Everything that does not require GPU inference runs on the ARM VM:
- Temporal server + web UI
- ChromaDB vector database (RAG)
- Archivist Agent (Wiki + ADR management)
- Factory Operator Console (CLI)
- Prometheus + Grafana monitoring
- Git repository management

---

## VRAM Summary

| Model | Parameters | Quantization | VRAM (weights) | VRAM (KV cache 32K) | Total | Required GPU |
|---|---|---|---|---|---|---|
| Qwen3-Coder-30B-A3B | 30B MoE | AWQ 4-bit | ~18GB | ~6GB | ~24GB | A10 24GB |
| DeepSeek-R1-Distill-Qwen-32B | 32B dense | AWQ 4-bit | ~20GB | ~16GB | ~36GB | A100 40GB |

---

## Why Oracle Cloud Specifically

1. **A10 and A100 availability** matches exact VRAM requirements — no alternative configuration exists at lower cost that satisfies both models
2. **Always-free ARM VM** eliminates orchestration infrastructure cost entirely
3. **Colocation** of GPU and ARM instances removes cross-provider network latency from the pipeline's inference calls
4. **Oracle's published investment** in open-weight model research aligns with this benchmark study's goals
5. **Research grant program** makes this compute accessible to independent researchers
