"""JSON API for the admin SPA (admin_ui/)."""
from fastapi import APIRouter

from . import catalogue, discrepancies, fixes, vehicles

router = APIRouter()
router.include_router(catalogue.router)
router.include_router(discrepancies.router)
router.include_router(fixes.router)
router.include_router(vehicles.router)

