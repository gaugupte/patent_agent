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

DATABASE_URL = "sqlite:///./patent_agent.db"

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
    engine = create_engine(
        "sqlite:///./patent_agent.db",
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        connect_args={"check_same_thread": False},
    )
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
