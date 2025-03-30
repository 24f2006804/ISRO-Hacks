from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./space_station.db"

# Create engine with check_same_thread=False for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool  # Use StaticPool for better concurrency in tests
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from ..models import Base
    Base.metadata.create_all(bind=engine)