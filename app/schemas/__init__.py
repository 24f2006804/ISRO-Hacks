from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Coordinates(BaseModel):
    width: float
    depth: float
    height: float

class Position(BaseModel):
    start_coordinates: Coordinates
    end_coordinates: Coordinates

    # For backward compatibility
    @property
    def startCoordinates(self) -> Dict:
        return self.start_coordinates.model_dump()

    @property
    def endCoordinates(self) -> Dict:
        return self.end_coordinates.model_dump()

class Item(BaseModel):
    item_id: str = Field(alias="itemId")
    name: str
    width: float
    depth: float
    height: float
    priority: int = Field(ge=0, le=100)
    expiry_date: Optional[datetime] = Field(None, alias="expiryDate")
    usage_limit: Optional[int] = Field(None, alias="usageLimit")
    preferred_zone: str = Field(alias="preferredZone")

class Container(BaseModel):
    container_id: str = Field(alias="containerId")
    zone: str
    width: float
    depth: float
    height: float

class PlacementStep(BaseModel):
    step: int
    action: str
    item_id: str = Field(alias="itemId")
    from_container: Optional[str] = Field(None, alias="fromContainer")
    from_position: Optional[Position] = Field(None, alias="fromPosition")
    to_container: str = Field(alias="toContainer")
    to_position: Position = Field(alias="toPosition")

class PlacementRequest(BaseModel):
    items: List[Item]
    containers: List[Container]

class ItemPlacement(BaseModel):
    item_id: str = Field(alias="itemId")
    container_id: str = Field(alias="containerId")
    position: Position

class PlacementResponse(BaseModel):
    success: bool
    placements: List[ItemPlacement]
    rearrangements: List[PlacementStep]

class RetrievalStep(BaseModel):
    step: int
    action: str
    item_id: str = Field(alias="itemId")
    item_name: str = Field(alias="itemName")

class SearchResponse(BaseModel):
    success: bool
    found: bool
    item: Optional[Dict] = None
    retrieval_steps: List[RetrievalStep] = Field(default_factory=list, alias="retrievalSteps")
    total_items: int = Field(alias="totalItems")
    active_items: int = Field(alias="activeItems")

class RetrievalRequest(BaseModel):
    item_id: str = Field(alias="itemId")
    user_id: str = Field(alias="userId")
    timestamp: datetime

class PlaceItemRequest(BaseModel):
    item_id: str = Field(alias="itemId")
    user_id: str = Field(alias="userId")
    timestamp: datetime
    container_id: str = Field(alias="containerId")
    position: Position

class WasteItem(BaseModel):
    itemId: str  # Changed from item_id to itemId
    name: str
    reason: str
    containerId: str  # Changed from container_id to containerId
    position: Position

class WasteResponse(BaseModel):
    success: bool
    waste_items: List[WasteItem] = Field(alias="wasteItems")

class ReturnPlanRequest(BaseModel):
    undocking_container_id: str = Field(alias="undockingContainerId")
    undocking_date: datetime = Field(alias="undockingDate")
    max_weight: float = Field(alias="maxWeight")

class ReturnManifest(BaseModel):
    undocking_container_id: str = Field(alias="undockingContainerId")
    undocking_date: datetime = Field(alias="undockingDate")
    return_items: List[Dict] = Field(alias="returnItems")
    total_volume: float = Field(alias="totalVolume")
    total_weight: float = Field(alias="totalWeight")

class ReturnPlanResponse(BaseModel):
    success: bool
    return_plan: List[Dict] = Field(alias="returnPlan")
    retrieval_steps: List[RetrievalStep] = Field(alias="retrievalSteps")
    return_manifest: ReturnManifest = Field(alias="returnManifest")

class SimulationRequest(BaseModel):
    num_of_days: Optional[int] = Field(None, alias="numOfDays")
    to_timestamp: Optional[datetime] = Field(None, alias="toTimestamp")
    items_to_be_used_per_day: List[Dict] = Field(alias="itemsToBeUsedPerDay")

class SimulationResponse(BaseModel):
    success: bool
    new_date: datetime = Field(alias="newDate")
    changes: Dict[str, List[Dict]]  # Using proper type hint

class LogEntry(BaseModel):
    timestamp: datetime
    user_id: str = Field(alias="userId")
    action_type: str = Field(alias="actionType")
    item_id: str = Field(alias="itemId")
    details: Dict

class LogResponse(BaseModel):
    logs: List[LogEntry]