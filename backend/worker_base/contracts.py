"""
Shared contract between the scheduler, a tool's worker image, and its
processor function. New tools implement `process()` with this exact
signature; everything else (download, upload, DB updates) is handled by
`worker_base.runner`, so a tool's code never touches storage or the database.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolContext:
    """Everything a processor function needs about the current job."""
    job_id: str
    params: dict
    workdir: Path


@dataclass
class ToolResult:
    """What a processor function must return so the runner can publish it."""
    result_path: Path
    metadata: dict
    preview_path: Path | None = None
