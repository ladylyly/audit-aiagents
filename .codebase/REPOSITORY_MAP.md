# Repository Map

Short answer to “where is what?” in this repository.

## Directory Layout

```text
automating-supplychain-aiagent/
├── README.md                     # Main setup and usage note
├── docker-compose.yml            # Review/runtime stack
├── .codebase/                    # Short project notes kept outside runtime
│   ├── REPOSITORY_MAP.md         # This file
│   ├── ARCHITECTURE.md
│   ├── INTEGRATIONS.md
│   └── TESTING.md
├── backend/                      # Python backend runtime
│   ├── api/
│   │   └── server.py             # Flask API entrypoint
│   ├── agents/
│   │   ├── orchestrator/         # Main audit flow
│   │   ├── technical_verification/
│   │   ├── compliance/
│   │   ├── certification/
│   │   └── esg/
│   ├── services/
│   │   ├── ipfs_fetcher.py       # CID fetch layer
│   │   ├── provenance_graph.py   # Provenance graph builder
│   │   └── tool_registry/        # Active tool contracts and explanations
│   ├── integrations/
│   │   ├── llm_client.py         # LLM-backed summaries and QA
│   │   └── technical_verifier_tools/
│   │       ├── generate_publish_vc_dag.mjs
│   │       ├── verify_vc_signature.mjs
│   │       ├── check_vc_anchors.mjs
│   │       ├── check_price_commitment_anchors.mjs
│   │       └── anchor_vc_hashes.mjs
│   ├── assets/
│   │   ├── certification/
│   │   ├── compliance/
│   │   └── esg/
│   ├── .env.example
│   ├── Dockerfile
│   ├── paths.py
│   └── requirements.txt
├── frontend/                     # React frontend
│   ├── src/
│   │   ├── app/
│   │   ├── pages/
│   │   ├── features/audit/
│   │   └── styles/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── contracts/
│   ├── deploy_stack/             # Truffle deployment workspace for product clones
│   │   └── output/product_clones.json
│   └── tools/                    # Active tool contracts
├── docs/
│   ├── current/                  # Kept runtime flow notes
├── data/
│   ├── generated/                # Generator output location
│   └── reports/                  # Stored audit reports
├── tools/
│   └── zkp-backend/              # Rust zkp-cli source
├── thesis/                       # Thesis writing and source material
├── Makefile                      # Thesis build helpers
└── .venv/                        # Optional local Python environment
```
