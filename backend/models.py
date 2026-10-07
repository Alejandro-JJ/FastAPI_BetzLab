"""
SQLAlchemy ORM models.

These classes define the persistent data schema used by the app: users,
uploaded files, and their background processing jobs. They are the source of
truth for the database structure and are the most relevant models to inspect when
tracing a bug involving user ownership, file metadata, or job status.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# User accounts and their relationships to files and jobs.
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    jobs = relationship("Job", back_populates="user")
    files = relationship("File", back_populates="user")

# Uploaded files and their owner. `object_key` is the source of truth in object
# storage; `path` is only a local cache path used for fast slice serving.
class File(Base):
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="files")

# Background processing jobs, dispatched by the scheduler to a temporary worker
# container. `tool_id` selects the worker image via the tool registry.
class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_id = Column(Integer, ForeignKey("files.id"))
    tool_id = Column(String, nullable=False)
    params_json = Column(Text, nullable=False, default="{}")
    # queued -> dispatching -> running -> completed | failed
    status = Column(String, default="queued")
    result_object_key = Column(String, nullable=True)
    metadata_object_key = Column(String, nullable=True)
    result_path = Column(String, nullable=True)
    # How the frontend should render result slices: "grayscale" or "labels".
    render_mode = Column(String, nullable=True)
    # JSON dict of small, DB-friendly result facts (e.g. beads_found, duration_seconds).
    result_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    container_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    user = relationship("User", back_populates="jobs")
    file = relationship("File")