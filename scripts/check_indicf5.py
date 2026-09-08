import platform

import torch
from transformers import AutoModel


def main() -> None:
    print(f"Python version: {platform.python_version()}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none"
    print(f"GPU model: {gpu_name}")
    print("IndicF5 environment ready")


if __name__ == "__main__":
    main()
