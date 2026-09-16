# Starting the system locally (step by step)

Follow this top to bottom to get the whole stack running and process one
real job end to end. Everything runs through Docker Compose - no local
Python/Node install is required.

Prerequisites: Docker and the Docker Compose plugin installed and running.

## 1. Start the core services

From the repository root:

```bash
docker compose up --build
```

This builds and starts:

- `db` - PostgreSQL (internal only - not published to the host)
- `minio` - object storage, API on port 9000, web console on port 9001
- `backend` - FastAPI, port 8000
- `scheduler` - watches for queued jobs and dispatches worker containers
- `frontend` - React app served on port 4173

Wait until you see the backend log `Uvicorn running on http://0.0.0.0:8000`.
Leave this terminal running; open a new terminal for the next steps.

## 2. Build the BeadBuddy worker image

The scheduler only starts containers from images that already exist, so
build the one enabled tool's worker image once:

```bash
docker compose --profile tools build beadbuddy-worker
```

This produces the `beadbuddy-worker:latest` image referenced by
`backend/tool_registry.py`. Repeat this command any time you change
`backend/tools/beadbuddy/processor.py`.

## 3. Open the app

- Frontend: http://localhost:4173
- API docs (Swagger UI): http://localhost:8000/docs
- MinIO console: http://localhost:9001 (login `minioadmin` / `minioadmin`)

## 4. Create an account and log in

In the frontend at http://localhost:4173:

1. Click through to Register, create any email/password.
2. Log in with those credentials.
3. You land on the tool dashboard. "BeadBuddy" should be enabled; the other
   three tools show "Coming soon" (expected - they have no worker image yet).

## 5. Get a test TIFF stack

Use any multi-page `.tif`/`.tiff` file you have. 

## 6. Run a job through the UI

1. Open "BeadBuddy" from the dashboard.
2. Click **Upload** and pick your `.tif` file.
3. Once uploaded, the source slice appears and the slice slider is enabled.
4. Click **Process**. The status text will cycle through
   `queued -> dispatching -> running -> completed`.
5. When it says "Processing finished. Result ready.", the processed panel
   shows the output and **Download** becomes enabled.
6. Click **Download** to get a ZIP with the result TIFF and its metadata
   JSON.

## 7. Watch it happen at the infrastructure level (optional but useful)

In another terminal, while a job is running:

```bash
docker ps --filter "name=job-"
```

You should briefly see a container named `job-<job-id>` appear and then
disappear on its own (`remove=True` in `scheduler/dispatcher.py`) - this is
the temporary worker container that processed exactly one job.

Scheduler logs:

```bash
docker compose logs -f scheduler
```

You'll see lines like:

```
Dispatching job <id> (beadbuddy) -> beadbuddy-worker:latest
```

Object storage contents (uploads and results) are visible in the MinIO
console at http://localhost:9001, inside the `beadbuddy` bucket, under
`uploads/` and `results/`.

## 8. Stopping everything

```bash
docker compose down
```

Add `-v` to also delete the Postgres and MinIO volumes (all users, jobs, and
files):

```bash
docker compose down -v
```

## Troubleshooting

- **Dashboard shows no tools / an error loading tools** - the backend isn't
  reachable yet; check `docker compose logs backend`.
- **Job stays in `queued` forever** - the scheduler can't find the worker
  image. Confirm step 2 ran successfully:
  `docker images | grep beadbuddy-worker`.
- **Job goes to `failed` immediately** - check
  `docker compose logs scheduler` for the error message recorded on the job,
  or query it directly: `GET /job/{job_id}` in the Swagger UI at `/docs`.
- **`docker: permission denied` from the scheduler** - the scheduler
  container needs access to `/var/run/docker.sock`; on Linux this usually
  means your user needs to be in the `docker` group, or you're running
  rootless Docker with a different socket path (adjust the volume mount in
  `docker-compose.yml` accordingly).

## Next step

To add a new analysis tool instead of just running BeadBuddy, see
[ADDING_A_NEW_TOOL.md](ADDING_A_NEW_TOOL.md) or, if you already have a
plain `analysis(image, params) -> image` function,
[INTEGRATING_AN_EXISTING_FUNCTION.md](INTEGRATING_AN_EXISTING_FUNCTION.md).
