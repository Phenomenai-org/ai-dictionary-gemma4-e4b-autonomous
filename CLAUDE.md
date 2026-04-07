# CLAUDE.md — Gemma 4 e4b Autonomous Dictionary

## Documentation Maintenance

When implementing significant changes, update these documents as part of the same PR:

- **CHANGELOG.md** — Add a bullet under the current month
- **ROADMAP.md** — Move items between sections as they land
- **README.md** — Update if API table, features, or Browse section changes

## API Documentation Maintenance

When API endpoints change, keep these in sync:

- **openapi.json** — Endpoint paths, schemas, examples
- **docs/for-machines/index.json** — Machine-readable catalog
- **docs/for-machines/index.html** — Human-readable API page

## Dictionary-Specific Notes

- Paradigm: Autonomous (single-model self-generation)
- Model: Gemma 4 e4b (local quantized open-weights model)
- Main site listing: Update `Phenomenai-org.github.io/docs/dictionaries/index.html` when status changes
- Worker: `ai-dictionary-gemma4-e4b-autonomous-proxy` on Cloudflare
- API base: `https://phenomenai.org/gemma4-e4b-autonomous/api/v1`
- GitHub repo: `https://github.com/Phenomenai-org/ai-dictionary-gemma4-e4b-autonomous`

## Generation Notes

Terms in this dictionary are generated autonomously by a local Gemma 4 e4b model. The generation pipeline runs offline and submits to this repo. Cross-model consensus ratings are collected from other models after terms are accepted.
