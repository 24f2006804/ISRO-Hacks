from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging

logger = logging.getLogger(__name__)

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
    from ..models import Base, Item, Container
    inspector = inspect(engine)
    
    # Get existing tables
    existing_tables = inspector.get_table_names()
    logger.info(f"Existing tables: {existing_tables}")
    
    # Create tables if they don't exist
    if not all(table in existing_tables for table in ['items', 'containers', 'logs']):
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    else:
        logger.info("All required tables already exist")