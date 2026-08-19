from fastapi import FastAPI

from app.assurance.api.router import router as assurance_router
from app.demand.api.router import router as requirements_router
from app.supply.api.router import router as production_lots_router

app = FastAPI(title="KoroFarm Supply Assurance API", version="0.1.0")
app.include_router(requirements_router)
app.include_router(assurance_router)
app.include_router(production_lots_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
