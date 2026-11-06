"""Read-only checks for KoroFarm Farmer History configuration and tables.

Run from src/backend with the same environment as the API server.
No schema creation, migrations, or data writes are performed.
"""
from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import inspect, text


def load_local_env() -> None:
    env_file = Path(__file__).resolve().parents[1] / '.env'
    if not env_file.exists():
        print('No backend .env found. Using existing process environment.')
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, raw = line.split('=', 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = raw.strip().strip('"').strip("'")


def main() -> None:
    existing_database_url = bool(os.getenv('DATABASE_URL'))
    load_local_env()
    if existing_database_url:
        print('Note: existing DATABASE_URL environment variable takes precedence over .env.')
    from app.infrastructure.database.session import create_engine_from_url

    engine = create_engine_from_url()
    print('Connected to:', engine.url.render_as_string(hide_password=True))
    inspector = inspect(engine)
    tables = ('farmers', 'farms', 'farmer_crops', 'historical_production', 'marketplace_receipts')
    with engine.connect() as connection:
        if engine.dialect.name == 'postgresql':
            db, schema = connection.execute(text('SELECT current_database(), current_schema()')).one()
            print('PostgreSQL database:', db, '| current schema:', schema)
        for table in tables:
            exists = inspector.has_table(table)
            print(f'{table}:', 'present' if exists else 'MISSING')
            if exists and table in {'farmers', 'farms', 'farmer_crops', 'historical_production'}:
                count = connection.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar_one()
                print('  rows:', count)
        if inspector.has_table('alembic_version'):
            print('Alembic revisions:', connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all())
        if inspector.has_table('historical_production'):
            years = connection.execute(text('SELECT MIN(production_year), MAX(production_year), COUNT(*) FROM historical_production')).one()
            print('History year range:', years[0], 'to', years[1], '| records:', years[2])
    print('No records were created or changed.')


if __name__ == '__main__':
    main()
