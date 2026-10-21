from fastapi import APIRouter

from app.modules.cms.admin_router import router as admin_router
from app.modules.cms.public_router import router as public_router

router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)
