"""
Database migration script for adding new columns and tables.

Run this after updating the code to add new features:
- is_custom column to app_settings table
- generation_versions table for version history
- missing columns to payments table (approval_url, order_request_id, capture_request_id)

Note: If the database doesn't exist yet, run the application first to create the schema,
then run this script to add any additional columns/tables.
"""

from app.db.database import engine, Base
from app.db.models import AppSetting, GenerationVersion
from sqlalchemy import text

def migrate():
    """Add new columns and tables if they don't exist"""

    # First, create all tables if they don't exist
    print("Creating database schema...")
    Base.metadata.create_all(bind=engine)
    print("✓ Database schema created/verified")

    with engine.connect() as conn:
        # Check if app_settings table exists
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'"))
        app_settings_exists = result.fetchone()

        if app_settings_exists:
            # Check if is_custom column exists in app_settings
            result = conn.execute(text("PRAGMA table_info(app_settings)"))
            columns = [row[1] for row in result.fetchall()]

            if 'is_custom' not in columns:
                print("Adding is_custom column to app_settings table...")
                conn.execute(text("ALTER TABLE app_settings ADD COLUMN is_custom BOOLEAN DEFAULT 0"))
                conn.commit()
                print("✓ is_custom column added")
            else:
                print("✓ is_custom column already exists")
        else:
            print("✓ app_settings table does not exist (will be created by SQLAlchemy)")

        # Check if generation_versions table exists
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='generation_versions'"))
        table_exists = result.fetchone()

        if not table_exists:
            print("Creating generation_versions table...")
            conn.execute(text("""
                CREATE TABLE generation_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id VARCHAR(36) NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    html_content TEXT,
                    css_content TEXT,
                    js_content TEXT,
                    verification_results JSON,
                    browser_results JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs (id)
                )
            """))
            conn.commit()
            print("✓ generation_versions table created")
        else:
            print("✓ generation_versions table already exists")

        # Check if payments table exists and add missing columns
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'"))
        payments_table_exists = result.fetchone()

        if payments_table_exists:
            result = conn.execute(text("PRAGMA table_info(payments)"))
            payment_columns = [row[1] for row in result.fetchall()]

            # Columns that should exist in payments table
            required_columns = {
                'approval_url': 'VARCHAR(500)',
                'order_request_id': 'VARCHAR(120)',
                'capture_request_id': 'VARCHAR(120)'
            }

            for col_name, col_type in required_columns.items():
                if col_name not in payment_columns:
                    print(f"Adding {col_name} column to payments table...")
                    conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"✓ {col_name} column added")
                else:
                    print(f"✓ {col_name} column already exists")
        else:
            print("✓ payments table does not exist (will be created by SQLAlchemy)")

    print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
