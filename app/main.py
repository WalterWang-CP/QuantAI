from fastapi import FastAPI

from app.policy.routes import router as policy_router


app = FastAPI(
    title="QuantAI Data Engine",
    description="Point-in-time financial data and company universe platform",
    version="0.2.0",
)


app.include_router(policy_router)


@app.get("/")
def root():
    return {
        "application": "QuantAI Data Engine",
        "version": "0.2.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }