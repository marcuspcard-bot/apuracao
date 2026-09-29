from alembic import context
from app.core.database import Base, get_engine
import app.models  # noqa: F401

if context.is_offline_mode():
    context.configure(url=get_engine().url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
