"""Read-only check: backend .env, selected database, migrations and tables.

Run from src/backend with your venv activated:
    python3 scripts/verify_korofarm_db.py

Does not print database passwords and does not alter any tables.
"""
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

# The standard FastAPI start command uses --env-file .env. Match that choice
# without overriding an explicitly exported DATABASE_URL.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from app.infrastructure.database.session import create_engine_from_url  # noqa: E402

engine = create_engine_from_url()
print("Engine URL:", engine.url.render_as_string(hide_password=True))
with engine.connect() as conn:
    print("Connected database:", conn.execute(text("SELECT current_database()")).scalar())
    print("Current schema:", conn.execute(text("SELECT current_schema()")).scalar())
    tables = inspect(conn)
    if tables.has_table("alembic_version"):
        print("Alembic revisions:", conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars().all())
    else:
        print("Alembic revisions: table not found")
    for name in ["buyers", "requirements", "programmes", "farmer_offers", "fulfilment_nodes", "marketplace_receipts"]:
        print(f"{name}: {'present' if tables.has_table(name) else 'MISSING'}")
