#!/usr/bin/env python3
"""Stage 23 one-epoch QLoRA pilot. Training workspace only; no production imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import time
from dataclasses import dataclass
from pathlib import Path

import bitsandbytes
import datasets
import peft
import torch
import transformers
import trl
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from torch.nn.utils.rnn import pad_sequence
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments


MODEL_ID = "Qwen/Qwen3-14B"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
SEED = 2301
MAX_LENGTH = 512


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def subsequence_positions(values: list[int], needle: list[int]):
    for index in range(0, len(values) - len(needle) + 1):
        if values[index : index + len(needle)] == needle:
            yield index


class ChatDataset(torch.utils.data.Dataset):
    def __init__(self, rows: list[dict], tokenizer, max_length: int) -> None:
        self.items: list[dict[str, list[int]]] = []
        assistant_prefix = tokenizer.encode("<|im_start|>assistant\n", add_special_tokens=False)
        im_end = tokenizer.convert_tokens_to_ids("<|im_end|>")
        if not assistant_prefix or im_end is None:
            raise RuntimeError("Qwen assistant boundary tokens could not be resolved")
        for row in rows:
            encoded = tokenizer.apply_chat_template(
                row["messages"],
                tokenize=True,
                add_generation_prompt=False,
                return_dict=True,
                enable_thinking=False,
            )
            input_ids = list(encoded["input_ids"])
            if len(input_ids) > max_length:
                raise RuntimeError(f"{row['id']} has {len(input_ids)} tokens, above configured {max_length}")
            labels = [-100] * len(input_ids)
            assistant_count = 0
            for start in subsequence_positions(input_ids, assistant_prefix):
                content_start = start + len(assistant_prefix)
                try:
                    content_end = input_ids.index(im_end, content_start)
                except ValueError as exc:
                    raise RuntimeError(f"{row['id']} has unterminated assistant content") from exc
                labels[content_start : content_end + 1] = input_ids[content_start : content_end + 1]
                assistant_count += 1
            expected = sum(message["role"] == "assistant" for message in row["messages"])
            if assistant_count != expected or all(value == -100 for value in labels):
                raise RuntimeError(f"{row['id']} assistant masking failed: expected {expected}, found {assistant_count}")
            self.items.append({"input_ids": input_ids, "attention_mask": [1] * len(input_ids), "labels": labels})

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
        return self.items[index]


@dataclass
class Collator:
    pad_token_id: int

    def __call__(self, items: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        ids = [torch.tensor(item["input_ids"], dtype=torch.long) for item in items]
        masks = [torch.tensor(item["attention_mask"], dtype=torch.long) for item in items]
        labels = [torch.tensor(item["labels"], dtype=torch.long) for item in items]
        return {
            "input_ids": pad_sequence(ids, batch_first=True, padding_value=self.pad_token_id),
            "attention_mask": pad_sequence(masks, batch_first=True, padding_value=0),
            "labels": pad_sequence(labels, batch_first=True, padding_value=-100),
        }


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=1.0)
    args = parser.parse_args()
    root = args.project_root.resolve()
    split_dir = root / "training/data/splits"
    output_dir = root / "training/checkpoints/stage23"
    adapter_dir = root / "training/checkpoints/prithi-qwen-lora-v0.1"
    if adapter_dir.exists():
        raise SystemExit(f"refusing to overwrite existing adapter: {adapter_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(SEED)
    torch.manual_seed(SEED)
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required; CPU fallback is disabled")
    if not torch.cuda.is_bf16_supported():
        raise SystemExit("L4 BF16 support check failed")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    rows = {name: read_jsonl(split_dir / f"{name}.jsonl") for name in ("train", "validation", "test")}
    train_data = ChatDataset(rows["train"], tokenizer, MAX_LENGTH)
    validation_data = ChatDataset(rows["validation"], tokenizer, MAX_LENGTH)

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    load_started = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quantization,
        device_map={"": 0},
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    )
    load_seconds = time.perf_counter() - load_started
    suffixes = {name.rsplit(".", 1)[-1] for name, _ in model.named_modules()}
    missing_targets = sorted(set(TARGET_MODULES) - suffixes)
    if missing_targets:
        raise RuntimeError(f"Qwen target modules missing: {missing_targets}")
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(
        model,
        LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules=TARGET_MODULES,
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    model.enable_input_require_grads()
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in model.parameters())
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=1.0e-4,
        lr_scheduler_type="cosine",
        warmup_steps=1,
        optim="paged_adamw_8bit",
        weight_decay=0.0,
        max_grad_norm=1.0,
        bf16=True,
        tf32=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_strategy="steps",
        logging_steps=1,
        logging_first_step=True,
        eval_strategy="steps",
        eval_steps=4,
        eval_on_start=True,
        save_strategy="steps",
        save_steps=4,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        seed=SEED,
        data_seed=SEED,
        remove_unused_columns=False,
        use_cache=False,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
        eval_dataset=validation_data,
        data_collator=Collator(tokenizer.pad_token_id),
        processing_class=tokenizer,
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    train_result = trainer.train()
    training_seconds = time.perf_counter() - started
    validation_metrics = trainer.evaluate()
    peak_vram = torch.cuda.max_memory_allocated()

    adapter_dir.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(adapter_dir, safe_serialization=True)
    tokenizer.save_pretrained(adapter_dir)
    metadata = {
        "stage": 23,
        "adapter_name": "prithi-qwen-lora-v0.1",
        "base_model": MODEL_ID,
        "base_lineage_for_ollama_candidate": "richardyoung/qwen3-14b-abliterated:Q4_K_M -> Qwen/Qwen3-14B",
        "license": "Apache-2.0",
        "dataset": "training/data/curated/prithi_pilot_v1_curated.jsonl",
        "dataset_sha256": sha256(root / "training/data/curated/prithi_pilot_v1_curated.jsonl"),
        "golden_eval_used_for_training": False,
        "seed": SEED,
        "splits": {name: len(value) for name, value in rows.items()},
        "max_sequence_length": MAX_LENGTH,
        "quantization": {"bits": 4, "type": "NF4", "double_quant": True, "compute_dtype": "bfloat16"},
        "lora": {"rank": 16, "alpha": 32, "dropout": 0.05, "target_modules": TARGET_MODULES},
        "training": {
            "epochs": args.epochs,
            "micro_batch": 1,
            "gradient_accumulation": 8,
            "effective_batch": 8,
            "learning_rate": 1.0e-4,
            "scheduler": "cosine",
            "gradient_checkpointing": True,
            "assistant_only_loss": True,
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "datasets": datasets.__version__,
            "peft": peft.__version__,
            "trl": trl.__version__,
            "bitsandbytes": bitsandbytes.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
        },
        "metrics": {
            "model_load_seconds": load_seconds,
            "training_seconds": training_seconds,
            "train_loss": train_result.metrics.get("train_loss"),
            "validation_loss": validation_metrics.get("eval_loss"),
            "global_steps": trainer.state.global_step,
            "peak_vram_bytes": peak_vram,
            "trainable_parameters": trainable,
            "total_parameters_visible": total,
        },
    }
    (adapter_dir / "training_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (adapter_dir / "README.md").write_text(
        "# Prithi Qwen LoRA v0.1\n\n"
        "Stage 23 pilot adapter for `Qwen/Qwen3-14B`. Apache-2.0 upstream; retain attribution and license notices when redistributing. "
        "Trained only on the curated pilot splits; `evals/prithi_golden_v2.jsonl` was not used for training. Do not load in production without a separate promotion decision.\n",
        encoding="utf-8",
    )
    metadata["metrics"]["adapter_size_bytes"] = directory_size(adapter_dir)
    (adapter_dir / "training_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "stage23_training_result.json").write_text(json.dumps({"train": train_result.metrics, "validation": validation_metrics, "metadata": metadata}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
