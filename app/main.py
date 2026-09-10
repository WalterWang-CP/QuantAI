from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.policy.routes import router as policy_router
from app.identity.routes import router as identity_router
from app.universe.routes import router as universe_router

app = FastAPI(
    title=settings.app_name,
    description="Point-in-time financial data and company universe platform",
    version="0.5.0",
)


app.include_router(policy_router)
app.include_router(identity_router)
app.include_router(universe_router)


@app.get("/")
def root():
    return {
        "application": settings.app_name,
        "version": "0.5.0",
        "status": "running",
    }

@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "healthy",
        }

    except Exception:
        return {
            "status": "degraded",
            "database": "unhealthy",
        }