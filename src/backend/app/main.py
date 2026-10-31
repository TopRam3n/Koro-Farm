from fastapi import Depends, FastAPI, Response
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware

from src.backend.app.core.auth import get_current_user
from src.backend.app.core.config import cors_origins, validate_runtime_configuration
from src.backend.app.assurance.api.router import router as assurance_router
from src.backend.app.assurance.api.allocations import router as allocations_router
from src.backend.app.assurance.api.exceptions import router as exceptions_router
from src.backend.app.assurance.api.operations import router as operations_router
from src.backend.app.assurance.application.operations import operational_status
from src.backend.app.main_dependencies import get_session
from src.backend.app.assurance.api.allocations import response_router as supplier_responses_router
from src.backend.app.demand.api.router import router as requirements_router
from src.backend.app.demand.api.buyers import router as buyers_router
from src.backend.app.supply.api.farmers import router as farmers_router
from src.backend.app.supply.api.router import router as production_lots_router
from src.backend.app.supply.api.crops import router as crops_router
from src.backend.app.fulfilment.api.router import router as fulfilment_router
from src.backend.app.reconciliation.api.router import router as reconciliation_router
from src.backend.app.compliance.api.router import router as compliance_router
from src.backend.app.trade_evidence.api.corridors import router as corridors_router
from src.backend.app.programmes.api.router import router as programmes_router
from src.backend.app.registry.api.router import router as registry_router
from src.backend.app.identity.api.router import router as identity_router
from src.backend.app.identity.application.authorization import require_roles
from src.backend.app.identity.application.tenancy import enforce_path_scope
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.ingestion.api.router import public_router as secure_actions_router
from src.backend.app.ingestion.api.router import router as ingestion_router
from src.backend.app.marketplace.api.router import router as marketplace_router

# Fail closed: refuse to start with configuration that could bypass or fake authentication.
validate_runtime_configuration()

app = FastAPI(title="KoroFarm Supply Assurance API", version="0.1.0")
staff_roles = (
    RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN, RoleCode.PROCUREMENT_MANAGER,
    RoleCode.SUPPLY_COORDINATOR, RoleCode.WAREHOUSE_OPERATOR, RoleCode.AUDITOR,
)
# Every staff router is organization-scoped: enforce_path_scope resolves each *_id path parameter to its
# owning organization and refuses anything it cannot attribute (identity/application/tenancy.py).
staff_dependencies = [Depends(get_current_user), Depends(require_roles(*staff_roles)), Depends(enforce_path_scope)]
app.include_router(requirements_router, dependencies=staff_dependencies)
app.include_router(buyers_router, dependencies=staff_dependencies)
app.include_router(farmers_router, dependencies=staff_dependencies)
app.include_router(assurance_router, dependencies=staff_dependencies)
app.include_router(allocations_router, dependencies=staff_dependencies)
app.include_router(exceptions_router, dependencies=staff_dependencies)
app.include_router(operations_router, dependencies=staff_dependencies)
# Farmers answer their own solicitations; staff record decisions on a farmer's behalf (commitments.respond enforces which).
app.include_router(supplier_responses_router, dependencies=[
    Depends(get_current_user), Depends(require_roles(*staff_roles, RoleCode.FARMER)), Depends(enforce_path_scope),
])
app.include_router(production_lots_router, dependencies=[
    Depends(get_current_user), Depends(require_roles(*staff_roles, RoleCode.FARMER)), Depends(enforce_path_scope),
])
app.include_router(fulfilment_router, dependencies=staff_dependencies)
# Any active member (farmers and buyers included) may read the crop catalogue; creation checks permissions.
app.include_router(crops_router, dependencies=[Depends(get_current_user), Depends(enforce_path_scope)])
app.include_router(reconciliation_router, dependencies=staff_dependencies)
app.include_router(compliance_router, dependencies=staff_dependencies)
app.include_router(corridors_router, dependencies=staff_dependencies)
app.include_router(programmes_router, dependencies=staff_dependencies)
app.include_router(registry_router, dependencies=staff_dependencies)
app.include_router(marketplace_router, dependencies=[Depends(get_current_user)])
app.include_router(identity_router)
app.include_router(ingestion_router)
app.include_router(secure_actions_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """The API process is up. It says nothing about exception monitoring; see /health/worker."""
    return {"status": "ok"}


@app.get("/health/worker", tags=["health"])
def worker_health(response: Response, session: Session = Depends(get_session)) -> dict:
    """Readiness of supply-exception monitoring, for uptime probes: 503 unless OPERATIONAL. No tenant data."""
    state = operational_status(session)
    if state["status"] != "OPERATIONAL":
        response.status_code = 503
    return {"status": state["status"], "reasons": state["reasons"], "worker": state["worker"]["state"],
            "last_beat_at": state["worker"]["last_beat_at"]}
