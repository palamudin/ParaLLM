# Python Control Plane

This directory now holds the active ParaLLM control plane and Python-served shell.

## Current Scope

The scaffold currently exposes these endpoints:

- `GET /`
- `GET /index.html`
- `GET /health`
- `GET /v1/system/topology`
- `GET /v1/system/infrastructure`
- `GET /v1/auth/status`
- `POST /v1/auth/keys`
- `GET /v1/state`
- `POST /v1/state/reset`
- `GET /v1/history`
- `GET /v1/events`
- `GET /v1/steps`
- `GET /v1/artifacts/{name}`
- `GET /v1/artifact`
- `GET /v1/evals/history`
- `POST /v1/evals/runs`
- `GET /v1/evals/artifact`
- `GET /v1/evals/artifacts/{run_id}/{artifact_id}`
- `POST /v1/draft`
- `POST /v1/tasks`
- `POST /v1/session/reset`
- `POST /v1/session/replay`
- `GET /v1/session/export`
- `POST /v1/runtime/apply`
- `POST /v1/workers/update`
- `POST /v1/workers/add`
- `POST /v1/positions/model`
- `POST /v1/loops`
- `POST /v1/loops/cancel`
- `POST /v1/jobs/manage`
- `POST /v1/targets/background`
- `POST /v1/rounds`
- `POST /v1/targets/run`

Those endpoints read and write the local `data/` tree directly.

They also honor the same deployment env overrides used by the container path:

- `LOOP_ROOT`
- `LOOP_DATA_ROOT`
- `LOOP_AUTH_FILE`
- `LOOP_DEPLOYMENT_PROFILE`
- `LOOP_QUEUE_BACKEND`
- `LOOP_METADATA_BACKEND`
- `LOOP_ARTIFACT_BACKEND`
- `LOOP_SECRET_BACKEND`
- `LOOP_SECRET_FILE`
- `LOOP_RUNTIME_EXECUTION_BACKEND`
- `LOOP_DATABASE_URL`
- `LOOP_REDIS_URL`
- `LOOP_OBJECT_STORE_URL`
- `LOOP_OBJECT_STORE_BUCKET`
- `LOOP_OBJECT_STORE_HEALTHCHECK_URL`
- `LOOP_OBJECT_STORE_ACCESS_KEY`
- `LOOP_OBJECT_STORE_SECRET_KEY`
- `LOOP_OBJECT_STORE_REGION`
- `LOOP_OPENAI_API_KEYS`
- `LOOP_RUNTIME_SERVICE_URL`
- `LOOP_SECRET_PROVIDER_URL`
- `LOOP_SECRET_PROVIDER_TOKEN`
- `LOOP_SECRET_PROVIDER_HEALTHCHECK_URL`

## Why This Exists

The active runtime shape is now:

- static frontend
- Python ASGI API
- Python worker/runtime services
- queue + database + object storage behind clean interfaces

## Run Locally

Install the backend dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the scaffold from the repo root:

```bash
python scripts/run_local_stack.py
```

Then open:

```text
http://127.0.0.1:8787/health
```

The topology contract is exposed at:

```text
http://127.0.0.1:8787/v1/system/topology
```

Infrastructure readiness is exposed at:

```text
http://127.0.0.1:8787/v1/system/infrastructure
```

## What Is Ported So Far

- path and storage model for the local `data/` tree
- state read model with loop/dispatch recovery view
- history/read-review payload assembly
- eval history and eval artifact reads
- auth-pool status readout
- auth key-pool mutation parity for append/replace/remove/clear
- draft normalization and persistence
- task creation with task snapshots, state reset, and event/step logging
- session reset with archive + carry-forward draft rebuild
- session replay and export bundle generation
- eval run queueing for the isolated sibling eval subsystem
- runtime/settings application to the active task
- worker draft mutation and adversarial roster growth
- per-position model changes for active task workers and summarizer
- background loop job creation, cancellation, retry, and resume
- Python background loop runner for the first hosted-compatible job path
- background target-dispatch queueing for commander, workers, commander-review, summarizer, and Answer Now
- sync target execution for parity with the existing manual dispatch surface
- Python-served shell defaults for same-origin `/v1/*` use
- typed topology reporting for queue, metadata, artifacts, secrets, and runtime execution backends
- selectable runtime execution backend:
  - embedded engine subprocess by default
  - optional `runtime_service` path for explicit service-boundary testing
- selectable queue backend:
  - `local_subprocess` for the current local file + subprocess path
  - `redis` for real background loop ordering and ready dispatch-launch handoff
- selectable metadata backend:
  - `json_files` for the local default
  - `postgres` for real shared state, job metadata, task snapshots, and eval run state used by both the backend and runtime engine
- selectable artifact backend:
  - `filesystem` for the local default
  - `object_storage` for real runtime checkpoints, saved output artifacts, session archives, and export bundles
- selectable secret backend:
  - `local_file` for the transitional local `Auth.txt` path
  - `env` for env-provided key pools from `LOOP_OPENAI_API_KEYS` / `OPENAI_API_KEYS`
  - `docker_secret` for mounted read-only secret files such as `/run/secrets/openai_api_keys`
  - `external` for a read-only HTTP secret provider that returns newline-delimited keys or JSON `{ "keys": [...] }`
- infrastructure readiness probes for redis, postgres, object storage, env/local/docker-secret backends, and runtime-service execution

## What Is Not Done Yet

- move the remaining metadata surfaces beyond state/jobs/tasks off transitional JSON files
- move eval suite/arm manifests and per-replicate eval artifacts behind hosted-ready storage abstractions
- move the remaining queue metadata off transitional JSON files now that Redis owns real scheduling seams
- modularize the frontend beyond the current single-file shell
- replace the remaining legacy compatibility labels in QA/docs with Python-native naming

## Current Principle

The shell and control plane now run through Python only. The next work is hardening, storage evolution, and cleanup.

## Tests

The first regression guard for the scaffold lives in:

```text
backend/tests/test_storage.py
```

Run it with:

```bash
python -m unittest backend.tests.test_storage backend.tests.test_control backend.tests.test_metadata backend.tests.test_queueing backend.tests.test_artifacts backend.tests.test_jobs backend.tests.test_dispatch backend.tests.test_settings backend.tests.test_sessions backend.tests.test_evals backend.tests.test_runtime_auth backend.tests.test_app
```

## Container Note

The control plane is the active service in the Python-only Docker stack under [deploy/README.md](../deploy/README.md).

## Frontend Path

The Python backend now serves the shell directly:

```text
http://127.0.0.1:8787/
```

The Python-only smoke lives here:

```bash
python scripts/qa_python_crossover_check.py
```
