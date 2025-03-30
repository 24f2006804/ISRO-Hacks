from fastapi import FastAPI, UploadFile, File, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from .schemas import (
    PlacementRequest, PlacementResponse,
    SearchResponse, RetrievalRequest,
    PlaceItemRequest, WasteResponse,
    ReturnPlanRequest, ReturnPlanResponse,
    SimulationRequest, SimulationResponse,
    LogResponse
)
from .services.placement import PlacementService
from .services.search import SearchService
from .services.waste import WasteManagementService
from .services.simulation import SimulationService
from .services.logging import LoggingService
from .utils.database import get_db, init_db
from .utils.csv_handler import CSVHandler
from .middleware.error_handler import error_handler_middleware
import os

app = FastAPI(title="Space Station Inventory Management System")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure templates
templates = Jinja2Templates(directory="templates")

# Add error handling middleware
app.middleware("http")(error_handler_middleware)

# Initialize services
placement_service = PlacementService()
search_service = SearchService()  # Initialize as instance
waste_service = WasteManagementService()
simulation_service = SimulationService()
logging_service = LoggingService()

# Initialize database
init_db()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend routes
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/inventory")
async def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", {"request": request})

@app.get("/waste")
async def waste_page(request: Request):
    return templates.TemplateResponse("waste.html", {"request": request})

@app.get("/simulation")
async def simulation_page(request: Request):
    return templates.TemplateResponse("simulation.html", {"request": request})

# API routes
@app.post("/api/placement", response_model=PlacementResponse)
async def placement_recommendations(
    request: PlacementRequest,
    db: Session = Depends(get_db)
):
    placements, rearrangements = placement_service.optimize_placement(
        request.items,
        request.containers
    )
    return PlacementResponse(
        success=True,
        placements=placements,
        rearrangements=rearrangements
    )

@app.get("/api/search", response_model=SearchResponse)
async def search_item(
    itemId: Optional[str] = None,
    itemName: Optional[str] = None,
    userId: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return search_service.search_item(db, itemId, itemName)

@app.post("/api/retrieve")
async def retrieve_item(
    request: RetrievalRequest,
    db: Session = Depends(get_db)
):
    # Handle timezone-aware timestamp
    if request.timestamp.tzinfo is None:
        timestamp = request.timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = request.timestamp

    success = search_service.log_retrieval(
        db,
        str(request.item_id),  # Ensure string ID
        request.user_id,
        timestamp
    )
    return {"success": success}

@app.post("/api/place")
async def place_item(
    request: PlaceItemRequest,
    db: Session = Depends(get_db)
):
    success = search_service.update_item_location(
        db,
        request.itemId,
        request.userId,
        request.containerId,
        request.position.dict(),
        request.timestamp
    )
    return {"success": success}

@app.get("/api/waste/identify", response_model=WasteResponse)
async def identify_waste(db: Session = Depends(get_db)):
    waste_items = waste_service.identify_waste_items(db)
    return WasteResponse(success=True, wasteItems=waste_items)

@app.post("/api/waste/return-plan", response_model=ReturnPlanResponse)
async def get_return_plan(
    request: ReturnPlanRequest,
    db: Session = Depends(get_db)
):
    return_plan, retrieval_steps, manifest = waste_service.plan_waste_return(
        db,
        request
    )
    return ReturnPlanResponse(
        success=True,
        returnPlan=return_plan,
        retrievalSteps=retrieval_steps,
        returnManifest=manifest
    )

@app.post("/api/waste/complete-undocking")
async def complete_undocking(
    undockingContainerId: str,
    timestamp: datetime,
    db: Session = Depends(get_db)
):
    success = waste_service.complete_undocking(
        db,
        undockingContainerId,
        timestamp
    )
    return {"success": success}

@app.post("/api/simulate/day")
async def simulate_days(
    request: SimulationRequest,
    db: Session = Depends(get_db)
):
    return simulation_service.simulate_time(db, request)

@app.post("/api/import/items")
async def import_items(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    result = await CSVHandler.import_items(db, contents)
    db.commit()  # Ensure changes are committed
    return {
        "success": result.get("success", False),
        "itemsImported": result.get("itemsImported", 0),
        "errors": result.get("errors", []),
        "message": str(result)  # Add full result for debugging
    }

@app.post("/api/import/containers")
async def import_containers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    result = await CSVHandler.import_containers(db, contents)
    db.commit()  # Ensure changes are committed
    return result

@app.get("/api/export/arrangement")
async def export_arrangement(db: Session = Depends(get_db)):
    csv_content = CSVHandler.export_arrangement(db)
    return {"content": csv_content}

@app.get("/api/logs", response_model=LogResponse)
async def get_logs(
    startDate: datetime,
    endDate: datetime,
    itemId: Optional[str] = None,
    userId: Optional[str] = None,
    actionType: Optional[str] = Query(None, regex="^(placement|retrieval|rearrangement|disposal)$"),
    db: Session = Depends(get_db)
):
    return logging_service.get_logs(
        db,
        startDate,
        endDate,
        itemId,
        userId,
        actionType
    )