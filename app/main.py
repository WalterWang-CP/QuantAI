from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.policy.routes import router as policy_router
from app.identity.routes import router as identity_router
from app.universe.routes import router as universe_router
from app.tracking.routes import router as tracking_router
from app.providers.routes import router as provider_router
from app.market_data.routes import router as market_data_router
from app.retrieval.routes import router as retrieval_router

app = FastAPI(
    title=settings.app_name,
    description="Point-in-time financial data and company universe platform",
    version="0.11.0",
)


app.include_router(policy_router)
app.include_router(identity_router)
app.include_router(universe_router)
app.include_router(tracking_router)
app.include_router(provider_router)
app.include_router(market_data_router)
app.include_router(retrieval_router)


@app.get("/")
def root():
    return {
        "application": settings.app_name,
        "version": "0.11.0",
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