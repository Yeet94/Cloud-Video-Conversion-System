# Shared configuration for video processing services
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # RabbitMQ Configuration
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_queue: str = "video-jobs"
    rabbitmq_vhost: str = "/"
    
   # MinIO Configuration
    minio_endpoint: str = "minio:9000"
    minio_external_endpoint: str = "localhost:9000"  # For presigned URLs accessible from browser
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "videos"
    minio_secure:bool = False
    
    # Database Configuration
    database_path: str = "/data/jobs.db"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # FFmpeg Configuration
    ffmpeg_output_format: str = "mp4"
    ffmpeg_video_codec: str = "libx264"
    ffmpeg_audio_codec: str = "aac"
    ffmpeg_preset: str = "medium"
    ffmpeg_crf: int = 23  # Quality: 0 (lossless) to 51 (worst)
    
    # Metrics Configuration
    metrics_port: int = 8001
    
    @property
    def rabbitmq_url(self) -> str:
        """Get RabbitMQ connection URL."""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
    
    @property
    def database_url(self) -> str:
        """Get SQLite database URL."""
        return f"sqlite:///{self.database_path}"
    
    class Config:
        env_prefix = "APP_"  # Avoid conflicts with Kubernetes service env vars
        case_sensitive = False
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
