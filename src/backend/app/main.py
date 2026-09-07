from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.backend.app.core.auth import get_current_user
from src.backend.app.core.config import cors_origins
from src.backend.app.assurance.api.router import router as assurance_router
from src.backend.app.assurance.api.allocations import router as allocations_router
from src.backend.app.demand.api.router import router as requirements_router
from src.backend.app.supply.api.router import router as production_lots_router
from src.backend.app.fulfilment.api.router import router as fulfilment_router
from src.backend.app.reconciliation.api.router import router as reconciliation_router
from src.backend.app.compliance.api.router import router as compliance_router
from src.backend.app.trade_evidence.api.corridors import router as corridors_router

app = FastAPI(title="KoroFarm Supply Assurance API", version="0.1.0")
app.include_router(requirements_router, dependencies=[Depends(get_current_user)])
app.include_router(assurance_router, dependencies=[Depends(get_current_user)])
app.include_router(allocations_router, dependencies=[Depends(get_current_user)])
app.include_router(production_lots_router, dependencies=[Depends(get_current_user)])
app.include_router(fulfilment_router, dependencies=[Depends(get_current_user)])
app.include_router(reconciliation_router, dependencies=[Depends(get_current_user)])
app.include_router(compliance_router, dependencies=[Depends(get_current_user)])
app.include_router(corridors_router, dependencies=[Depends(get_current_user)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
