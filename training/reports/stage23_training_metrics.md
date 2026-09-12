# Stage 23 training metrics

## Run summary

| Metric | Result |
|---|---:|
| Base checkpoint | `Qwen/Qwen3-14B` |
| Adapter | `prithi-qwen-lora-v0.1` |
| GPU | NVIDIA L4, 23,034 MiB |
| Epochs | 1.0 |
| Optimizer steps | 17 |
| Training examples | 132 |
| Validation examples | 7 |
| Held-out split examples | 7 |
| Training time | 173.56 s |
| Model load time | 77.48 s |
| Final train loss | 1.56837 |
| Initial validation loss | 3.14698 |
| Final validation loss | 1.13367 |
| Peak PyTorch allocated VRAM | 16,588,621,312 bytes (15.45 GiB) |
| Adapter directory | 268,407,179 bytes (about 256 MiB) |
| Adapter safetensors | 256,976,504 bytes |
| Trainable parameters | 64,225,280 (0.433%) |

## Configuration

- 4-bit NF4 base loading with double quantization
- BF16 compute and TF32 enabled on the L4
- LoRA rank 16, alpha 32, dropout 0.05
- Targets: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`
- Micro-batch 1; gradient accumulation 8; effective batch 8
- Gradient checkpointing enabled
- Maximum sequence length 512, selected from observed data (maximum 492; p95 312)
- Assistant-only causal-language-model loss
- Learning rate 1e-4, cosine schedule, one warmup step
- One epoch only to limit pilot overfitting

Validation loss declined at every recorded evaluation: 3.147 before training, then 1.821, 1.257, 1.156, 1.135, and 1.134 at the end.

## Environment

- Python 3.10.20
- PyTorch 2.11.0+cu128
- CUDA 12.8
- Transformers 5.17.0
- Datasets 5.0.1
- PEFT 0.20.0
- TRL 1.13.0
- Accelerate 1.15.0
- bitsandbytes 0.50.2

## GPU utilization note

Historical utilization percentage was not sampled during the successful run; the authoritative resource metric is the 15.45 GiB PyTorch peak allocation. A post-run attempt to reproduce one micro-step was made after production Gemma had been restored and occupied about 8.76 GiB. That diagnostic failed before backward with CUDA OOM while trying to coexist with Gemma, so its 60% median/65% peak load telemetry is not represented as training utilization. The process exited cleanly, production Gemma remained active, and no checkpoint was changed.

## Storage

- Final adapter: `training/checkpoints/prithi-qwen-lora-v0.1/`
- Intermediate checkpoints and trainer state: `training/checkpoints/stage23/` (about 763 MiB)
- Persistent Hugging Face base cache: `training/models/huggingface/` (about 28 GiB)
- Checkpoints and base cache are ignored by Git.

