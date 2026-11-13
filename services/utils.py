"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  file has various utility functions and classes that support the application, including database initialization, audit logging, and other helper functions. It provides a structured way to manage database connections, log model calls, tool calls, and errors, and ensure proper resource management.
* ? Usage:  The AuditService class can be used to log model calls, tool calls, and errors.
*/
"""

import json
import logging
import os

# import psycopg
# from langchain_mcp_adapters.client import MultiServerMCPClient
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------
# Database configuration
# ---------------------------------------------------------

# Keep local audit storage configurable, and default production audit storage to
# the portal database. Ignore a legacy production SQLite override so upgrades
# also move new audit writes to PostgreSQL.
PORTAL_DATABASE_URL = os.getenv("DATABASE_URL")
AUDIT_DATABASE_URL = os.getenv("AUDIT_DATABASE_URL")
IS_PRODUCTION = os.getenv("DJANGO_DEBUG", "true").lower() not in {"1", "true", "yes"}
if IS_PRODUCTION and PORTAL_DATABASE_URL and PORTAL_DATABASE_URL.startswith(("postgres://", "postgresql://")):
    DATABASE_URL = (
        AUDIT_DATABASE_URL
        if AUDIT_DATABASE_URL and AUDIT_DATABASE_URL.startswith(("postgres://", "postgresql://"))
        else PORTAL_DATABASE_URL
    )
else:
    DATABASE_URL = AUDIT_DATABASE_URL or PORTAL_DATABASE_URL or "sqlite:///./patent_agent.db"
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    # SQLAlchemy otherwise defaults to psycopg2; the project installs psycopg 3.
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()
import uuid


# ---------------------------------------------------------
# Audit table
# ---------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(100), nullable=False, index=True)
    calling_function = Column(String(200), nullable=False)
    query = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    datetime = Column(DateTime(timezone=True), nullable=False)


def init_db():
    engine_options = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }
    if DATABASE_URL.startswith("sqlite:"):
        engine_options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, **engine_options)
    # Create tables here
    Base.metadata.create_all(
        engine
    )  # The key is that Base.metadata automatically contains every ORM class that inherits from that same Base.
    return engine


# ---------------------------------------------------------
# Audit logging
# ---------------------------------------------------------


class AuditService:
    def __init__(self, db_engine):
        self.SessionLocal = sessionmaker(bind=db_engine)

    def log_model_call(self, session_id, function_name, prompt, answer):
        try:
            if hasattr(answer, "model_dump_json"):
                answer = answer.model_dump_json()
            elif not isinstance(answer, str):
                answer = json.dumps(answer, default=str)
            db = self.SessionLocal()  # does not create a new database connection each time. The underlying SQLAlchemy engine/pool handles that.
            record = AuditLog(
                id=str(uuid.uuid4()),
                session_id=session_id,
                calling_function=function_name,
                query=prompt,
                answer=answer,
                datetime=datetime.now(timezone.utc),
            )

            db.add(record)
            db.commit()

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        print(f"MODEL: {function_name}")
        # Later: INSERT into MSSQL

    def log_tool_call(self, tool_name, tool_args):
        print(f"TOOL: {tool_name}")

    def log_error(self, source, error):
        print(f"ERROR: {source} : {error}")
