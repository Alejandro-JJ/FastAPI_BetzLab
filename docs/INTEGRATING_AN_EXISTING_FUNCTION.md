# Integrating a plain `analysis(image, params) -> image` function

This is a copy/paste-oriented walkthrough for the most common case: you
already have a working Python function that takes an image array and a
parameter dict and returns a processed image array, e.g.

```python
def mainAnalysis(imageIn: np.ndarray, params: dict) -> np.ndarray:
    ...
```

and you want it running as a tool in the platform, with its own dashboard
card, upload/run/download workflow, and its own temporary worker container.

For the general concepts (registry, scheduler, worker images) see
[ADDING_A_NEW_TOOL.md](ADDING_A_NEW_TOOL.md). This file only shows the exact
files to create for this specific, very common shape of function.

Everywhere below, replace `my_tool` with your tool's id (lowercase,
underscores, no spaces - it becomes a folder name and part of a Docker image
tag).

## Step 0: pick a tool id and folder

```
backend/tools/my_tool/
```

## Step 1: put your existing code where the worker can import it

Copy your existing module(s) into `backend/tools/my_tool/`. If your function
lives in `mainAnalysis.py` with helpers in other files, copy the whole set:

```
backend/tools/my_tool/
    mainAnalysis.py      # your existing code, unchanged
    helpers.py           # any modules it imports, unchanged
```

Nothing in your existing code needs to change. It should stay pure: given
an image and a dict, return an image. Don't add file I/O, database calls, or
HTTP inside it - that stays out of `mainAnalysis.py` and lives in the adapter
below instead.

## Step 2: write the adapter (`processor.py`)

This is the only new code you write. It converts between "a file on disk"
(what the platform gives you) and "an array in memory" (what your function
expects). Create `backend/tools/my_tool/processor.py`:

```python
"""Adapter between the platform and mainAnalysis()."""
from pathlib import Path

import tifffile

from worker_base.contracts import ToolContext, ToolResult
from tools.my_tool.mainAnalysis import mainAnalysis


def process(input_path: Path, context: ToolContext) -> ToolResult:
    # 1. Load the uploaded file into whatever your function expects.
    image_in = tifffile.imread(input_path)

    # 2. Call your existing function completely unchanged.
    image_out = mainAnalysis(image_in, context.params)

    # 3. Save the returned array to a new file in the job's scratch folder.
    result_path = context.workdir / f"result_{input_path.stem}.tif"
    tifffile.imwrite(result_path, image_out)

    # 4. Anything you want recorded alongside the result (shown to the user
    #    in the downloaded metadata file). Include the parameters used, at
    #    minimum, for reproducibility.
    metadata = {
        "job_id": context.job_id,
        "source_file": input_path.name,
        "tool": "my_tool",
        "parameters": context.params,
    }

    return ToolResult(result_path=result_path, metadata=metadata)
```

Notes:
- `input_path` is a local file path to the uploaded image; the platform has
  already downloaded it from object storage before calling `process()`.
- `context.params` is exactly the dict of numbers the user set in the
  browser form (see step 4) - pass it straight through to `mainAnalysis`.
- `context.workdir` is a scratch directory unique to this job; write your
  output file there, don't use a hardcoded path.
- If your function raises an exception, the runner catches it automatically
  and marks the job `failed` with the error message - you don't need
  try/except here.
- If `imageIn`/`imageOut` are 2D image slices rather than TIFF stacks, swap
  `tifffile` for `PIL.Image.open(...)` / `Image.fromarray(...).save(...)` -
  the rest of this file stays the same.

## Step 3: write the Dockerfile

Create `backend/tools/my_tool/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY worker_requirements.txt ./
RUN pip install --no-cache-dir -r worker_requirements.txt

# Add any extra packages mainAnalysis.py needs (scipy, scikit-image, ...):
# RUN pip install --no-cache-dir scikit-image==0.24.0

COPY database.py models.py storage.py ./
COPY worker_base ./worker_base
COPY tools/my_tool ./tools/my_tool
RUN touch tools/__init__.py

ENV TOOL_ID=my_tool
CMD ["python", "-m", "worker_base.runner"]
```

If `mainAnalysis.py` needs packages beyond `backend/worker_requirements.txt`
(numpy/pillow/tifffile are already there), add a `RUN pip install ...` line
for them, or a separate `worker_requirements.txt` in your tool's folder.

## Step 4: register the tool

Add an entry to `backend/tool_registry.py`. The `parameters` tuple defines
both the keys of the `params` dict your function receives and the number
inputs shown in the browser - list every keyword your function reads from
`params`:

```python
Tool(
    id="my_tool",
    name="My Tool",
    description="One-line description shown on the dashboard card.",
    order=5,
    enabled=True,
    worker_image="my-tool-worker:latest",
    parameters=(
        ToolParameter("threshold", "Threshold", 0.5, 0, 1, 0.01),
        ToolParameter("iterations", "Iterations", 10, 1, 100, 1),
    ),
)
```

## Step 5: build the worker image and wire it into Compose

Add a build-only entry to `docker-compose.yml` (next to `beadbuddy-worker`):

```yaml
my-tool-worker:
  profiles: ["tools"]
  build:
    context: ./backend
    dockerfile: tools/my_tool/Dockerfile
  image: my-tool-worker:latest
```

The `image:` tag here must exactly match `worker_image` in step 4. Build it:

```bash
docker compose --profile tools build my-tool-worker
```

## Step 6: try it

```bash
docker compose up --build
```

Log in to the frontend, and "My Tool" now appears on the dashboard with an
upload/parameter/download workflow identical to BeadBuddy's, but running your
`mainAnalysis` function in its own container. No frontend code was needed.

## Checklist

- [ ] `backend/tools/my_tool/mainAnalysis.py` - your unchanged function
- [ ] `backend/tools/my_tool/processor.py` - the `process()` adapter
- [ ] `backend/tools/my_tool/Dockerfile`
- [ ] `Tool(...)` entry in `backend/tool_registry.py`
- [ ] worker service entry in `docker-compose.yml`
- [ ] `docker compose --profile tools build my-tool-worker` succeeds
- [ ] a full upload -> process -> download run works from the browser
