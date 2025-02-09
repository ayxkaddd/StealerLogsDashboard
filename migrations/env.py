import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, engine_from_config, pool, text
from sqlalchemy_utils import database_exists, create_database

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_URL
from models.log_models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def setup_database():
    sync_db_url = DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_db_url)

    if not database_exists(engine.url):
        create_database(engine.url)
        print(f"Created database {engine.url.database}")

    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        connection.commit()

def run_migrations_online():
    setup_database()
    sync_db_url = DATABASE_URL.replace("+asyncpg", "")
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = sync_db_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    from alembic import context
    context.run_migrations()
else:
    run_migrations_online()