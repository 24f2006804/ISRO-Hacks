from typing import List, Dict, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import Item, Container
from ..schemas import WasteItem, ReturnPlanRequest, ReturnManifest, Position
from .logging import LoggingService

class WasteManagementService:
    def __init__(self):
        self.logging_service = LoggingService()

    def identify_waste_items(self, db: Session) -> List[WasteItem]:
        current_date = datetime.now(timezone.utc)
        waste_items = []

        # Query items that are expired or out of uses
        items = db.query(Item).filter(
            ((Item.expiry_date.isnot(None) & (Item.expiry_date <= current_date)) |
            (Item.usage_limit.isnot(None) & (Item.uses_remaining <= 0))) &
            (Item.is_waste == False)
        ).all()

        for item in items:
            # Create position model from JSON if it exists
            position = None
            if item.position:
                position = Position(
                    start_coordinates=item.position["startCoordinates"],
                    end_coordinates=item.position["endCoordinates"]
                )

            # Convert expiry_date to timezone-aware if needed
            if item.expiry_date and item.expiry_date.tzinfo is None:
                expiry_date = item.expiry_date.replace(tzinfo=timezone.utc)
            else:
                expiry_date = item.expiry_date

            waste_item = WasteItem(
                itemId=str(item.id),  # Ensure string format and use itemId alias
                name=item.name,
                reason="Expired" if expiry_date and expiry_date <= current_date else "Out of Uses",
                containerId=item.container_id or "unknown",  # Use containerId alias
                position=position or Position(
                    start_coordinates={"width": 0, "depth": 0, "height": 0},
                    end_coordinates={"width": 0, "depth": 0, "height": 0}
                )
            )
            waste_items.append(waste_item)

            # Mark item as waste in database
            item.is_waste = True
            db.add(item)

            # Log waste identification
            self.logging_service.add_log(
                db=db,
                user_id="system",
                action_type="disposal",
                item_id=item.id,
                details={
                    "reason": waste_item.reason,
                    "container": item.container_id,
                    "identified_at": current_date.isoformat()
                }
            )

        db.commit()
        return waste_items

    def plan_waste_return(
        self,
        db: Session,
        request: ReturnPlanRequest
    ) -> Tuple[List[dict], List[dict], ReturnManifest]:
        # Get all waste items
        waste_items = db.query(Item).filter(Item.is_waste == True).all()
        
        return_plan = []
        retrieval_steps = []
        total_volume = 0
        total_weight = 0
        return_items = []
        step_counter = 1

        # Sort waste items by their position - items closer to the container exit first
        waste_items.sort(
            key=lambda x: (
                x.position["startCoordinates"]["depth"],
                x.position["startCoordinates"]["height"]
            )
        )

        for item in waste_items:
            # Calculate item volume and check weight limit
            item_volume = item.width * item.depth * item.height
            if total_weight + item.mass > request.maxWeight:
                break

            # Add to return manifest
            return_items.append({
                "itemId": item.id,
                "name": item.name,
                "reason": "Expired" if item.expiry_date <= datetime.utcnow() else "Out of Uses"
            })

            # Add to return plan
            return_plan.append({
                "step": step_counter,
                "itemId": item.id,
                "itemName": item.name,
                "fromContainer": item.container_id,
                "toContainer": request.undockingContainerId
            })

            # Generate retrieval steps
            retrieval_steps.append({
                "step": step_counter,
                "action": "retrieve",
                "itemId": item.id,
                "itemName": item.name
            })

            total_volume += item_volume
            total_weight += item.mass
            step_counter += 1

        manifest = ReturnManifest(
            undockingContainerId=request.undockingContainerId,
            undockingDate=request.undockingDate,
            returnItems=return_items,
            totalVolume=total_volume,
            totalWeight=total_weight
        )

        return return_plan, retrieval_steps, manifest

    def complete_undocking(
        self,
        db: Session,
        undocking_container_id: str,
        timestamp: datetime
    ) -> bool:
        # Get all waste items in the undocking container
        items = db.query(Item).filter(
            Item.container_id == undocking_container_id,
            Item.is_waste == True
        ).all()

        # Delete waste items from database
        for item in items:
            # Log undocking disposal
            self.logging_service.add_log(
                db=db,
                user_id="system",
                action_type="disposal",
                item_id=item.id,
                details={
                    "undockingContainerId": undocking_container_id,
                    "timestamp": timestamp.isoformat()
                }
            )
            db.delete(item)

        db.commit()
        return True