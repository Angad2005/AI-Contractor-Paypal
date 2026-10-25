from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_LEGACY_COLUMNS = {
    "jobs": {
        "deliverable_type": "VARCHAR(32) NOT NULL DEFAULT 'browser_app'",
        "artifact_path": "VARCHAR(255)",
    },
    "app_settings": {
        "is_custom": "BOOLEAN NOT NULL DEFAULT FALSE",
    },
    "payments": {
        "approval_url": "VARCHAR(500)",
        "order_request_id": "VARCHAR(120)",
        "capture_request_id": "VARCHAR(120)",
    },
}


class Base(DeclarativeBase):
    pass


def migrate_legacy_columns(target_engine=engine):
    """Add columns introduced after an existing database was first created."""
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    preparer = target_engine.dialect.identifier_preparer

    with target_engine.begin() as connection:
        for table, required_columns in _LEGACY_COLUMNS.items():
            if table not in existing_tables:
                continue

            existing_columns = {
                column["name"] for column in inspect(connection).get_columns(table)
            }
            for column, definition in required_columns.items():
                if column in existing_columns:
                    continue
                quoted_table = preparer.quote(table)
                quoted_column = preparer.quote(column)
                connection.exec_driver_sql(
                    f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {definition}"
                )
                existing_columns.add(column)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
