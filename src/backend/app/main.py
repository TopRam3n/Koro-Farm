from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.backend.app.assurance.api.router import router as assurance_router
from src.backend.app.assurance.api.allocations import router as allocations_router
from src.backend.app.demand.api.router import router as requirements_router
from src.backend.app.supply.api.router import router as production_lots_router
from src.backend.app.fulfilment.api.router import router as fulfilment_router

app = FastAPI(title="KoroFarm Supply Assurance API", version="0.1.0")
app.include_router(requirements_router)
app.include_router(assurance_router)
app.include_router(allocations_router)
app.include_router(production_lots_router)
app.include_router(fulfilment_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Bun/Vite development server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
