from app.marketplace.api.requests import router as marketplace_requests_router
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import get_current_user
from app.agriculture.api import router as agricultural_intelligence_router
from app.core.config import cors_origins
from app.assurance.api.router import router as assurance_router
from app.assurance.api.allocations import router as allocations_router
from app.demand.api.router import router as requirements_router
from app.supply.api.router import router as production_lots_router
from app.fulfilment.api.router import router as fulfilment_router
from app.reconciliation.api.router import router as reconciliation_router
from app.compliance.api.router import router as compliance_router
from app.trade_evidence.api.corridors import router as corridors_router
from app.programmes.api.router import router as programmes_router
from app.registry.api.router import router as registry_router
from app.identity.api.router import router as identity_router
from app.identity.application.authorization import require_roles
from app.identity.domain.permissions import RoleCode
from app.ingestion.api.router import public_router as secure_actions_router
from app.ingestion.api.router import router as ingestion_router
from app.marketplace.api.router import router as marketplace_router
from app.supply.api.farmer_history import router as farmer_history_router

app = FastAPI(title="KoroFarm Supply Assurance API", version="0.1.0")
app.include_router(agricultural_intelligence_router, dependencies=[Depends(get_current_user)])
staff_roles = (
    RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN, RoleCode.PROCUREMENT_MANAGER,
    RoleCode.SUPPLY_COORDINATOR, RoleCode.WAREHOUSE_OPERATOR, RoleCode.AUDITOR,
)
staff_dependencies = [Depends(get_current_user), Depends(require_roles(*staff_roles))]
app.include_router(requirements_router, dependencies=staff_dependencies)
app.include_router(assurance_router, dependencies=staff_dependencies)
app.include_router(allocations_router, dependencies=staff_dependencies)
app.include_router(production_lots_router, dependencies=[
    Depends(get_current_user), Depends(require_roles(*staff_roles, RoleCode.FARMER)),
])
app.include_router(fulfilment_router, dependencies=staff_dependencies)
app.include_router(reconciliation_router, dependencies=staff_dependencies)
app.include_router(compliance_router, dependencies=staff_dependencies)
app.include_router(corridors_router, dependencies=staff_dependencies)
app.include_router(programmes_router, dependencies=staff_dependencies)
app.include_router(registry_router, dependencies=staff_dependencies)
app.include_router(marketplace_router, dependencies=[Depends(get_current_user)])
app.include_router(marketplace_requests_router, dependencies=[Depends(get_current_user)])
app.include_router(identity_router)
app.include_router(ingestion_router)
app.include_router(secure_actions_router)
app.include_router(
    farmer_history_router,
    dependencies=[
        Depends(get_current_user),
        Depends(require_roles(*staff_roles, RoleCode.FARMER)),
    ],
)

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
