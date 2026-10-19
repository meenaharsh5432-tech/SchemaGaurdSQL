from sqlalchemy import create_engine
from app.config import settings

engine=create_engine(
    settings.database_url.get_secret_value(),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=0,
    pool_timeout=5,
    connect_args={"connect_timeout":5},
)