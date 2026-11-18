# IntentFlow Reproducibility Inventory

## Repository components

- backend: `backend/`
- frontend: `frontend/`
- testbed: `testbed/topology/`
- evaluation scripts: `evaluation/`
- unit tests: `tests/`, `frontend/tests/`
- existing reports: `docs/`
- deployment: `deploy/`, `scripts/`

## Backend dependencies

Authoritative direct application/test versions are in `requirements.in`; `requirements.txt` is the hash-locked dependency graph.

Key dependencies include:

- Pydantic 2.13.5;
- FastAPI 0.141.1;
- Uvicorn 0.54.0;
- pytest 9.1.1;
- OpenAI SDK 3.45.0;
- provider-specific SDK/HTTP dependencies as pinned in `requirements.txt`.

The live testbed additionally requires Linux Mininet, Open vSwitch, iproute2, iperf3, ping, ethtool, Ryu 4.34, and system privileges.

## System setup

The repository provides:

```bash
bash scripts/setup_system.sh
bash scripts/setup_ryu_venv.sh
sudo python3 -m pip install --break-system-packages --require-hashes --only-binary=:all: -r requirements.txt
```

The setup script notes that Ryu uses `.venv-ryu/`, while the main application dependencies use system Python.

Do not claim the environment is reproducible until its Linux distribution, kernel, Mininet/OVS/Ryu versions, CPU count, and kernel datapath are documented for each run.

## Backend environment variables

Local `.env.example`:

- `INTENTFLOW_ENVIRONMENT=development`
- `INTENTFLOW_AUTH_DISABLED=true`
- `INTENTFLOW_API_HOST=127.0.0.1`
- `INTENTFLOW_API_PORT=8000`
- `INTENTFLOW_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`
- `INTENTFLOW_COOKIE_SECURE=false`
- `LLM_PROVIDER=mock`

Additional backend variables found in source/docs:

- `INTENTFLOW_API_TOKEN`
- `INTENTFLOW_RYU_BASE_URL`
- `INTENTFLOW_WORKER_SOCKET`
- `INTENTFLOW_TOPOLOGY_DB`
- `INTENTFLOW_EVIDENCE_JSON_DIR`
- `INTENTFLOW_EVIDENCE_MARKDOWN_DIR`
- `INTENTFLOW_EVIDENCE_GID`
- `INTENTFLOW_API_GID`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS`
- `GROQ_API_KEY`, `GROQ_MODEL`

## Frontend environment variables

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_INTENTFLOW_AUTH_DISABLED`

Frontend examples are in `frontend/.env.example`.

## Backend startup

Development examples in the README:

```bash
python3 -m uvicorn backend.api.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

A production worker requires dedicated accounts, groups, protected socket setup, evidence directories, and systemd configuration. See `docs/systemd-deployment.md`.

## Tests

Backend:

```bash
pytest -q
```

Core backend subset used by this audit:

```bash
pytest -q tests/test_topology_graph.py tests/test_path_enumeration.py tests/test_constraint_evaluation.py tests/test_candidate_selection.py tests/test_planner_contract.py tests/test_topology_catalog.py tests/test_intent_normalization.py tests/test_canonical_intent.py tests/test_llm_mock.py tests/test_bandwidth_decision.py tests/test_latency_decision.py
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

## Live systematic bandwidth experiment

```bash
sudo mn -c
sudo PYTHONPATH=. python3 evaluation/run_evaluation.py
PYTHONPATH=. python3 evaluation/summarize.py
PYTHONPATH=. python3 evaluation/build_final_report.py
```

Useful split invocation:

```bash
sudo PYTHONPATH=. python3 evaluation/run_evaluation.py --scenarios feasible,boundary
sudo PYTHONPATH=. python3 evaluation/run_evaluation.py --modes ONE_SHOT --repetitions 5
```

This script uses real network operations and infrastructure cleanup. It must not be described as simulation.

## Live generalized constraint experiment

```bash
sudo mn -c
sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py bandwidth
sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py latency
sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py combined
sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py minimize-latency
sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py maximize-bandwidth
sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py constrained-minimize-latency
```

## Offline result rebuilding

```bash
PYTHONPATH=. python3 evaluation/summarize.py
PYTHONPATH=. python3 evaluation/build_final_report.py
```

These scripts read existing artifacts and do not rerun Mininet/Ryu.

## Missing configuration and data

- original `evaluation_runs_*.json` source sweep files are absent from `evaluation/results/`;
- no external topology seed corpus is retained for paper experiments;
- no repeated packet-loss dataset is retained;
- no complete generalized-latency run artifact is retained;
- no baseline comparison artifacts are retained;
- no environment file for a dedicated hardware or repeated CI testbed is retained;
- no exact seed or repetition ordering is retained for each live sweep row;
- no raw ping/iperf3 log directory is retained;
- no complete test environment lock for the frontend/native packages is retained.
