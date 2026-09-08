# System requirements

Prithi is designed for Linux. A modern NVIDIA GPU is recommended; the current known-good device is an NVIDIA L4 with 24 GB nominal VRAM.

## Core software

- Python 3.10 or newer (the current tested environment uses Python 3.10.20)
- NVIDIA driver compatible with the installed CUDA runtime
- CUDA-capable PyTorch for diagnostics and optional model workflows
- CUDA 12 cuBLAS compatibility libraries for CTranslate2/faster-whisper
- cuDNN 9
- FFmpeg for common audio formats
- Ollama for the local OpenAI-compatible conversational model
- Git and curl for setup and restoration

Do not replace NVIDIA drivers as part of the project setup. Use a GPU server image that already supplies a compatible driver.

## Cloud services

Google Cloud Text-to-Speech must be enabled for the selected Google project. Supply a service-account JSON locally through `GOOGLE_APPLICATION_CREDENTIALS`; never store it in Git.

## Storage and networking

- Persistent writable project storage is required.
- `gemma3:12b` uses about 8.1 GB on disk.
- Ollama runtime/CUDA libraries use about 2.1 GB.
- Whisper `large-v3-turbo` uses about 1.6 GB.
- Allow extra space for Python wheels, generated WAVs, future models, and logs.
- Ollama binds locally to TCP port `11434`; it is not exposed publicly by these scripts.

Large models live under `runtime/`, which is intentionally ignored by Git.
