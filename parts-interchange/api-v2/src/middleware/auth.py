from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from src.config import settings

_admin_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)
_worker_header = APIKeyHeader(name="X-Worker-Key", auto_error=False)


async def require_admin_key(key: str | None = Security(_admin_header)):
    if key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")


async def require_worker_key(key: str | None = Security(_worker_header)):
    if key != settings.worker_api_key:
        raise HTTPException(status_code=403, detail="Invalid worker key")
