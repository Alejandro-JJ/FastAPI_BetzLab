"""
FastAPI application entrypoint.

This module wires together the HTTP API, database access, authentication,
file upload handling, and job dispatch. It is the control plane: it never runs
heavy analysis itself. A job it creates is picked up by the scheduler
(scheduler/dispatcher.py), which starts a temporary worker container for that
one job. Large files live in object storage (storage.py), not on this
machine's disk, so the worker can run on any machine that can reach the store.
"""
import json
import os
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import numpy as np
import tifffile
from PIL import Image

import storage
from auth import (
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)
from database import Base, engine, get_db
from models import File, Job, User
from schemas import UserCreate, UserRead
from tool_registry import get_tool, list_tools, to_public_dict

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

# Local cache directories. Object storage is the source of truth; these only
# speed up repeated reads (e.g. scrubbing through TIFF slices) on this machine.
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "results"))

UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)


def _accepted_extensions() -> set[str]:
    extensions = {
        extension
        for tool in list_tools()
        if tool.enabled
        for extension in tool.accepted_extensions
    }
    return extensions or {".tif", ".tiff"}


def _stack_slice_response(file_path: Path, slice_index: int) -> Response:
    """Read one TIFF slice and return it as a browser-friendly PNG."""
    stack = tifffile.imread(file_path)
    if stack.ndim == 2:
        stack = stack[np.newaxis, ...]
    if stack.ndim != 3 or not 0 <= slice_index < stack.shape[0]:
        raise HTTPException(status_code=404, detail="Slice not found")

    image_slice = stack[slice_index]
    if image_slice.dtype != np.uint8:
        image_slice = image_slice.astype(np.float32)
        minimum = image_slice.min()
        maximum = image_slice.max()
        if maximum > minimum:
            image_slice = ((image_slice - minimum) / (maximum - minimum) * 255).astype(np.uint8)
        else:
            image_slice = np.zeros_like(image_slice, dtype=np.uint8)

    image_buffer = BytesIO()
    Image.fromarray(image_slice).save(image_buffer, format="PNG")
    return Response(content=image_buffer.getvalue(), media_type="image/png")

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
TOOL REGISTRY
"""
@app.get("/tools")
async def get_tools(current_user: User = Depends(get_current_active_user)):
    """List every tool the dashboard can show, driven entirely by tool_registry.py."""
    return [to_public_dict(tool) for tool in list_tools()]


"""
UPLOAD TAB
"""
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if Path(file.filename or "").suffix.lower() not in _accepted_extensions():
        raise HTTPException(status_code=400, detail="This file type is not supported by any tool")

    # Store the file first to get a database id, which becomes part of the object key.
    db_file = File(filename=file.filename, object_key="", path="", user_id=current_user.id)
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # Cache locally for fast slice reads, and upload the same bytes to object storage.
    local_path = UPLOAD_DIR / str(db_file.id) / file.filename
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    object_key = f"uploads/{db_file.id}/{file.filename}"
    storage.upload_path(local_path, object_key)

    db_file.object_key = object_key
    db_file.path = str(local_path)
    db.commit()

    uploaded_stack = tifffile.imread(local_path)
    slice_count = uploaded_stack.shape[0] if uploaded_stack.ndim == 3 else 1

    # Upload only stores the source file; processing starts when the user clicks Process.
    return {
        "filename": file.filename,
        "file_id": db_file.id,
        "slice_count": slice_count,
        "status": "uploaded",
        "message": f"File {db_file.id} uploaded and ready to process"
    }


@app.get("/files/{file_id}/slice/{slice_index}")
async def get_source_slice(
    file_id: int,
    slice_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db_file = db.query(File).filter(File.id == file_id, File.user_id == current_user.id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
    local_path = storage.ensure_local_copy(db_file.object_key, Path(db_file.path))
    return _stack_slice_response(local_path, slice_index)


@app.get("/job/{job_id}/slice/{slice_index}")
async def get_result_slice(
    job_id: str,
    slice_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db_job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not db_job or not db_job.result_object_key:
        raise HTTPException(status_code=404, detail="Result not found")
    cache_path = RESULTS_DIR / job_id / Path(db_job.result_object_key).name
    local_path = storage.ensure_local_copy(db_job.result_object_key, cache_path)
    return _stack_slice_response(local_path, slice_index)


@app.get("/job/{job_id}/download")
async def download_job_result(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Only the owner of a completed job may download its output package.
    db_job = db.query(Job).filter(Job.id == job_id).first()
    if not db_job or db_job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    if db_job.status != "completed" or not db_job.result_object_key:
        raise HTTPException(status_code=409, detail="The result is not ready yet")

    cache_dir = RESULTS_DIR / job_id
    result_path = storage.ensure_local_copy(db_job.result_object_key, cache_dir / Path(db_job.result_object_key).name)
    metadata_path = storage.ensure_local_copy(db_job.metadata_object_key, cache_dir / Path(db_job.metadata_object_key).name)

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(result_path, result_path.name)
        zip_file.write(metadata_path, metadata_path.name)
    archive.seek(0)

    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{job_id}.zip"'},
    )

"""
RUN TAB
"""
@app.post("/tools/{tool_id}/run")
async def run_tool(
    tool_id: str,
    file_id: int = Body(...),
    params: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    tool = get_tool(tool_id)
    if tool is None or not tool.enabled:
        raise HTTPException(status_code=404, detail="Tool not found or not available")

    db_file = db.query(File).filter(File.id == file_id).first()
    if not db_file or db_file.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="File not found")

    # The scheduler (a separate process) picks this row up; the API never
    # starts a worker itself. See scheduler/dispatcher.py.
    job_id = str(uuid.uuid4())
    db_job = Job(
        id=job_id,
        user_id=current_user.id,
        file_id=file_id,
        tool_id=tool_id,
        params_json=json.dumps(params),
        status="queued",
    )
    db.add(db_job)
    db.commit()

    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"{tool.name} queued for file {file_id}",
    }


@app.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    db_job = db.query(Job).filter(Job.id == job_id).first()
    if not db_job or db_job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": db_job.status,
        "error": db_job.error_message,
    }
