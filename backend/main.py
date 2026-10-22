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
import mimetypes
import os
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import colorcet as cc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
from minio.error import S3Error

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


# Glasbey palette optimized for a dark/black background (colorcet.glasbey_dark),
# used to render label images: background (label 0) stays black, every other
# label gets a maximally-distinct color from this palette.
_GLASBEY_DARK = [
    tuple(int(hex_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    for hex_color in cc.glasbey_dark
]


def _labels_to_rgb(label_slice: np.ndarray) -> np.ndarray:
    """Color-code a label image: background (0) black, each label a distinct color."""
    rgb = np.zeros((*label_slice.shape, 3), dtype=np.uint8)
    for label in np.unique(label_slice):
        if label == 0:
            continue
        rgb[label_slice == label] = _GLASBEY_DARK[int(label) % len(_GLASBEY_DARK)]
    return rgb


def _stack_slice_response(file_path: Path, slice_index: int, render_mode: str = "grayscale") -> Response:
    """Read one TIFF slice and return it as a browser-friendly PNG."""
    stack = tifffile.imread(file_path)
    if stack.ndim == 2:
        stack = stack[np.newaxis, ...]
    if stack.ndim != 3 or not 0 <= slice_index < stack.shape[0]:
        raise HTTPException(status_code=404, detail="Slice not found")

    image_slice = stack[slice_index]

    if render_mode == "labels":
        image_buffer = BytesIO()
        Image.fromarray(_labels_to_rgb(image_slice), mode="RGB").save(image_buffer, format="PNG")
        return Response(content=image_buffer.getvalue(), media_type="image/png")

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


def _field_magnitude(field: np.ndarray) -> np.ndarray:
    arr = np.asarray(field)
    if np.iscomplexobj(arr):
        arr = arr.real

    if arr.ndim >= 3 and arr.shape[-1] in (2, 3):
        return np.sqrt(np.sum(np.square(arr.astype(np.float32)), axis=-1, dtype=np.float32))
    if arr.ndim >= 3 and arr.shape[0] in (2, 3):
        moved = np.moveaxis(arr, 0, -1)
        return np.sqrt(np.sum(np.square(moved.astype(np.float32)), axis=-1, dtype=np.float32))
    return np.abs(arr).astype(np.float32)


def _field_quiver_components(field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(field)
    if np.iscomplexobj(arr):
        arr = arr.real

    if arr.ndim >= 3 and arr.shape[-1] >= 3:
        return arr[..., 2].astype(np.float32), arr[..., 1].astype(np.float32)
    if arr.ndim >= 3 and arr.shape[-1] == 2:
        return arr[..., 1].astype(np.float32), arr[..., 0].astype(np.float32)
    if arr.ndim >= 3 and arr.shape[0] >= 3:
        moved = np.moveaxis(arr, 0, -1)
        return moved[..., 2].astype(np.float32), moved[..., 1].astype(np.float32)
    if arr.ndim >= 3 and arr.shape[0] == 2:
        moved = np.moveaxis(arr, 0, -1)
        return moved[..., 1].astype(np.float32), moved[..., 0].astype(np.float32)
    zero = np.zeros(arr.shape[-2:], dtype=np.float32)
    return zero, zero


def _render_matplotlib_plot_png(
    field: np.ndarray,
    stage_name: str,
    preview_mode: str,
    colormap: str,
    quiver_stride: int,
    show_scale_bar: bool,
    micrometers_per_vector_pixel: float,
    resolution_scale: float,
    quiver_length_scale: float,
    quiver_size_scale: float,
) -> bytes:
    magnitude = _field_magnitude(field)
    if magnitude.ndim != 2:
        raise ValueError("Expected 2D magnitude for matplotlib preview")

    height, width = int(magnitude.shape[0]), int(magnitude.shape[1])
    base_scale = max(1.0, float(resolution_scale))
    adaptive_scale = min(3.0, max(1.5, 1500.0 / max(1, max(height, width))))
    scale = min(4.0, max(base_scale, adaptive_scale))
    mode = (preview_mode or "magnitude").strip().lower()
    if stage_name == "traction" and mode == "magnitude":
        mode = "both"

    image_px_h = int(round(height * scale))
    image_px_w = int(round(width * scale))
    colorbar_enabled = mode in {"magnitude", "both"}
    cbar_px = max(28, int(round(image_px_w * 0.06))) if colorbar_enabled else 0
    pad_px = 12 if colorbar_enabled else 0

    total_px_w = image_px_w + cbar_px + pad_px
    total_px_h = image_px_h
    dpi = 200
    figure = plt.figure(figsize=(total_px_w / dpi, total_px_h / dpi), dpi=dpi)

    if colorbar_enabled:
        image_width_frac = image_px_w / total_px_w
        pad_frac = pad_px / total_px_w
        cbar_frac = cbar_px / total_px_w
        axes = figure.add_axes([0.0, 0.0, image_width_frac, 1.0])
        cbar_axes = figure.add_axes([image_width_frac + pad_frac, 0.07, cbar_frac, 0.86])
    else:
        axes = figure.add_axes([0.0, 0.0, 1.0, 1.0])
        cbar_axes = None

    axes.set_axis_off()
    axes.set_aspect("equal", adjustable="box")
    image = axes.imshow(magnitude, cmap=colormap, origin="lower", interpolation="nearest")

    if mode in {"field", "both"}:
        u, v = _field_quiver_components(field)
        stride = max(1, int(quiver_stride))
        yy, xx = np.mgrid[0:height:stride, 0:width:stride]
        uu = u[::stride, ::stride]
        vv = v[::stride, ::stride]
        magnitude_uv = np.sqrt(np.square(uu) + np.square(vv))
        max_magnitude = float(np.max(magnitude_uv)) if magnitude_uv.size > 0 else 0.0

        if mode == "both":
            color = "white"
            alpha = 1.0
            c_values = None
        else:
            color = None
            alpha = 1.0
            c_values = magnitude_uv

        size_scale = max(0.1, float(quiver_size_scale))
        quiver_kwargs = {
            "pivot": "middle",
            "angles": "xy",
            "scale_units": "xy",
            "scale": None,
            "width": max(0.0012, 0.0030 * size_scale),
            "headwidth": max(2.5, 4.2 * size_scale),
            "headlength": max(3.2, 5.8 * size_scale),
            "headaxislength": max(2.8, 5.2 * size_scale),
            "minshaft": 2,
            "minlength": 0.6,
            "alpha": alpha,
        }

        length_scale = max(0.05, float(quiver_length_scale))
        if max_magnitude > 0:
            normalize_to_pixels = max(8.0, 0.12 * min(height, width))
            uu = (uu / max_magnitude) * normalize_to_pixels * length_scale
            vv = (vv / max_magnitude) * normalize_to_pixels * length_scale
        else:
            uu = uu * length_scale
            vv = vv * length_scale

        if c_values is None:
            axes.quiver(xx, yy, uu, vv, color=color, **quiver_kwargs)
        else:
            axes.quiver(xx, yy, uu, vv, c_values, cmap=colormap, **quiver_kwargs)

    if colorbar_enabled and cbar_axes is not None:
        colorbar = figure.colorbar(image, cax=cbar_axes, orientation="vertical")
        colorbar.outline.set_linewidth(0.8)
        colorbar.ax.tick_params(labelsize=7, length=2, width=0.8)

    if show_scale_bar and micrometers_per_vector_pixel > 0:
        target_um = 10.0
        length_px = max(8, min(int(width * 0.35), int(round(target_um / micrometers_per_vector_pixel))))
        label_um = length_px * micrometers_per_vector_pixel
        x0 = int(width * 0.05)
        y0 = int(height * 0.08)
        axes.plot([x0, x0 + length_px], [y0, y0], color="white", linewidth=2.0, solid_capstyle="butt")
        axes.text(x0, y0 + max(3, int(height * 0.018)), f"{label_um:.1f} um", color="white", fontsize=7, ha="left", va="bottom")

    image_buffer = BytesIO()
    figure.savefig(image_buffer, format="png", dpi=dpi, facecolor="white", edgecolor="white")
    plt.close(figure)
    image_buffer.seek(0)
    return image_buffer.getvalue()

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
    try:
        storage.upload_path(local_path, object_key)
    except S3Error as error:
        detail = f"Object storage error ({error.code}): {error.message}"
        if error.code == "XMinioStorageFull":
            detail = "Upload failed: object storage is full. Free space in MinIO (or run a hard reset) and try again."
            raise HTTPException(status_code=507, detail=detail)
        raise HTTPException(status_code=502, detail=detail)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Upload failed while storing file: {error}")

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
    return _stack_slice_response(local_path, slice_index, render_mode=db_job.render_mode or "grayscale")


@app.get("/job/{job_id}/vector/{slice_index}")
async def get_result_vector_slice(
    job_id: str,
    slice_index: int,
    stride: int = Query(default=6, ge=1, le=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db_job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    if db_job.status != "completed":
        raise HTTPException(status_code=409, detail="Result is not ready yet")

    summary = json.loads(db_job.result_summary) if db_job.result_summary else {}
    artifact_keys = summary.get("artifact_object_keys") or {}
    vector_object_key = artifact_keys.get("vector_fields")
    if not vector_object_key:
        raise HTTPException(status_code=404, detail="Vector field artifact not found for this job")

    vector_cache_path = RESULTS_DIR / job_id / Path(vector_object_key).name
    vector_local_path = storage.ensure_local_copy(vector_object_key, vector_cache_path)

    try:
        vectors = np.load(vector_local_path)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Unable to read vector artifact: {error}") from error

    if vectors.ndim == 3:
        vectors = vectors[np.newaxis, ...]

    if vectors.ndim != 4:
        raise HTTPException(status_code=500, detail="Unexpected vector artifact shape")

    if not 0 <= slice_index < vectors.shape[0]:
        raise HTTPException(status_code=404, detail="Slice not found")

    field = np.asarray(vectors[slice_index])
    if field.ndim != 3 or field.shape[-1] < 2:
        raise HTTPException(status_code=500, detail="Vector slice has invalid dimensions")

    sampled = field[::stride, ::stride, :]
    if sampled.size == 0:
        sampled = field
        stride = 1

    if sampled.shape[-1] >= 3:
        u = sampled[..., 2]
        v = sampled[..., 1]
    else:
        u = sampled[..., 1]
        v = sampled[..., 0]

    magnitude = np.sqrt(np.sum(np.square(sampled), axis=-1, dtype=np.float32), dtype=np.float32)

    return {
        "slice_index": slice_index,
        "sampled_height": int(sampled.shape[0]),
        "sampled_width": int(sampled.shape[1]),
        "stride": int(stride),
        "vector_dim": int(sampled.shape[-1]),
        "u": np.asarray(u, dtype=np.float32).tolist(),
        "v": np.asarray(v, dtype=np.float32).tolist(),
        "magnitude": np.asarray(magnitude, dtype=np.float32).tolist(),
        "unit": str(summary.get("vector_field_unit", "a.u.")),
        "scale_hint": float(summary.get("vector_field_scale_hint", 1.0)),
    }


@app.get("/job/{job_id}/artifact/{artifact_name}")
async def get_result_artifact(
    job_id: str,
    artifact_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db_job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    if db_job.status != "completed":
        raise HTTPException(status_code=409, detail="Result is not ready yet")

    summary = json.loads(db_job.result_summary) if db_job.result_summary else {}
    artifact_keys = summary.get("artifact_object_keys") or {}
    artifact_object_key = artifact_keys.get(artifact_name)
    if not artifact_object_key:
        raise HTTPException(status_code=404, detail="Artifact not found")

    cache_path = RESULTS_DIR / job_id / Path(artifact_object_key).name
    local_path = storage.ensure_local_copy(artifact_object_key, cache_path)
    media_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    return Response(content=local_path.read_bytes(), media_type=media_type)


@app.post("/job/{job_id}/plot/{stage}/{slice_index}")
async def rerender_plot_slice(
    job_id: str,
    stage: str,
    slice_index: int,
    preview_mode: str = Body(default="magnitude"),
    plot_colormap: str = Body(default="jet"),
    quiver_stride: int = Body(default=1),
    show_scale_bar: bool = Body(default=True),
    plot_resolution_scale: float = Body(default=2.5),
    plot_quiver_length_scale: float = Body(default=1.0),
    plot_quiver_size_scale: float = Body(default=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stage_name = stage.strip().lower()
    if stage_name not in {"displacement", "traction"}:
        raise HTTPException(status_code=400, detail="Stage must be 'displacement' or 'traction'")

    db_job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    if db_job.status != "completed":
        raise HTTPException(status_code=409, detail="Result is not ready yet")

    summary = json.loads(db_job.result_summary) if db_job.result_summary else {}
    artifact_keys = summary.get("artifact_object_keys") or {}
    vector_object_key = artifact_keys.get("vector_fields")
    if not vector_object_key:
        raise HTTPException(status_code=404, detail="Vector field artifact not found for this job")

    vector_cache_path = RESULTS_DIR / job_id / Path(vector_object_key).name
    vector_local_path = storage.ensure_local_copy(vector_object_key, vector_cache_path)
    try:
        vectors = np.load(vector_local_path)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Unable to read vector artifact: {error}") from error

    if vectors.ndim == 3:
        vectors = vectors[np.newaxis, ...]
    if vectors.ndim != 4:
        raise HTTPException(status_code=500, detail="Unexpected vector artifact shape")
    if not 0 <= slice_index < vectors.shape[0]:
        raise HTTPException(status_code=404, detail="Slice not found")

    field = np.asarray(vectors[slice_index])
    params = summary.get("parameters") or {}
    displacement_method = str(summary.get("displacement_method") or params.get("displacement_method") or "dft").strip().lower()
    step_size = int(params.get("step_size", 10))
    mue2pix = float(params.get("mue2pix", 0.0772))
    vector_pixel_step = step_size if displacement_method in {"dft", "elastix", "elastix3d"} else 1
    micrometers_per_vector_pixel = mue2pix * max(1, vector_pixel_step)

    png_bytes = _render_matplotlib_plot_png(
        field=field,
        stage_name=stage_name,
        preview_mode=preview_mode,
        colormap=str(plot_colormap).strip().lower(),
        quiver_stride=max(1, int(quiver_stride)),
        show_scale_bar=bool(show_scale_bar),
        micrometers_per_vector_pixel=micrometers_per_vector_pixel,
        resolution_scale=float(plot_resolution_scale),
        quiver_length_scale=float(plot_quiver_length_scale),
        quiver_size_scale=float(plot_quiver_size_scale),
    )
    return Response(content=png_bytes, media_type="image/png")


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

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    artifact_object_keys = metadata.get("artifact_object_keys") or {}

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(result_path, result_path.name)
        zip_file.write(metadata_path, metadata_path.name)
        for artifact_object_key in dict.fromkeys(artifact_object_keys.values()):
            artifact_path = storage.ensure_local_copy(
                artifact_object_key,
                cache_dir / Path(artifact_object_key).name,
            )
            zip_file.write(artifact_path, artifact_path.name)
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

    # TFM needs two inputs (before + after). The main `file_id` is "before";
    # `after_file_id` travels in params and is resolved to an object key here,
    # so workers remain stateless and do not need DB reads for extra inputs.
    if tool_id == "traction_force":
        after_file_id = params.get("after_file_id")
        if after_file_id is None:
            raise HTTPException(status_code=400, detail="Traction force requires 'after_file_id' in params")
        try:
            after_file_id = int(after_file_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="'after_file_id' must be an integer")

        after_file = db.query(File).filter(File.id == after_file_id).first()
        if not after_file or after_file.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="After file not found")

        params = dict(params)
        params["after_file_id"] = after_file_id
        params["after_object_key"] = after_file.object_key
        params["after_filename"] = after_file.filename

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
        "summary": json.loads(db_job.result_summary) if db_job.result_summary else None,
    }
