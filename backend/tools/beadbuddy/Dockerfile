# Worker image for the BeadBuddy tool.
#
# The scheduler starts one short-lived container from this image per
# segmentation job (see backend/scheduler/dispatcher.py). It only bundles the
# shared worker runtime plus this tool's own code, so its dependency set can
# diverge freely from other tools' images.
FROM python:3.11-slim

WORKDIR /app

COPY worker_requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r worker_requirements.txt

COPY database.py models.py storage.py ./
COPY worker_base ./worker_base
COPY tools/beadbuddy ./tools/beadbuddy
RUN touch tools/__init__.py

ENV TOOL_ID=beadbuddy
CMD ["python", "-m", "worker_base.runner"]
