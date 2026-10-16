"""JSON API for the admin SPA (admin_ui/). The Jinja pages under /admin/ui stay until phase 5."""
from fastapi import APIRouter

from . import catalogue, discrepancies, fixes, vehicles

router = APIRouter()
router.include_router(catalogue.router)
router.include_router(discrepancies.router)
router.include_router(fixes.router)
router.include_router(vehicles.router)

