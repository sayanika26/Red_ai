# Model and adapter backup strategy

Public/runtime model binaries are not stored in normal Git. The bootstrap downloads the required Ollama and faster-whisper models into ignored persistent project storage.

LoRA adapters under `training/checkpoints/` may contain valuable private work and must be backed up separately. Supported approaches:

1. A private Hugging Face model repository with access controls and a documented base-model/license relationship.
2. Private cloud object storage with encryption, retention policy, and checksums.
3. An encrypted archive stored outside the Studio and outside the Git working tree.

For every adapter record its dataset version, base checkpoint, license, training configuration, Git commit, and SHA-256 checksums. Do not merge or publish an adapter until its license, data rights, and safety evaluation are reviewed.
