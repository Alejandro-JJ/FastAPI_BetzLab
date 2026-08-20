"""
FastAPI application entrypoint.

This module wires together the HTTP API, database access, authentication,
file upload handling, and Celery job orchestration. It is the main coordinator
for the backend and is the first place to inspect when debugging request flow,
user authentication, or background processing lifecycle.
"""
import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from auth import (
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)
from database import Base, engine, get_db
from models import File, Job, User
from schemas import UserCreate, UserRead
from tasks import celery_app

load_dotenv()

# Expose the API to the browser frontend and allow token-based requests.
app = FastAPI(title="Test API Alejandro")

# CORS must whitelist the frontend origins that are allowed to call the API.
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure the database schema exists before serving requests.
Base.metadata.create_all(bind=engine)

# Persistent directories for uploaded source files and generated result images.
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "results"))

UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# User register point
# Requires no authentication (public post)
@app.post("/auth/register", response_model=UserRead)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    user_in_db = db.query(User).filter(User.email == user.email).first()
    if user_in_db:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    hashed_password = get_password_hash(user.password) # password gets hashed here during registration
    db_user = User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# User login point
# Requires authentication
@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Find user
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password): 
        # comparison with hashed password stored in database
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


# Post of current user
@app.get("/auth/me", response_model=UserRead)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

"""
UPLOAD TAB
"""
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Save uploaded file to the server's storage before enqueueing a job.
    file_path = UPLOAD_DIR / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Store file in database
    db_file = File(
        filename=file.filename,
        path=str(file_path),
        user_id=current_user.id
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # Upload only stores the source file; processing starts when the user clicks Process.
    return {
        "filename": file.filename,
        "size": file.size,
        "file_id": db_file.id,
        "status": "uploaded",
        "message": f"File {db_file.id} uploaded and ready to process"
    }


@app.get("/results/{filename}")
async def get_result_file(filename: str):
    file_path = RESULTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    return FileResponse(file_path)

"""
RUN TAB
"""
@app.post("/run")
async def run_segmentation(
    file_id: int = Body(...),
    params: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Check if file exists and belongs to user
    db_file = db.query(File).filter(File.id == file_id).first()
    if not db_file or db_file.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = db_file.path

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Store job in database
    db_job = Job(
        id=job_id,
        user_id=current_user.id,
        file_id=file_id,
        status="pending"
    )
    db.add(db_job)
    db.commit()

    # Enqueue the task only after the user submits the analysis parameters.
    task = celery_app.send_task(
        "tasks.run_segmentation_task",
        args=[file_path, params, job_id],
        task_id=job_id
    )

    return {
        "job_id": job_id,
        "status": "processing",
        "message": f"Segmentation started for file {file_id}"
    }


@app.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Check that the job exists and belongs to the current user.
    db_job = db.query(Job).filter(Job.id == job_id).first()
    if not db_job or db_job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get task result from celery
    task = celery_app.AsyncResult(job_id)

    if task.ready():
        # Store the completed result path in the database.
        db_job.status = "completed"
        db_job.result_path = task.result.get("result_path")
        db.commit()
        return{
            "job_id": job_id,
            "status": "DONE",
            "results": task.result
        }
    else:
        return{
            "job_id": job_id,
            "status": "processing",
        }