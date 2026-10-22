# Worker image for the Traction Force Microscopy tool.

# Build context is the repository root, not backend/, because this tool
# depends on the shared worker runtime that lives at the backend/ level.

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed by TFM tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY backend/worker_requirements.txt ./
COPY backend/tools/traction_force/worker_requirements.txt ./tool_requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r worker_requirements.txt -r tool_requirements.txt

# Copy core platform components
COPY backend/database.py backend/models.py backend/storage.py ./
COPY backend/worker_base ./worker_base
COPY backend/tools/traction_force ./tools/traction_force
COPY TFM_Utilities_OG/SRC ./
COPY bb_funcs ./bb_funcs

# Create empty __init__.py if needed
RUN touch tools/__init__.py

# Set the tool identifier for the runner
ENV TOOL_ID=traction_force
CMD ["python", "-m", "worker_base.runner"]