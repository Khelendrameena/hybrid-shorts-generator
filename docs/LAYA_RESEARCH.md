# Laya — verified research notes (inspected 2026-11-10)

Sources: Hugging Face model card `convaiinnovations/laya-multilingual`,
HF blog "Laya AI Model: How It Works, Run It Locally, and Evaluate It",
GitHub `NandhaKishorM/laya`.

## What Laya actually is (do NOT mistake it for a generative LLM)

- **Family:** Laya, by Convai Innovations. Open weights, **Apache-2.0**, released Sep 2026.
- **Type:** Non-autoregressive **System-1 decision model**. It **never generates text**.
  There is nothing to parse and no prose output.
- **Input:** a **state** (text, or a dict/JSON such as `{"body": "..."}`) plus one or
  more **typed questions** defined at request time.
- **Output:** one forward pass returns typed answers with probabilities:
  `{"answers": {...}, "routing": {...}, "model": ..., "usage": ...}`

## Checkpoints

| Checkpoint | Encoder | Params | Context | Use |
|---|---|---|---|---|
| `convaiinnovations/laya` | ModernBERT-large | 421M | 512 | English |
| **`convaiinnovations/laya-multilingual`** | **mmBERT-base** | **322M** | **1024, up to 8192 with `max_len=8192`** | **100+ languages — this project** |
| `convaiinnovations/laya-typed-decisions` | ModernBERT-large | 421M | 1024 | fine-tuned workflows |

Multilingual architecture: mmBERT-base backbone (307M, bidirectional, 22 layers,
hidden 768, **256k vocab**) + decision head trained from scratch (2 transformer
layers, option-marker scorer scoring each option at its own `[MASK]` token then
softmax over that question's options, act/escalate head). 322M total.
Trained with RLCD (RL against strictly proper scoring rules).

## The three typed question types — the ONLY supported interface

```python
questions = {
  "department": {"type": "choice",
                 "instructions": "Which team should handle `body`?",
                 "criteria": {"billing": "invoices, payments, refunds",
                              "technical": "bugs and outages"}},
  "urgency":    {"type": "score",
                 "instructions": "How urgent is this?",
                 "criteria": ["routine", "soon", "blocking"]},
  "refund":     {"type": "noul",
                 "instructions": "Does the sender ask for money back?"},
}
```

- `choice` → `answers[q]["choice"]` + `answers[q]["probabilities"]`
- `score`  → ordered levels; returns a distribution + expected level. **Weakest
  primitive** (model card: SST-5 0.282, measured position bias — rarely picks the
  first-listed level). This project therefore prefers `noul` + `choice` and treats
  `score` as a secondary signal only.
- `noul`   → `answers[q]["noul"]` = P(true). Model card warns it can under-report
  "true" (~0.5 on clearly positive inputs); the documented workaround is the same
  question as a 2-option `choice` with neutral keys A/B. Our engine cross-checks
  critical noul answers that way when confidence is ambiguous.

## Real inference API (from the model card, verbatim shape)

```python
pip install laya          # Python 3.10+
import laya
agent = laya.load("convaiinnovations/laya-multilingual")
result = agent.predict({"body": "..."}, questions, max_len=8192)
print(result["answers"]["department"]["choice"])

from laya import Router   # recommended for mixed-language traffic
router = Router()
router.predict(state, questions)   # routes by script/language
```

Gotcha from the card: if `laya.load()` hangs, `transformers` probing TensorFlow
can deadlock — run with `USE_TF=0`. Our engine sets that before import.

## Size / VRAM truth for an RTX 3050 (4 GB)

322M params → ~1.29 GB fp32, ~0.65 GB fp16 on disk/in VRAM, plus activations.
It **fits** in 4 GB alone — but NOT alongside Faster-Whisper + Ollama
`qwen3:4b` (~2.5 GB Q4). Hence this project's **ModelManager**: only one heavy
model is resident at a time; Laya is unloaded before Ollama generation and
vice-versa (Ollama is also told `keep_alive=0`).

Speed (vendor, Tesla T4): 32.8 ms for 1 question, 72.3 ms for 10 (7.2 ms/q).

## Honest limitations (from the model card itself)

1. **Text only.** Laya does not see video frames, faces or audio. This project
   never claims otherwise: visual suitability comes from separate OpenCV /
   audio-energy features, combined in the scoring formula — not from Laya.
2. **Ships uncalibrated.** Temperatures are all 1.0; it is systematically
   over-confident (mean confidence 0.75–0.83 vs much lower accuracy). ECE
   0.314 → 0.106 after fitting temperatures on held-out data. Our engine
   therefore blends Laya probabilities with deterministic transcript/visual
   features and never treats a raw Laya probability as ground truth.
3. **Near-chance zero-shot on typed-decisions workflows** (0.342 vs 0.318
   random). Fine-tuning is where capability comes from — out of scope for the
   MVP; the heuristic blend is the working alternative and is labelled as such.
4. Keep `choice` questions under ~20 options (options share a 256-token head budget).
5. Long inputs: reliable to ~4,000 tokens before the question; beyond that,
   accuracy varies. Our candidate windows stay well under that.
