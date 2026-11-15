# Local performance benchmark (target laptop)

Hardware: Windows 11, 7.4 GB RAM, CPU-only, so the TRD's "Minimum" profile.
Model: `qwen2.5:3b` (Ollama 0.40.16, 1.9 GB, quantized).

| Measure | TRD target | Measured | Status |
|---|---|---|---|
| Rule/ML analysis (full 11-step pipeline) | ≤ 2 s | 0.42–0.60 s (AnomalyDetect ≈ 170–530 ms of that) | Met |
| Save check-in (API) | ≤ 1 s | < 0.1 s | Met |
| First start incl. seeding 3 × 41 days | — | ≈ 6 s | — |
| LLM raw speed | — | ≈ 10 tok/s prompt, ≈ 7 tok/s generation | — |
| LLM explanation (3 findings, 2 passages) | ≤ 20 s (benchmark, not guaranteed) | 51 s and 118 s (two runs) | **Not met** |
| JSON compliance | — | First prompt version: invalid/truncated; after prompt reduction and truncation repair: valid | — |

**Consequences built into the design.**

- The explanation runs in a background thread after the run is saved, so urgent alerts are never delayed.
- The UI shows the deterministic explanation immediately and swaps in the validated LLM text when it is ready.
- On this hardware the LLM is a convenience feature. For the live demo, warm the model first (run one analysis
  before presenting; `keep_alive` is 15 min), or set `LOCAL_LLM_ENABLED=false`.
- A smaller model (e.g. a 1–1.5B instruct model) or a 16 GB / GPU machine should be benchmarked if explanation
  latency matters.

## Smaller-model comparison (same findings, copy of the live database)

| Model | Cold run | Warm run | Statements accepted by the guard |
|---|---|---|---|
| qwen2.5:1.5b | 307 s (timed out) | 63 s | 1–2 |
| qwen2.5:3b | 60 s | 35 s | 1–2 |

The smaller model is **not** faster on this laptop. With 7.4 GB of RAM mostly in use, the bottleneck is memory
paging, not model size. qwen2.5:3b stays the default.

The realistic fix is hardware: 16 GB RAM, or closing other applications before the demo. The app never waits for
the explanation either way.
