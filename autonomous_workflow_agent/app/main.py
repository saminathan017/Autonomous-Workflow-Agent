"""
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from autonomous_workflow_agent.app.api.routes import router
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.utils.logging import setup_logging, get_logger

# Initialize logging
settings = get_settings()
setup_logging(log_level=settings.log_level)
logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Autonomous Workflow Agent",
    description="Email → Sheets → AI Report automation system",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api", tags=["workflow"])

# Mount static files for frontend
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Mounted frontend from {frontend_dir}")
else:
    logger.warning(f"Frontend directory not found: {frontend_dir}")


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Autonomous Workflow Agent starting up...")
    logger.info(f"OpenAI Model: {settings.openai_model}")
    logger.info(f"Max OpenAI calls per run: {settings.openai_max_calls_per_run}")
    logger.info(f"Database: {settings.database_path}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Autonomous Workflow Agent shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "autonomous_workflow_agent.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug
    )
