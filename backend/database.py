"""
Database connection and session factory.

This module centralizes the SQLAlchemy engine configuration. It decides which
connection string is used, creates database sessions for request-scoped work, and
keeps the ORM layer independent from the rest of the application.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# SQLite remains the local default, but container or remote deployments can provide
# a PostgreSQL URL through environment variables.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./database.db",
)

engine_kwargs = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

# Build the SQLAlchemy engine once and reuse it across the app.
engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    # Each request gets its own session so DB operations stay isolated and safe.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
