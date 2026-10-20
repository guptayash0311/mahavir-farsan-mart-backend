from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.modules.automation.router import router as automation_router
from app.modules.business.router import router as business_router
from app.modules.catalog.router import router as catalog_router
from app.modules.cms.router import router as cms_router
from app.modules.commerce.router import router as commerce_router
from app.modules.documents.router import router as documents_router
from app.modules.governance.router import router as governance_router
from app.modules.identity.router import router as identity_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(identity_router, tags=["identity"])
api_router.include_router(catalog_router, tags=["catalog"])
api_router.include_router(cms_router, tags=["cms"])
api_router.include_router(commerce_router, tags=["commerce"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(business_router, tags=["business"])
api_router.include_router(automation_router, tags=["automation"])
api_router.include_router(governance_router, tags=["governance"])
