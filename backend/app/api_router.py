from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.marketplace.router import router as marketplace_router
from app.modules.plans.router import router as plans_router
from app.modules.profiles.router import router as profiles_router
from app.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(profiles_router)
api_router.include_router(plans_router)
api_router.include_router(marketplace_router)
