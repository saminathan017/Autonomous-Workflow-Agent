"""
Configuration management for the Autonomous Workflow Agent.
Loads settings from environment variables with safe defaults.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    openai_max_tokens: int = Field(default=800, description="Maximum tokens per request")
    openai_timeout_seconds: int = Field(default=20, description="Request timeout in seconds")
    openai_max_calls_per_run: int = Field(default=5, description="Maximum OpenAI calls per workflow run")
    
    # Google OAuth Configuration
    google_client_id: str = Field(..., description="Google OAuth client ID")
    google_client_secret: str = Field(..., description="Google OAuth client secret")
    google_redirect_uri: str = Field(default="http://localhost:8000/auth/callback", description="OAuth redirect URI")
    
    # Google Sheets Configuration
    google_sheet_id: str = Field(..., description="Target Google Sheet ID")
    
    # Application Configuration
    app_host: str = Field(default="0.0.0.0", description="Application host")
    app_port: int = Field(default=8000, description="Application port")
    app_debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Database Configuration
    database_path: str = Field(default="data/state.db", description="SQLite database path")
    
    # Workflow Configuration
    workflow_max_retries: int = Field(default=3, description="Maximum retries per workflow step")
    workflow_retry_delay_seconds: int = Field(default=5, description="Delay between retries")
    
    class Config:
        env_file = str(Path(__file__).parent.parent / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def get_absolute_database_path(self) -> Path:
        """Get the absolute path to the database file."""
        if Path(self.database_path).is_absolute():
            return Path(self.database_path)
        # Resolve relative to project root
        project_root = Path(__file__).parent.parent
        return project_root / self.database_path


# Global settings instance
settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global settings
    if settings is None:
        settings = Settings()
    return settings


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """Get the data directory, creating it if necessary."""
    data_dir = get_project_root() / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


def get_reports_dir() -> Path:
    """Get the reports directory, creating it if necessary."""
    reports_dir = get_data_dir() / "reports"
    reports_dir.mkdir(exist_ok=True)
    return reports_dir
