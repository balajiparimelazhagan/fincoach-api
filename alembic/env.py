from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import settings
from app.db import Base
from app.models import User, Currency, Category, Transactor, Transaction, Budget, BudgetItem

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

        # Run post-migration synthetic data script using the existing connection
        # so that all inserts occur in the same database as the migrations.  We
        # adjust sys.path so that the `scripts` package can be imported when
        # Alembic is executed from the alembic directory inside the container.
        try:
            import sys
            import os as _os
            root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
            if root not in sys.path:
                sys.path.insert(0, root)

            from scripts.synthetic_data_seeder import main as _post_main

            # connection is a SQLAlchemy Connection; extract the raw DBAPI
            # connection (psycopg2) so our helper can use it.
            dbapi_conn = connection.connection
            _post_main(dbapi_conn)
            print("Post-migration synthetic data script completed")
        except Exception as e:
            # Log the error but do not interrupt migrations
            print(f"Error running post-migration script: {e}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

