"""
Job scheduler: launches one temporary worker container per queued job.

This process polls the `jobs` table for work instead of listening on a queue,
which keeps the moving parts to a minimum (no separate broker). It claims a
job atomically with a conditional UPDATE so multiple scheduler instances
(e.g. one per remote machine) can run against the same database without
double-dispatching the same job.

For a single machine this uses the local Docker daemon (via the mounted
docker.sock) to start containers on the shared compose network. To run
workers on a *different* physical machine, run another copy of this process
there, pointed at the same DATABASE_URL, with Docker access on that machine -
each scheduler instance just needs to be able to reach the object store and
the database, and to run its own local `docker run`. Swapping the Docker
client for a Kubernetes Job creation call is the natural next step and does
not require changing anything else in this file's calling code.
"""
import os
import time
import traceback
from datetime import datetime, timezone

import docker
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from database import SessionLocal
from models import Job
from tool_registry import get_tool

load_dotenv()

POLL_INTERVAL_SECONDS = float(os.getenv("SCHEDULER_POLL_INTERVAL", "2"))
MAX_CONCURRENT_JOBS = int(os.getenv("SCHEDULER_MAX_CONCURRENT_JOBS", "4"))
DOCKER_NETWORK = os.getenv("SCHEDULER_DOCKER_NETWORK", "beadbuddy_default")
RESULTS_PREFIX_TEMPLATE = "results/{job_id}/"

_docker_client = docker.from_env()


def _claim_next_job() -> Job | None:
    """Atomically move one queued job to 'dispatching' so it is only picked up once."""
    db = SessionLocal()
    try:
        running = db.query(Job).filter(Job.status.in_(["dispatching", "running"])).count()
        if running >= MAX_CONCURRENT_JOBS:
            return None

        candidate = (
            db.query(Job)
            .filter(Job.status == "queued")
            .order_by(Job.created_at.asc())
            .first()
        )
        if candidate is None:
            return None

        # Conditional update guards against a second scheduler claiming the same row.
        result = db.execute(
            text("UPDATE jobs SET status = 'dispatching' WHERE id = :id AND status = 'queued'"),
            {"id": candidate.id},
        )
        db.commit()
        if result.rowcount == 0:
            return None

        # Re-fetch with `file` eagerly loaded: `_dispatch` reads job.file.object_key
        # after this session is closed, and a lazy load would fail on a detached instance.
        job = (
            db.query(Job)
            .options(joinedload(Job.file))
            .filter(Job.id == candidate.id)
            .one()
        )
        db.expunge(job)
        return job
    finally:
        db.close()


def _mark_failed(job_id: str, message: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = message
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _dispatch(job: Job) -> None:
    tool = get_tool(job.tool_id)
    if tool is None or not tool.enabled or not tool.worker_image:
        _mark_failed(job.id, f"Tool '{job.tool_id}' is not available for processing.")
        return

    environment = {
        "JOB_ID": job.id,
        "TOOL_ID": job.tool_id,
        "INPUT_OBJECT_KEY": job.file.object_key,
        "PARAMS_JSON": job.params_json,
        "RESULT_PREFIX": RESULTS_PREFIX_TEMPLATE.format(job_id=job.id),
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", ""),
        "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY", ""),
        "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY", ""),
        "MINIO_BUCKET": os.getenv("MINIO_BUCKET", ""),
        "MINIO_SECURE": os.getenv("MINIO_SECURE", "false"),
    }

    print(f"Dispatching job {job.id} ({job.tool_id}) -> {tool.worker_image}")
    try:
        container = _docker_client.containers.run(
            tool.worker_image,
            environment=environment,
            network=DOCKER_NETWORK,
            detach=True,
            remove=True,
            name=f"job-{job.id}",
        )
    except docker.errors.APIError as error:
        _mark_failed(job.id, f"Failed to start worker container: {error}")
        return

    db = SessionLocal()
    try:
        db_job = db.query(Job).filter(Job.id == job.id).first()
        if db_job:
            db_job.container_id = container.id
            db.commit()
    finally:
        db.close()


def run_forever() -> None:
    print(f"Scheduler started. Polling every {POLL_INTERVAL_SECONDS}s, max {MAX_CONCURRENT_JOBS} concurrent jobs.")
    while True:
        try:
            job = _claim_next_job()
            if job is not None:
                _dispatch(job)
            else:
                time.sleep(POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001 - one bad job must not kill the scheduler loop
            traceback.print_exc()
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
