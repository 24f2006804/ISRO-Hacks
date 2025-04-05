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
        
        # Sort waste items by priority (higher priority items returned first)
        waste_items.sort(key=lambda x: (-x.priority, x.expiry_date or datetime.max))
        
        return_plan = []
        retrieval_steps = []
        total_volume = 0
        total_weight = 0
        return_items = []
        step_counter = 1

        # Get undocking container dimensions
        undocking_container = db.query(Container).filter(
            Container.id == request.undockingContainerId
        ).first()
        
        if not undocking_container:
            raise InventoryError("Undocking container not found")

        # Calculate available space in undocking container
        available_space = undocking_container.width * undocking_container.depth * undocking_container.height

        for item in waste_items:
            # Calculate item volume and check constraints
            item_volume = item.width * item.depth * item.height
            
            # Check if item fits within remaining weight and volume limits
            if (total_weight + item.mass > request.maxWeight or
                total_volume + item_volume > available_space):
                continue

            # Add to return manifest
            return_items.append({
                "itemId": item.id,
                "name": item.name,
                "mass": item.mass,
                "volume": item_volume,
                "reason": "Expired" if (item.expiry_date and item.expiry_date <= datetime.now(timezone.utc)) 
                         else "Out of Uses"
            })

            # Generate retrieval steps if item is currently in a container
            if item.container_id and item.container_id != request.undockingContainerId:
                # Get blocking items that need to be moved
                blocking_items = self._find_blocking_items(db, item)
                
                # Add steps to move blocking items
                for blocking_item in blocking_items:
                    retrieval_steps.append({
                        "step": step_counter,
                        "action": "move",
                        "itemId": blocking_item.id,
                        "itemName": blocking_item.name,
                        "fromContainer": item.container_id,
                        "toContainer": "temporary"
                    })
                    step_counter += 1

                # Add step to move waste item to undocking container
                retrieval_steps.append({
                    "step": step_counter,
                    "action": "move",
                    "itemId": item.id,
                    "itemName": item.name,
                    "fromContainer": item.container_id,
                    "toContainer": request.undockingContainerId
                })
                step_counter += 1

                # Add steps to return blocking items
                for blocking_item in reversed(blocking_items):
                    retrieval_steps.append({
                        "step": step_counter,
                        "action": "move",
                        "itemId": blocking_item.id,
                        "itemName": blocking_item.name,
                        "fromContainer": "temporary",
                        "toContainer": item.container_id
                    })
                    step_counter += 1

                # Add to return plan
                return_plan.append({
                    "step": step_counter,
                    "itemId": item.id,
                    "itemName": item.name,
                    "fromContainer": item.container_id,
                    "toContainer": request.undockingContainerId,
                    "mass": item.mass,
                    "volume": item_volume
                })
                step_counter += 1

            total_volume += item_volume
            total_weight += item.mass

        manifest = ReturnManifest(
            undockingContainerId=request.undockingContainerId,
            undockingDate=request.undockingDate,
            returnItems=return_items,
            totalVolume=total_volume,
            totalWeight=total_weight
        )

        return return_plan, retrieval_steps, manifest

    def _find_blocking_items(self, db: Session, target_item: Item) -> List[Item]:
        """Find items that need to be moved to access the target item"""
        blocking_items = []
        
        if not target_item.container_id or not target_item.position:
            return blocking_items

        # Get all items in the same container
        container_items = db.query(Item).filter(
            Item.container_id == target_item.container_id,
            Item.id != target_item.id,
            Item.is_waste == False
        ).all()

        target_pos = target_item.position
        for item in container_items:
            if not item.position:
                continue

            # Check if item blocks access to target
            if (item.position["startCoordinates"]["depth"] < target_pos["startCoordinates"]["depth"] and
                self._check_path_blocked(item.position, target_pos)):
                blocking_items.append(item)

        # Sort by position (items closer to the front first)
        blocking_items.sort(key=lambda x: x.position["startCoordinates"]["depth"])
        return blocking_items

    def _check_path_blocked(self, blocking_pos: Dict, target_pos: Dict) -> bool:
        """Check if an item blocks the retrieval path"""
        return (blocking_pos["startCoordinates"]["width"] < target_pos["endCoordinates"]["width"] and
                blocking_pos["endCoordinates"]["width"] > target_pos["startCoordinates"]["width"] and
                blocking_pos["startCoordinates"]["height"] < target_pos["endCoordinates"]["height"] and
                blocking_pos["endCoordinates"]["height"] > target_pos["startCoordinates"]["height"])

    def complete_undocking(
        self,
        db: Session,
        undocking_container_id: str,
        timestamp: datetime
    ) -> bool:
        try:
            # Get all waste items in the undocking container
            items = db.query(Item).filter(
                Item.container_id == undocking_container_id,
                Item.is_waste == True
            ).all()

            # Calculate total values for logging
            total_items = len(items)
            total_mass = sum(item.mass for item in items)
            total_volume = sum(item.width * item.depth * item.height for item in items)

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
                        "timestamp": timestamp.isoformat(),
                        "disposalType": "undocking",
                        "totalItems": total_items,
                        "totalMass": total_mass,
                        "totalVolume": total_volume
                    }
                )
                db.delete(item)

            # Clear container references
            db.query(Item).filter(
                Item.container_id == undocking_container_id
            ).update({"container_id": None, "position": None})

            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error completing undocking: {str(e)}")
            db.rollback()
            return False