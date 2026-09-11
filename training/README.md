# Prithi training workspace

This directory contains candidate data and offline tooling only. Nothing here is loaded by the production Prithi web app.

- `data/raw/`: generated or authored candidates awaiting review
- `data/curated/`: approved/edited data assembled by a reviewer
- `data/splits/`: deterministic training/validation/test derivatives
- `config/`: taxonomy and canonical schema
- `scripts/`: generation, review, validation, deduplication, conversion and split tools
- `reports/`: validator and duplicate reports

Never train directly from `raw/`. Never place the golden evaluation set in a training split.
