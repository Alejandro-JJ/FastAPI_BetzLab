# Restarting The System For Testing

This guide is the recommended restart flow now that multiple tools are
available. It is safe to run repeatedly while developing and testing.

Prerequisites: Docker Engine + Docker Compose plugin running.

## 1. Full restart (clean, repeatable)

From the repository root:

```bash
docker compose down
docker compose up --build -d
```

This restarts core services:

- `db` (PostgreSQL)
- `minio` (object storage)
- `backend` (FastAPI)
- `scheduler` (job dispatcher)
- `frontend` (UI)

Check service health:

```bash
docker compose ps
docker compose logs --tail=80 backend scheduler
```

Backend is ready when logs show Uvicorn started on port `8000`.

## 2. Rebuild worker images for enabled tools

Workers are not started by `docker compose up`; they are launched on-demand by
the scheduler. Build all worker images used for tests:

```bash
docker compose --profile tools build beadbuddy-worker traction-force-worker
```

Verify images exist:

```bash
docker images | grep -E "beadbuddy-worker|traction-force-worker"
```

Re-run this build command whenever you modify code under:

- `backend/tools/beadbuddy/`
- `backend/tools/traction_force/`
- `backend/worker_base/`

## 3. Open test endpoints

- Frontend: http://localhost:4173
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

MinIO credentials:

- User: `minioadmin`
- Password: `minioadmin`

## 4. Functional testing checklist

1. Log in from the frontend.
2. Confirm tools appear in dashboard.
3. Run one BeadBuddy job (`.tif` upload -> process -> download ZIP).
4. Run one Traction Force job (upload Before + After -> process -> download ZIP).
5. Confirm each job reaches `completed` and produces result + metadata.

Optional scheduler visibility during tests:

```bash
docker compose logs -f scheduler
```

You should see dispatch lines like:

```text
Dispatching job <id> (beadbuddy) -> beadbuddy-worker:latest
Dispatching job <id> (traction_force) -> traction-force-worker:latest
```

## 5. Fast restart during iterative development

Use this when you changed only API/frontend/scheduler compose services (not worker images):

```bash
docker compose up --build -d backend scheduler frontend
```

If worker code changed, also rebuild workers:

```bash
docker compose --profile tools build beadbuddy-worker traction-force-worker
```

## 6. Hard reset (wipe test data)

If you want a completely clean test environment (users, uploads, jobs, results):

```bash
docker compose down -v
docker compose up --build -d
docker compose --profile tools build beadbuddy-worker traction-force-worker
```

## 7. MinIO space cleanup (maintainer runbook)

Use this when uploads fail with storage errors such as `XMinioStorageFull` or
`Upload failed: object storage is full`.

### 7.1 Check current disk usage

From repository root:

```bash
df -h /
docker system df
docker compose exec minio sh -lc "df -h /data && du -sh /data/* 2>/dev/null | sort -h | tail -n 30"
```

Notes:

- MinIO stores objects in Docker volume `beadbuddy_minio_data` mounted at `/data` in the container.
- If host `/` is near 100%, MinIO can still reject uploads even after deleting objects.

### 7.2 Clear only MinIO objects (keep Postgres users/jobs)

```bash
docker compose stop backend scheduler
docker compose exec minio sh -lc "rm -rf /data/*"
rm -rf backend/uploads/* backend/results/*
docker compose start minio backend scheduler
```

### 7.3 Free host Docker disk space (if host is still full)

```bash
docker builder prune -af
docker image prune -af
```

Then verify free space again:

```bash
df -h /
docker compose exec minio sh -lc "df -h /data"
```

### 7.4 Rebuild worker images if they were pruned

```bash
docker compose --profile tools build beadbuddy-worker traction-force-worker
```

### 7.5 Full destructive reset (wipe DB + MinIO)

```bash
docker compose down -v
docker compose up --build -d
docker compose --profile tools build beadbuddy-worker traction-force-worker
```

This is the fastest way to return to a clean test environment.

## Troubleshooting

- Jobs stay `queued`: worker image missing. Rebuild with `--profile tools build`.
- Job fails with `pull access denied` / `image not found` for `traction-force-worker` or `beadbuddy-worker`: worker images were removed locally (often after `docker image prune`). Rebuild with:

```bash
docker compose --profile tools build beadbuddy-worker traction-force-worker
```
- Job fails quickly: inspect `docker compose logs scheduler` and job status at `/job/{job_id}`.
- UI cannot load tools: check `docker compose logs backend`.
- Scheduler Docker permission errors: ensure `/var/run/docker.sock` is accessible to Docker and scheduler.

## Related docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/ADDING_A_NEW_TOOL.md](docs/ADDING_A_NEW_TOOL.md)
- [docs/INTEGRATING_AN_EXISTING_FUNCTION.md](docs/INTEGRATING_AN_EXISTING_FUNCTION.md)
