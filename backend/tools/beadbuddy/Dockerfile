# Worker image for the BeadBuddy tool.
#
# Build context is the repository root, not backend/, because this tool
# depends on the shared `bb_funcs` scientific package that lives next to
# `backend/` (see docker-compose.yml's `beadbuddy-worker` service for the
# matching context/dockerfile pair).
#
# The scheduler starts one short-lived container from this image per
# segmentation job (see backend/scheduler/dispatcher.py). It only bundles the
# shared worker runtime plus this tool's own code, so its dependency set can
# diverge freely from other tools' images.
FROM python:3.11-slim

WORKDIR /app

# pyclesperanto_prototype (via pyopencl) needs an OpenCL runtime to run
# against; pocl provides a CPU-based one so segmentation works without a GPU.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ocl-icd-opencl-dev opencl-headers \
        ocl-icd-libopencl1 pocl-opencl-icd \
    && rm -rf /var/lib/apt/lists/*

COPY backend/worker_requirements.txt ./
COPY backend/tools/beadbuddy/worker_requirements.txt ./tool_requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r worker_requirements.txt -r tool_requirements.txt

COPY backend/database.py backend/models.py backend/storage.py ./
COPY backend/worker_base ./worker_base
COPY backend/tools/beadbuddy ./tools/beadbuddy
COPY bb_funcs ./bb_funcs
RUN touch tools/__init__.py

ENV TOOL_ID=beadbuddy
CMD ["python", "-m", "worker_base.runner"]

