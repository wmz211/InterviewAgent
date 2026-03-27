"""
Aggregate all API endpoint routers.
"""
from fastapi import APIRouter

from app.api.endpoints import interview, upload, ws

api_router = APIRouter()

api_router.include_router(upload.router, prefix="/upload", tags=["Upload"])
api_router.include_router(interview.router, prefix="/interview", tags=["Interview"])
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
