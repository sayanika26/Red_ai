# Stage 23 base-model lineage and license

## Verified lineage

The installed evaluation model is `richardyoung/qwen3-14b-abliterated:Q4_K_M` (Ollama digest prefix `6158df281780`, approximately 9.0 GB). Its publisher's matching Hugging Face GGUF model card identifies `Qwen/Qwen3-14B` as `base_model` and describes the artifact as an abliterated, quantized derivative.

Training will **not** use the Ollama GGUF/Q4 artifact. The pilot uses the upstream full-precision lineage checkpoint `Qwen/Qwen3-14B`, loaded through Transformers with 4-bit NF4 QLoRA. This is the compatible official chat/instruct lineage, not the separate `Qwen/Qwen3-14B-Base` pretraining checkpoint.

This distinction matters: the exported adapter learns the Prithi pilot behavior on the official Qwen3-14B checkpoint; it does not reproduce or redistribute the publisher's GGUF abliteration transformation.

## License result

`Qwen/Qwen3-14B` declares the Apache License 2.0 and includes the Apache-2.0 license text. Apache-2.0 permits use, modification, creation of derivative works, and redistribution, including adapter weights, provided its license/notice and attribution requirements are followed. Modified distributions must identify changes and preserve relevant copyright, patent, trademark, and attribution notices.

**Result: compatible for this fine-tuning run and later adapter redistribution with Apache-2.0 attribution/notice compliance.**

## Sources checked

- Official upstream model and usage: <https://huggingface.co/Qwen/Qwen3-14B>
- Official upstream license: <https://huggingface.co/Qwen/Qwen3-14B/blob/main/LICENSE>
- Publisher's GGUF lineage metadata: <https://huggingface.co/richardyoung/Qwen3-14B-abliterated-GGUF>
- Installed Ollama tag metadata: <https://ollama.com/richardyoung/qwen3-14b-abliterated/tags>

No production model configuration is changed by this decision.
