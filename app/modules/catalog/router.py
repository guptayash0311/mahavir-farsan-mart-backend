from fastapi import APIRouter

from app.modules.catalog.admin_router import router as admin_router
from app.modules.catalog.public_router import router as public_router

router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)
