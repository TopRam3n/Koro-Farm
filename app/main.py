from fastapi import FastAPI

from app.assurance.api.router import router as assurance_router
from app.assurance.api.allocations import router as allocations_router
from app.demand.api.router import router as requirements_router
from app.supply.api.router import router as production_lots_router
from app.fulfilment.api.router import router as fulfilment_router

app = FastAPI(title="KoroFarm Supply Assurance API", version="0.1.0")
app.include_router(requirements_router)
app.include_router(assurance_router)
app.include_router(allocations_router)
app.include_router(production_lots_router)
app.include_router(fulfilment_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
