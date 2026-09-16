## BetzLab FastAPI project - Analysis tools

A modular toolbox: each analysis tool runs in its own temporary, containerized
worker, started on demand by a scheduler when a job is queued. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/ADDING_A_NEW_TOOL.md](docs/ADDING_A_NEW_TOOL.md) to add a tool.

- FastAPI -> control plane API (auth, uploads, job creation)
- PostgreSQL -> users, files, jobs
- MinIO (S3-compatible) -> uploaded datasets and results
- Scheduler -> launches one worker container per queued job
- React -> frontend, dashboard and tool workspace driven by the tool registry

## Quick start

See [docs/STARTUP.md](docs/STARTUP.md) for a full step-by-step walkthrough to
run and test the whole system locally right now.

```bash
docker compose up --build              # db, minio, backend, scheduler, frontend
docker compose --profile tools build   # build worker images (e.g. beadbuddy-worker)
```

- Frontend: http://localhost:4173
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001 (minioadmin / minioadmin)

Stop everything with `docker compose down` (add `-v` to also wipe the
database and object storage volumes).

## Status

- Auth (register/login), file upload, job queue, and worker dispatch work
  end to end for the BeadBuddy tool.
- BeadBuddy's `processor.py` currently performs a placeholder stack copy;
  swap in the real segmentation logic (e.g. from `bb_funcs/`) there.
- MBR analysis, Traction Force Microscopy, and 3D Segmentation are registered
  as "coming soon" tools, ready for a processor + worker image each.

