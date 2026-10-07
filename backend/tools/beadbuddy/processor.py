"""BeadBuddy's analysis step, in the shape `worker_base.runner` expects.

Wraps `bb_funcs.Segmentation.MasterSegmenter`, the real segmentation pipeline
(adapted from the BeadBuddy Streamlit app), behind the platform's process()
contract.
"""
import time
from pathlib import Path

import tifffile

from bb_funcs.Segmentation import MasterSegmenter
from worker_base.contracts import ToolContext, ToolResult


def process(input_path: Path, context: ToolContext) -> ToolResult:
    stack = tifffile.imread(input_path)
    params = context.params

    started = time.perf_counter()
    im_beads, n_beads = MasterSegmenter(
        stack,
        timepoint=params.get("timepoint", 0),
        backg_r=params.get("backg_r", 20),
        threshold=params.get("threshold", 200),
        spot_sigma=params.get("spot_sigma", 1),
        outline_sigma=params.get("outline_sigma", 1),
        perc_int=params.get("perc_int", 100),
    )
    duration_seconds = time.perf_counter() - started

    result_path = context.workdir / f"result_{input_path.stem}.tif"
    tifffile.imwrite(result_path, im_beads)

    metadata = {
        "job_id": context.job_id,
        "source_file": input_path.name,
        "operation": "MasterSegmenter",
        "parameters": params,
        "beads_found": int(n_beads),
        "duration_seconds": round(duration_seconds, 2),
    }

    return ToolResult(result_path=result_path, metadata=metadata, render_mode="labels")


