"""
Generic worker entrypoint used by every tool's container image.

The scheduler starts one of these containers per job with a handful of
environment variables. This script does the boring, identical part for every
tool (download input, call the tool's `process()`, upload output, update the
job row) so a new tool only has to implement `tools/<tool_id>/processor.py`.

Required environment variables:
  JOB_ID             - the Job.id row to update
  TOOL_ID            - selects tools/<TOOL_ID>/processor.py
  INPUT_OBJECT_KEY   - object store key of the uploaded source file
  PARAMS_JSON        - JSON-encoded dict of user-provided parameters
  RESULT_PREFIX      - object store key prefix to upload outputs under
  DATABASE_URL       - shared with the API so the job status stays consistent
  MINIO_*            - object store connection, same as the API
"""
import importlib
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal  # noqa: E402
from models import Job  # noqa: E402
import storage  # noqa: E402
from worker_base.contracts import ToolContext  # noqa: E402

WORKDIR = Path("/tmp/job")


def _load_processor(tool_id: str):
    module = importlib.import_module(f"tools.{tool_id}.processor")
    return module.process


def _mark_job(job_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            return
        for name, value in fields.items():
            setattr(job, name, value)
        db.commit()
    finally:
        db.close()


def main() -> int:
    job_id = os.environ["JOB_ID"]
    tool_id = os.environ["TOOL_ID"]
    input_object_key = os.environ["INPUT_OBJECT_KEY"]
    params = json.loads(os.environ.get("PARAMS_JSON", "{}"))
    result_prefix = os.environ["RESULT_PREFIX"]

    WORKDIR.mkdir(parents=True, exist_ok=True)
    _mark_job(job_id, status="running", started_at=datetime.now(timezone.utc))

    try:
        input_path = WORKDIR / Path(input_object_key).name
        storage.download_to_path(input_object_key, input_path)

        process = _load_processor(tool_id)
        context = ToolContext(job_id=job_id, params=params, workdir=WORKDIR)
        result = process(input_path, context)

        result_key = f"{result_prefix}{result.result_path.name}"
        storage.upload_path(result.result_path, result_key)

        artifact_object_keys: dict[str, str] = {}
        if result.artifacts:
            for artifact_name, artifact_path in result.artifacts.items():
                artifact_key = f"{result_prefix}{artifact_path.name}"
                storage.upload_path(artifact_path, artifact_key)
                artifact_object_keys[str(artifact_name)] = artifact_key

        if artifact_object_keys:
            result.metadata = dict(result.metadata)
            result.metadata["artifact_object_keys"] = artifact_object_keys

        metadata_path = WORKDIR / f"{result.result_path.stem}_metadata.json"
        metadata_path.write_text(json.dumps(result.metadata, indent=2), encoding="utf-8")
        metadata_key = f"{result_prefix}{metadata_path.name}"
        storage.upload_path(metadata_path, metadata_key)

        _mark_job(
            job_id,
            status="completed",
            result_object_key=result_key,
            metadata_object_key=metadata_key,
            render_mode=result.render_mode,
            result_summary=json.dumps(result.metadata),
            finished_at=datetime.now(timezone.utc),
        )
        print(f"Job {job_id} completed: {result_key}")
        return 0
    except Exception as error:  # noqa: BLE001 - report any failure back to the job row
        traceback.print_exc()
        _mark_job(
            job_id,
            status="failed",
            error_message=str(error),
            finished_at=datetime.now(timezone.utc),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
