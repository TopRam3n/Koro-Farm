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

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
if database_url := os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
