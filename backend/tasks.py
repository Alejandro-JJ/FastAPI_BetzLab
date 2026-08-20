"""
Celery background processing tasks.

This module defines the asynchronous jobs that run outside the HTTP request cycle.
The dummy task currently converts an image to grayscale, but it is the place where
all heavier operations should be implemented later: image analysis, filtering,
and other math-heavy processing.
"""

import os
import time
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv
from PIL import Image

from database import SessionLocal
from models import Job

load_dotenv()

# Root directory for generated result files.
BASE_DIR = Path(__file__).resolve().parent
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery connects to Redis for broker and result storage.
celery_app = Celery(
    "tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

@celery_app.task
def run_segmentation_task(file_path: str, params: dict, job_id: str):

    print(f"Starting segmentation on {file_path}")

    # This artificial delay simulates a long-running image task while debugging flow.
    time.sleep(5)
    
    """
    THE ACTUAL JOB
    """
    # Load the image
    img = Image.open(file_path)
    
    # Convert to grayscale (black and white)
    img_gray = img.convert('L')

    """
    UNTIL HERE
    """
    
    # Save the processed file in the results folder so it can be downloaded later.
    result_path = BASE_DIR / "results" / f"segmented_{Path(file_path).stem}.jpeg"
    result_path.parent.mkdir(exist_ok=True)
    
    # Save as a valid JPEG image
    img_gray.save(result_path, "JPEG")
    
    print(f"Segmentation complete! Result saved to {result_path}")
    
    # Update database with job status
    db = SessionLocal()
    try:
        db_job = db.query(Job).filter(Job.id == job_id).first()
        if db_job:
            db_job.status = "completed"
            db_job.result_path = str(result_path)
            db.commit()
            print(f"Database updated: Job {job_id} marked as completed")
    except Exception as e:
        print(f"Error updating database: {e}")
        db.rollback()
    finally:
        db.close()
    
    return {"status": "complete", "result_path": str(result_path)}