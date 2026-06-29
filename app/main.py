"""
FastAPI application entry point.
"""
import asyncio
import sys
from contextlib import asynccontextmanager
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
from app.db.database import init_db
from app.core.runtime_safety import parse_cors_origins, validate_runtime_settings

settings = get_settings()
runtime_issues = validate_runtime_settings(settings)
if runtime_issues:
    raise RuntimeError("Unsafe production configuration: " + "; ".join(runtime_issues))

# --- Logging ---
logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
)

async def _preload_gliner() -> None:
    try:
        from app.rag.graph_rag.knowledge_base import _get_gliner

        logger.info("Starting GLiNER preload in background")
        model = await asyncio.to_thread(_get_gliner)
        if model is None:
            logger.warning("GLiNER preload finished: unavailable")
        else:
            logger.info("GLiNER preload finished")
    except Exception as e:
        logger.warning(f"GLiNER preload failed: {e}")


async def _preload_knowledge_graph() -> None:
    try:
        from app.rag.graph_rag.knowledge_base import get_knowledge_graph

        logger.info("Starting knowledge graph preload in background")
        kg = await asyncio.to_thread(get_knowledge_graph)
        logger.info(f"Knowledge graph preload finished: {type(kg).__name__}")
    except Exception as e:
        logger.warning(f"Knowledge graph preload failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    preload_tasks: list[asyncio.Task] = []
    if settings.preload_gliner_on_startup:
        preload_tasks.append(asyncio.create_task(_preload_gliner()))
    if settings.preload_knowledge_graph_on_startup:
        preload_tasks.append(asyncio.create_task(_preload_knowledge_graph()))
    app.state.preload_tasks = preload_tasks
    try:
        yield
    finally:
        for task in preload_tasks:
            if not task.done():
                task.cancel()


# --- App ---
app = FastAPI(
    title="AI Virtual Interview Coach",
    description="Multimodal AI interview system powered by LangGraph + Hybrid RAG",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(settings.cors_allowed_origins, settings.app_env),
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

    @app.get("/admin", include_in_schema=False)
    async def serve_admin():
        return FileResponse(str(_STATIC / "admin.html"))


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
