from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import settings

db_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Supabase's transaction-mode pooler reuses connections across transactions, which
# breaks server-side prepared statements (DuplicatePreparedStatement errors).
# Disable them at the psycopg level.
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
