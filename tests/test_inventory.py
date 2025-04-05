import pytest
import logging
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.main import app
from app.models import Base, Item, Container  # Add Item and Container imports
from app.utils.database import get_db
from app.services.placement import PlacementService
from app.services.search import SearchService
from app.services.waste import WasteManagementService
from app.services.simulation import SimulationService
from app.schemas import SimulationRequest

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"  # Use in-memory database for tests
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool  # Use StaticPool for test concurrency
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def test_db():
    """Create a fresh database for each test"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client that shares the test database session"""
    app.dependency_overrides[get_db] = lambda: test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

def test_placement_optimization():
    """Test item placement optimization"""
    service = PlacementService()
    items = [
        {
            "itemId": "001",
            "name": "Test Item",
            "width": 10,
            "depth": 10,
            "height": 20,
            "priority": 80,
            "preferredZone": "Zone A"
        }
    ]
    containers = [
        {
            "containerId": "contA",
            "zone": "Zone A",
            "width": 100,
            "depth": 85,
            "height": 200
        }
    ]
    
    placements, rearrangements = service.optimize_placement(items, containers)
    assert len(placements) == 1
    assert placements[0].item_id == "001"  # Use snake_case
    assert placements[0].container_id == "contA"  # Use snake_case

def test_search_and_retrieval(test_db, client):
    """Test item search and retrieval"""
    service = SearchService()
    
    # Add test item
    response = client.post(
        "/api/import/items",
        files={
            "file": ("items.csv", "Item ID,Name,Width,Depth,Height,Mass,Priority,Expiry Date,Usage Limit,Preferred Zone\n001,Test Item,10,10,20,5,80,2025-12-31,10,Zone A")
        }
    )
    assert response.status_code == 200

    # Query directly from database to verify item exists
    item = test_db.query(Item).filter(Item.id == "001").first()
    assert item is not None, "Item was not properly imported"
    
    # Test search
    result = service.search_item(test_db, item_id="001")
    assert result.found == True
    assert result.item["itemId"] == "001"
    
    # Test retrieval
    success = service.log_retrieval(
        test_db,
        "001",
        "test_user",
        datetime.now(timezone.utc)  # Use timezone-aware datetime
    )
    assert success == True

def test_waste_management(test_db, client):
    """Test waste identification and handling"""
    service = WasteManagementService()
    
    # Add expired item
    response = client.post(
        "/api/import/items",
        files={
            "file": ("items.csv", "Item ID,Name,Width,Depth,Height,Mass,Priority,Expiry Date,Usage Limit,Preferred Zone\n001,Expired Item,10,10,20,5,80,2024-01-01,10,Zone A")
        }
    )
    assert response.status_code == 200
    
    # Query database to verify item exists
    item = test_db.query(Item).filter(Item.id == "001").first()
    assert item is not None, "Item was not properly imported"
    
    # Check waste identification
    waste_items = service.identify_waste_items(test_db)
    assert len(waste_items) == 1
    assert waste_items[0].itemId == "001"  # Using camelCase as defined in schema

def test_time_simulation(test_db, client):
    """Test time simulation and item status updates"""
    service = SimulationService()
    
    # Add test item
    response = client.post(
        "/api/import/items",
        files={
            "file": ("items.csv", "Item ID,Name,Width,Depth,Height,Mass,Priority,Expiry Date,Usage Limit,Preferred Zone\n001,Test Item,10,10,20,5,80,2025-12-31,3,Zone A")
        }
    )
    assert response.status_code == 200
    
    # Query database to verify item exists
    item = test_db.query(Item).filter(Item.id == "001").first()
    assert item is not None, "Item was not properly imported"
    assert item.uses_remaining == 3, "Uses remaining not properly set"
    
    # Simulate usage for 5 days (should deplete the item)
    result = service.simulate_time(
        test_db,
        SimulationRequest(
            numOfDays=5,
            itemsToBeUsedPerDay=[{"itemId": "001"}]
        )
    )
    assert result.success == True
    assert len(result.changes["itemsDepletedToday"]) == 1
    
    # Verify item was marked as waste
    item = test_db.query(Item).filter(Item.id == "001").first()
    assert item.is_waste == True, "Item not marked as waste after depletion"

def test_csv_import_export(test_db, client):
    """Test CSV import and export functionality"""
    # Test container import
    containers_response = client.post(
        "/api/import/containers",
        files={
            "file": ("containers.csv", "Container ID,Zone,Width,Depth,Height\ncontA,Zone A,100,85,200")
        }
    )
    assert containers_response.status_code == 200
    resp_json = containers_response.json()
    print(f"Container import response: {resp_json}")  # Debug print
    assert resp_json["success"] == True, "Container import failed"
    assert resp_json["containersImported"] == 1
    
    # Verify container in database
    container = test_db.query(Container).filter(Container.id == "contA").first()
    assert container is not None, "Container was not properly imported"
    
    # Test items import
    items_response = client.post(
        "/api/import/items",
        files={
            "file": ("items.csv", "Item ID,Name,Width,Depth,Height,Mass,Priority,Expiry Date,Usage Limit,Preferred Zone\n001,Test Item,10,10,20,5,80,2025-12-31,10,Zone A")
        }
    )
    assert items_response.status_code == 200
    resp_json = items_response.json()
    print(f"Items import response: {resp_json}")  # Debug print
    assert resp_json["success"] == True, f"Item import failed: {resp_json.get('message')}"
    assert resp_json["itemsImported"] == 1
    
    # Verify item in database
    item = test_db.query(Item).filter(Item.id == "001").first()
    assert item is not None, "Item was not properly imported"
    
    # Test arrangement export
    export_response = client.get("/api/export/arrangement")
    assert export_response.status_code == 200
    assert "content" in export_response.json()

def test_logging(test_db, client):
    """Test action logging"""
    # Use timezone-aware datetime
    now = datetime.now(timezone.utc)
    
    # First, add the item that will be retrieved
    response = client.post(
        "/api/import/items",
        files={
            "file": ("items.csv", "Item ID,Name,Width,Depth,Height,Mass,Priority,Expiry Date,Usage Limit,Preferred Zone\n001,Test Item,10,10,20,5,80,2025-12-31,10,Zone A")
        }
    )
    assert response.status_code == 200
    
    # Query database to verify item exists
    item = test_db.query(Item).filter(Item.id == "001").first()
    assert item is not None, "Item was not properly imported"
    
    # Log retrieval action
    retrieval_response = client.post(
        "/api/retrieve",
        json={
            "itemId": "001",
            "userId": "test_user",
            "timestamp": now.isoformat()
        }
    )
    assert retrieval_response.status_code == 200
    
    # Check logs
    logs_response = client.get(
        "/api/logs",
        params={
            "startDate": (now - timedelta(days=1)).isoformat(),
            "endDate": (now + timedelta(days=1)).isoformat(),  # Widen time window
            "actionType": "retrieval"
        }
    )
    assert logs_response.status_code == 200
    logs = logs_response.json()["logs"]
    assert len(logs) > 0
    assert logs[0]["actionType"] == "retrieval"