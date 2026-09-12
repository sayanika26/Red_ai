#!/usr/bin/env python3
"""One unsaved LoRA micro-step used only to sample approximate L4 utilization."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    sys.path.insert(0, str(root / "training/scripts"))
    from train_stage23_qlora import ChatDataset, Collator, MODEL_ID

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token_id is None: tokenizer.pad_token = tokenizer.eos_token
    row = json.loads((root / "training/data/splits/train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    dataset = ChatDataset([row], tokenizer, 512)
    batch = {key: value.cuda() for key, value in Collator(tokenizer.pad_token_id)([dataset[0]]).items()}
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=quant, device_map={"": 0}, dtype=torch.bfloat16, attn_implementation="sdpa", low_cpu_mem_usage=True)
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True)
    model = PeftModel.from_pretrained(base, root / "training/checkpoints/prithi-qwen-lora-v0.1", is_trainable=True)
    model.enable_input_require_grads()
    model.train()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    loss = model(**batch).loss
    loss.backward()
    torch.cuda.synchronize()
    print(json.dumps({"unsaved_microstep_loss": float(loss.detach()), "seconds": time.perf_counter() - started, "peak_vram_bytes": torch.cuda.max_memory_allocated()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
