# Deploy Stack

This directory holds the Python-only deployment shape for ParaLLM.

## Current Shape

- `backend`: Python ASGI shell + control plane on `:8787`
- background loop jobs and target dispatches run as Python subprocesses inside the same image for the current single-node path

## Local Bring-Up

Portable local path:

```bash
python -m pip install -r requirements-dev.txt
python scripts/run_local_stack.py
```

Optional compatibility path with the legacy resident runtime service:

```bash
python scripts/run_local_stack.py --with-runtime-service
```

Docker bring-up:

```bash
docker compose -f deploy/compose.yml up --build
```

Hosted-dev dependency bring-up:

```bash
docker compose -f deploy/compose.hosted-dev.yml up --build
```

Hosted-dev with a dedicated runtime service:

```bash
docker compose \
  -f deploy/compose.hosted-dev.yml \
  -f deploy/compose.hosted-dev.runtime-service.yml \
  up --build
```

Then open:

- `http://127.0.0.1:${LOOP_PUBLISHED_PORT:-8787}/health`
- `http://127.0.0.1:${LOOP_PUBLISHED_PORT:-8787}/`
- `http://127.0.0.1:${LOOP_PUBLISHED_PORT:-8787}/v1/system/topology`

## Environment Contract

The repo-level `.env.example` documents the current deployment-facing variables:

- `LOOP_HOST`, `LOOP_PORT`
- `LOOP_PUBLISHED_PORT`
- `LOOP_POSTGRES_PUBLISHED_PORT`
- `LOOP_REDIS_PUBLISHED_PORT`
- `LOOP_OBJECT_STORE_PUBLISHED_PORT`
- `LOOP_OBJECT_STORE_CONSOLE_PUBLISHED_PORT`
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
- `LOOP_RUNTIME_HOST`, `LOOP_RUNTIME_PORT`
- `LOOP_RUNTIME_SERVICE_URL`
- `LOOP_SECRET_PROVIDER_URL`
- `LOOP_SECRET_PROVIDER_TOKEN`
- `LOOP_SECRET_PROVIDER_HEALTHCHECK_URL`

The backend is the primary entrypoint now. The runtime-service variables remain for compatibility/testing flows, not as the main product boundary.

## Service Boundary

Current single-node boundary:

- `backend`
  - serves the shell
  - owns `/v1/*` control-plane routes
  - launches background loop and dispatch subprocesses
  - reads and writes `data/` state, jobs, artifacts, and eval outputs
- `runtime/engine.py`
  - remains the reasoning/runtime library used by the backend job runners
- `runtime/service.py`
  - optional runtime execution service when the backend is configured with `LOOP_RUNTIME_EXECUTION_BACKEND=runtime_service`

Hosted target boundary:

- stateless Python control-plane containers
- queue and durable state separated from web serving
- artifact storage abstracted from local disk
- secret retrieval moved away from local transitional files

The repo now exposes that boundary through:

- `GET /v1/system/topology`
- `GET /v1/system/infrastructure`

The hosted-dev proof path now lives in:

- `python scripts/qa_hosted_dev_stack.py`
- `python scripts/package_hosted_bundle.py`

That smoke is intentionally strict:

- it fails immediately if Docker is not installed/running
- it boots `deploy/compose.hosted-dev.yml`
- it verifies the live topology reports `redis`, `postgres`, `object_storage`, and `docker_secret`
- it creates tasks and background loops through the live API
- it proves Postgres rows exist and MinIO objects are written

The hosted-dev compose file includes explicit dependency targets for:

- `postgres`
- `redis`
- `minio`

The hosted runtime-service override adds:

- `runtime`
- backend runtime delegation through `LOOP_RUNTIME_EXECUTION_BACKEND=runtime_service`
- a dedicated `deploy/runtime/Dockerfile` image with the same Python dependency set as the backend image

In the current codebase that means:

- Redis is now a real queue participant for background loop ordering and ready target-dispatch launch handoff
- Postgres is now the real metadata backend for control-plane state, jobs, task snapshots, and eval run state when `LOOP_METADATA_BACKEND=postgres`
- object storage is now the real backend for runtime checkpoints, saved output artifacts, session archives, and export bundles when `LOOP_ARTIFACT_BACKEND=object_storage`
- mounted secret files are now a real read-only backend for OpenAI key pools when `LOOP_SECRET_BACKEND=docker_secret`
- eval suite/arm manifests are still filesystem-backed in this phase

## Persistence

Two named volumes are created by `compose.yml`:

- `loop_data` for state, tasks, outputs, jobs, evals
- `loop_auth` for the transitional local `Auth.txt` secret file used only by the local compose path

## Notes

- The backend service serves both the shell and the `/v1/*` control-plane routes.
- Docker is now the packaging path; the legacy web-server stack is no longer part of the active runtime path.
- Hosted-dev now defaults to `LOOP_SECRET_BACKEND=docker_secret` with `/run/secrets/openai_api_keys`.
- Env-backed secrets are still supported through `LOOP_SECRET_BACKEND=env` and `LOOP_OPENAI_API_KEYS`.
- External read-only secret providers are now supported through `LOOP_SECRET_BACKEND=external`, `LOOP_SECRET_PROVIDER_URL`, and optional bearer auth via `LOOP_SECRET_PROVIDER_TOKEN`.
- `python scripts/package_hosted_bundle.py` creates a portable handoff bundle under `build/hosted-bundle/` for Docker-capable rigs.
