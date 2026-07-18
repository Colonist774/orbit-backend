from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)


engine = create_engine(
    DATABASE_URL,
    echo=True,
)


SessionLocal = sessionmaker(
    bind=engine,
)


def get_session():
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()