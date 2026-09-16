"""BeadBuddy's analysis step, in the shape `worker_base.runner` expects.

This is the one function a developer needs to replace to plug in the real
segmentation pipeline (e.g. calling into ``bb_funcs``). It currently performs
a placeholder stack copy so the end-to-end pipeline (upload -> dispatch ->
process -> download) can be exercised before the real algorithm is ready.
"""
from pathlib import Path

import tifffile

from worker_base.contracts import ToolContext, ToolResult


def process(input_path: Path, context: ToolContext) -> ToolResult:
    stack = tifffile.imread(input_path)

    result_path = context.workdir / f"result_{input_path.stem}.tif"
    tifffile.imwrite(result_path, stack)

    metadata = {
        "job_id": context.job_id,
        "source_file": input_path.name,
        "operation": "dummy stack copy",
        "parameters": context.params,
    }

    return ToolResult(result_path=result_path, metadata=metadata)
