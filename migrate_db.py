"""Manually apply the additive schema updates also run at application startup."""

from app.db.database import Base, engine, migrate_legacy_columns
from app.db import models


def migrate():
    Base.metadata.create_all(bind=engine)
    migrate_legacy_columns(engine)
    print("Database schema migration completed successfully.")


if __name__ == "__main__":
    migrate()
