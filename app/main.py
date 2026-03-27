"""
FastAPI application entry point.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # 加载 .env 到 os.environ，确保 LangSmith 等环境变量生效

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from app.config import get_settings
from app.api.router import api_router

settings = get_settings()

# --- Logging ---
logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
)

# --- App ---
app = FastAPI(
    title="AI Virtual Interview Coach",
    description="Multimodal AI interview system powered by LangGraph + Hybrid RAG",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

# ── Static frontend ────────────────────────────────────────────────────
_STATIC = Path(__file__).parents[1] / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(_STATIC / "index.html"))


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.app_env}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
