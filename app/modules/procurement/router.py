"""Procurement application entry. The business package still owns the records."""

from fastapi import APIRouter

from app.modules.business.router import router as business_router

router = APIRouter()
router.include_router(business_router)
