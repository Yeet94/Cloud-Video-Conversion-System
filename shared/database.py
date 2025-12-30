# Database operations for job management
import sqlite3
from datetime import datetime
from typing import Optional, List
from contextlib import contextmanager
import threading
import os

from .models import JobStatus, JobResponse


# Thread-local storage for database connections
_local = threading.local()


def get_db_path() -> str:
    """Get database path from environment or default."""
    return os.environ.get("DATABASE_PATH", "/data/jobs.db")


def init_database(db_path: Optional[str] = None) -> None:
    """Initialize the database with required tables."""
    path = db_path or get_db_path()
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            input_path TEXT NOT NULL,
            output_path TEXT,
            output_format TEXT DEFAULT 'mp4',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_message TEXT,
            conversion_time_ms INTEGER
        )
    """)
    
    # Create index for status queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
    """)
    
    conn.commit()
    conn.close()


@contextmanager
def get_connection(db_path: Optional[str] = None):
    """Get a database connection (thread-safe)."""
    path = db_path or get_db_path()
    
    if not hasattr(_local, 'connection') or _local.connection is None:
        _local.connection = sqlite3.connect(path, check_same_thread=False)
        _local.connection.row_factory = sqlite3.Row
    
    try:
        yield _local.connection
    except Exception:
        _local.connection.rollback()
        raise


def create_job(
    job_id: str,
    input_path: str,
    output_format: str = "mp4",
    db_path: Optional[str] = None
) -> JobResponse:
    """Create a new job in the database."""
    now = datetime.utcnow().isoformat()
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO jobs (id, status, input_path, output_format, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, JobStatus.PENDING.value, input_path, output_format, now, now)
        )
        conn.commit()
    
    return get_job(job_id, db_path)


def get_job(job_id: str, db_path: Optional[str] = None) -> Optional[JobResponse]:
    """Get a job by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        return _row_to_job_response(row)


def get_all_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 100,
    db_path: Optional[str] = None
) -> List[JobResponse]:
    """Get all jobs, optionally filtered by status."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        if status:
            cursor.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        
        rows = cursor.fetchall()
        return [_row_to_job_response(row) for row in rows]


def update_job_status(
    job_id: str,
    status: JobStatus,
    output_path: Optional[str] = None,
    error_message: Optional[str] = None,
    conversion_time_ms: Optional[int] = None,
    db_path: Optional[str] = None
) -> Optional[JobResponse]:
    """Update job status and related fields."""
    now = datetime.utcnow().isoformat()
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Build dynamic update query
        updates = ["status = ?", "updated_at = ?"]
        params = [status.value, now]
        
        if output_path is not None:
            updates.append("output_path = ?")
            params.append(output_path)
        
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        
        if conversion_time_ms is not None:
            updates.append("conversion_time_ms = ?")
            params.append(conversion_time_ms)
        
        params.append(job_id)
        
        cursor.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()
    
    return get_job(job_id, db_path)


def delete_job(job_id: str, db_path: Optional[str] = None) -> bool:
    """Delete a job by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_job_counts(db_path: Optional[str] = None) -> dict:
    """Get count of jobs by status."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM jobs
            GROUP BY status
        """)
        rows = cursor.fetchall()
        return {row['status']: row['count'] for row in rows}


def _row_to_job_response(row: sqlite3.Row) -> JobResponse:
    """Convert a database row to JobResponse model."""
    return JobResponse(
        id=row['id'],
        status=JobStatus(row['status']),
        input_path=row['input_path'],
        output_path=row['output_path'],
        output_format=row['output_format'] or 'mp4',
        created_at=datetime.fromisoformat(row['created_at']),
        updated_at=datetime.fromisoformat(row['updated_at']),
        error_message=row['error_message'],
        conversion_time_ms=row['conversion_time_ms']
    )
