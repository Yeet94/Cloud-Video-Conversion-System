# Shared Pydantic models for request/response validation
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum
import uuid


class JobStatus(str, Enum):
    """Enum for job status values."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreate(BaseModel):
    """Request model for creating a new conversion job."""
    input_path: str = Field(..., description="Path to input video in MinIO")
    output_format: Optional[str] = Field("mp4", description="Output video format")
    
    class Config:
        json_schema_extra = {
            "example": {
                "input_path": "uploads/video.avi",
                "output_format": "mp4"
            }
        }


class JobResponse(BaseModel):
    """Response model for job details."""
    id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    input_path: str = Field(..., description="Path to input video")
    output_path: Optional[str] = Field(None, description="Path to converted video")
    output_format: str = Field("mp4", description="Output format")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    conversion_time_ms: Optional[int] = Field(None, description="Conversion time in milliseconds")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "input_path": "uploads/video.avi",
                "output_path": "converted/video.mp4",
                "output_format": "mp4",
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:05:00Z",
                "error_message": None,
                "conversion_time_ms": 30000
            }
        }


class UploadURLRequest(BaseModel):
    """Request model for generating upload URL."""
    filename: str = Field(..., description="Name of the file to upload")
    content_type: Optional[str] = Field("video/mp4", description="MIME type of the file")
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "my_video.avi",
                "content_type": "video/avi"
            }
        }


class UploadURLResponse(BaseModel):
    """Response model for presigned upload URL."""
    upload_url: str = Field(..., description="Presigned URL for file upload")
    object_path: str = Field(..., description="Path where file will be stored")
    job_id: str = Field(..., description="Pre-generated job ID for tracking")
    expires_in: int = Field(3600, description="URL expiration time in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "upload_url": "http://minio:9000/videos/uploads/abc123.avi?...",
                "object_path": "uploads/abc123.avi",
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "expires_in": 3600
            }
        }


class DownloadURLResponse(BaseModel):
    """Response model for presigned download URL."""
    download_url: str = Field(..., description="Presigned URL for file download")
    expires_in: int = Field(3600, description="URL expiration time in seconds")


class QueueMessage(BaseModel):
    """Message format for RabbitMQ job queue."""
    job_id: str = Field(..., description="Job identifier")
    input_path: str = Field(..., description="MinIO path to input file")
    output_format: str = Field("mp4", description="Desired output format")
    created_at: str = Field(..., description="ISO timestamp of job creation")
    
    @classmethod
    def create(cls, job_id: str, input_path: str, output_format: str = "mp4") -> "QueueMessage":
        """Factory method to create a queue message."""
        return cls(
            job_id=job_id,
            input_path=input_path,
            output_format=output_format,
            created_at=datetime.utcnow().isoformat()
        )


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str = Field("healthy", description="Service health status")
    version: str = Field("1.0.0", description="Service version")
    rabbitmq: bool = Field(..., description="RabbitMQ connection status")
    minio: bool = Field(..., description="MinIO connection status")
    database: bool = Field(..., description="Database connection status")
