from logging.config import fileConfig
import os
from pathlib import Path
import sys

# Alembic is normally invoked from ``src/backend``. Ensure the repository root
# is importable so the application's canonical ``src.backend`` imports work in
# a clean checkout as well as from an IDE launched at the repository root.
repository_root = Path(__file__).resolve().parents[3]
if str(repository_root) not in sys.path:
    sys.path.insert(0, str(repository_root))

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.backend.app.demand.domain.models import Buyer, Requirement  # noqa: F401
from src.backend.app.economics.domain.models import CostSnapshot, LotCostInput  # noqa: F401
from src.backend.app.fulfilment.domain.models import FulfilmentNode  # noqa: F401
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.supply.domain.models import Farmer, ProductionLot  # noqa: F401
from src.backend.app.supply.domain.planning_models import SupplyAllocation, SupplyPlan  # noqa: F401
from src.backend.app.programmes.domain.models import Programme  # noqa: F401
from src.backend.app.identity.domain.models import (  # noqa: F401
    AccessRequest, Organization, OrganizationMembership, Permission, Role, RolePermission, UserAccount,
)
from src.backend.app.ingestion.domain.models import (  # noqa: F401
    BulkImport, BulkImportRow, IngestionRecord, OperationalObservation, OutboundMessage, SecureActionLink,
)
from src.backend.app.marketplace.domain.models import AvailabilityAlert, AvailabilityWatch, MarketplaceOrder  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
if database_url := os.getenv("DATABASE_URL"):
    # configparser treats "%" as interpolation; URL-encoded passwords (e.g. %40) must be escaped.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Migrations take explicit locks and run DDL; use the session pooler or a direct connection, not port 6543.
    connect_args = {"prepare_threshold": None} if ":6543/" in config.get_main_option("sqlalchemy.url", "") else {}
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool, connect_args=connect_args)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
