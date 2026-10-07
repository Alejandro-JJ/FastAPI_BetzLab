# Adding a new tool

This walks through everything needed to add a new analysis tool to the
BetzLab Toolbox: it appears on the dashboard, gets its own upload/run/download
workflow in the browser, and runs in its own temporary worker container.

You do not need to touch `main.py`, the scheduler, or any frontend page to do
this - the dashboard and workspace are both driven by the tool registry.

If you already have a plain `analysis(image, params) -> image` function and
just want to plug it in, see
[INTEGRATING_AN_EXISTING_FUNCTION.md](INTEGRATING_AN_EXISTING_FUNCTION.md)
for a more direct, copy/paste walkthrough of these same steps.

## 1. Register the tool

Add one entry to `backend/tool_registry.py`:

```python
Tool(
    id="mbr_analysis",
    name="MBR analysis",
    description="Spherical harmonics decomposition of segmented beads.",
    order=2,
    enabled=True,
    worker_image="mbr-analysis-worker:latest",
    parameters=(
        ToolParameter("lmax", "Max degree", 8, 1, 15, 1),
        ToolParameter("smoothing", "Smoothing", 0, 0, 20, 1),
    ),
)
```

- `id` must be unique and is used as the Docker image tag prefix and the
  Celery-free job's `tool_id` column.
- `enabled=False` shows the card as "Coming soon" and disables it - useful
  while you are still building the worker image.
- `parameters` auto-generates the number inputs shown in the browser; the
  frontend needs no changes to render them.

## 2. Write the processing function

Create `backend/tools/mbr_analysis/processor.py` with one function:

```python
from pathlib import Path
from worker_base.contracts import ToolContext, ToolResult

def process(input_path: Path, context: ToolContext) -> ToolResult:
    # context.params  -> dict of the parameters submitted from the browser
    # context.workdir -> scratch directory, already created for this job
    # context.job_id  -> the Job.id row this run belongs to

    result_path = context.workdir / f"result_{input_path.stem}.tif"
    # ... run the real analysis here, write output to result_path ...

    return ToolResult(
        result_path=result_path,
        metadata={"job_id": context.job_id, "parameters": context.params},
    )
```

This function is the only place tool-specific code lives. It never touches
the database, object storage, or HTTP - `worker_base/runner.py` handles
downloading the input, uploading the output, and updating the job status
around this call. If your analysis needs heavier dependencies (e.g. a
different NumPy/SciPy stack, GPU libraries), they only need to be installed
in *this tool's* worker image, not in the API image.

Reuse existing scientific code by importing from `bb_funcs/` inside your
processor, the same way you would in a plain script.

## 3. Add a Dockerfile for the worker image

Create `backend/tools/mbr_analysis/Dockerfile`, following the BeadBuddy one
as a template:

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY worker_requirements.txt ./
RUN pip install --no-cache-dir -r worker_requirements.txt

COPY database.py models.py storage.py ./
COPY worker_base ./worker_base
COPY tools/mbr_analysis ./tools/mbr_analysis
RUN touch tools/__init__.py

ENV TOOL_ID=mbr_analysis
CMD ["python", "-m", "worker_base.runner"]
```

If this tool needs extra Python packages, add a `worker_requirements.txt`
next to the Dockerfile in the tool's own folder and `COPY`/`pip install` that
instead of the shared one, so its dependency set stays isolated from other
tools.

## 4. Wire the image into Compose (local/dev builds)

Add a build-only entry next to `beadbuddy-worker` in `docker-compose.yml`:

```yaml
mbr-analysis-worker:
  profiles: ["tools"]
  build:
    context: ./backend
    dockerfile: tools/mbr_analysis/Dockerfile
  image: mbr-analysis-worker:latest
```

Build it with:

```bash
docker compose --profile tools build mbr-analysis-worker
```

If your processor needs code that lives outside `backend/` (e.g. the shared
`bb_funcs/` scientific package, as BeadBuddy's does), the build context can't
reach it - Docker refuses to `COPY` from outside the build context. Point the
context at the repo root instead and prefix every `COPY` in the Dockerfile
with `backend/` (see `backend/tools/beadbuddy/Dockerfile` for a worked
example):

```yaml
mbr-analysis-worker:
  profiles: ["tools"]
  build:
    context: .
    dockerfile: backend/tools/mbr_analysis/Dockerfile
  image: mbr-analysis-worker:latest
```

The `worker_image` value in step 1 must match the `image:` tag here exactly -
that is how the scheduler knows which image to launch for this tool's jobs.

In a real multi-machine deployment, push this image to a registry
(`registry.example.com/mbr-analysis-worker:0.1.0`) and use that tag instead so
any machine running a scheduler can pull and run it.

## 5. Done - what you get for free

- The dashboard automatically shows a new card once `enabled=True`.
- The upload/run/slice/download workflow, parameter form, and progress
  polling all come from `frontend/src/pages/ToolWorkspace.tsx`; no new
  frontend file is needed unless the tool's UI genuinely differs from
  "upload a stack, tune numbers, get a result back".
- The scheduler dispatches this tool's jobs the same way as every other
  tool's, using the atomic job-claim logic in
  `backend/scheduler/dispatcher.py`.

## When you do need custom frontend UI

If a tool's inputs or outputs don't fit the generic upload/slice/download
shape (e.g. it needs a second file input, or renders a chart instead of an
image), add a dedicated page under `frontend/src/pages/` and render it from
`App.tsx` when `activeTool.id === 'your_tool_id'`, instead of
`ToolWorkspace`. Keep using `services/api.ts`'s `getTools`/`runTool` so the
job lifecycle stays consistent with every other tool.
