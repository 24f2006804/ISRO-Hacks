from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import Item, Container
from ..schemas import SearchResponse, RetrievalStep
from .logging import LoggingService
import logging

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.logging_service = LoggingService()

    def search_item(
        self,
        db: Session,
        item_id: Optional[str] = None,
        item_name: Optional[str] = None
    ) -> Dict[str, Any]:
        query = db.query(Item)
        search_result = None
        
        if item_id:
            # Check if item exists before filtering
            all_items = query.all()
            logger.info(f"All items in db: {[(item.itemId, item.name) for item in all_items]}")
            
            query = query.filter(Item.itemId == str(item_id))
            logger.info(f"Searching for item with ID: {item_id}")
            search_result = query.first()
            logger.info(f"Found item: {search_result.itemId if search_result else None}")
        elif item_name:
            search_result = query.filter(Item.name == item_name).first()

        # Log the search activity
        self.logging_service.add_log(
            db=db,
            user_id="system",  # Replace with actual user ID when authentication is implemented
            action_type="search",
            item_id=search_result.itemId if search_result else None,
            details={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "searchType": "id" if item_id else "name",
                "searchTerm": item_id or item_name,
                "found": bool(search_result)
            }
        )

        if not search_result:
            return {
                "success": True,
                "found": False,
                "totalItems": db.query(func.count(Item.itemId)).scalar() or 0,
                "activeItems": db.query(func.count(Item.itemId)).filter(Item.is_waste == False).scalar() or 0
            }

        # Generate item details
        item_details = {
            "itemId": str(search_result.itemId),
            "name": search_result.name,
            "containerId": search_result.container_id,
            "width": search_result.width,
            "depth": search_result.depth,
            "height": search_result.height,
            "mass": search_result.mass,
            "priority": search_result.priority,
            "expiryDate": search_result.expiry_date.isoformat() if search_result.expiry_date else None,
            "usageLimit": search_result.usage_limit,
            "usesRemaining": search_result.uses_remaining,
            "preferredZone": search_result.preferred_zone,
            "zone": search_result.container.zone if search_result.container else None,
            "position": search_result.position,
            "isWaste": search_result.is_waste  # Include waste status
        }

        # Determine status for waste items
        if search_result.is_waste:
            # Convert expiry_date to timezone-aware if needed
            if search_result.expiry_date and search_result.expiry_date.tzinfo is None:
                expiry_date = search_result.expiry_date.replace(tzinfo=timezone.utc)
            else:
                expiry_date = search_result.expiry_date

            if search_result.uses_remaining == 0:
                item_details["status"] = "Used"
            elif expiry_date and expiry_date <= datetime.now(timezone.utc):
                item_details["status"] = "Expired"
            else:
                item_details["status"] = "Waste"
        else:
            item_details["status"] = "Active"

        # Calculate retrieval steps
        retrieval_steps = self._calculate_retrieval_steps(db, search_result)

        return {
            "success": True,
            "found": True,
            "item": item_details,
            "retrievalSteps": retrieval_steps,
            "totalItems": db.query(func.count(Item.itemId)).scalar() or 0,
            "activeItems": db.query(func.count(Item.itemId)).filter(Item.is_waste == False).scalar() or 0
        }

    def _calculate_retrieval_steps(
        self,
        db: Session,
        target_item: Item
    ) -> List[RetrievalStep]:
        steps = []
        step_counter = 1

        if not target_item.position or not target_item.container_id:
            return steps

        # Find items blocking direct perpendicular access
        blocking_items = self._find_blocking_items(db, target_item)
        
        # Sort blocking items by priority (lower priority items moved first)
        blocking_items.sort(key=lambda x: x.priority)

        # Generate steps for moving blocking items
        for blocking_item in blocking_items:
            # Add step to remove blocking item
            steps.append(RetrievalStep(
                step=step_counter,
                action="remove",
                itemId=blocking_item.itemId,
                itemName=blocking_item.name
            ))
            step_counter += 1

        # Add step to retrieve target item
        steps.append(RetrievalStep(
            step=step_counter,
            action="retrieve",
            itemId=target_item.itemId,
            itemName=target_item.name
        ))
        step_counter += 1

        # Add steps to place back blocking items in reverse order (higher priority items placed first)
        for blocking_item in reversed(blocking_items):
            steps.append(RetrievalStep(
                step=step_counter,
                action="place",
                itemId=blocking_item.itemId,
                itemName=blocking_item.name
            ))
            step_counter += 1

        return steps

    def _find_blocking_items(
        self,
        db: Session,
        target_item: Item
    ) -> List[Item]:
        """Find items that need to be moved to retrieve the target item"""
        if not target_item.position or not target_item.container_id:
            return []

        # Get all items in the same container
        blocking_items = []
        container_items = db.query(Item).filter(
            Item.container_id == target_item.container_id,
            Item.itemId != target_item.itemId,
            Item.is_waste == False  # Exclude waste items
        ).all()

        target_position = target_item.position
        target_front_access = float(target_position["startCoordinates"]["depth"])
        
        for item in container_items:
            if not item.position:
                continue

            item_position = item.position
            item_depth = float(item_position["startCoordinates"]["depth"])
            
            # Check if item is in front of target item
            if item_depth < target_front_access:
                # Check if there's overlap in width and height
                width_overlap = (
                    float(item_position["endCoordinates"]["width"]) > float(target_position["startCoordinates"]["width"]) and
                    float(item_position["startCoordinates"]["width"]) < float(target_position["endCoordinates"]["width"])
                )
                height_overlap = (
                    float(item_position["endCoordinates"]["height"]) > float(target_position["startCoordinates"]["height"]) and
                    float(target_position["startCoordinates"]["height"]) < float(target_position["endCoordinates"]["height"])
                )
                
                if width_overlap and height_overlap:
                    blocking_items.append(item)

        # Sort blocking items by their depth (front to back)
        blocking_items.sort(key=lambda x: float(x.position["startCoordinates"]["depth"]))
        return blocking_items

    def _check_perpendicular_overlap(
        self,
        target_start: Dict,
        target_end: Dict,
        item_start: Dict,
        item_end: Dict
    ) -> bool:
        """Check if an item blocks the perpendicular access path of the target item"""
        return not (
            item_end["width"] <= target_start["width"] or
            item_start["width"] >= target_end["width"] or
            item_end["height"] <= target_start["height"] or
            item_start["height"] >= target_end["height"]
        )

    def log_retrieval(
        self,
        db: Session,
        item_id: str,
        user_id: str,
        timestamp: datetime
    ) -> bool:
        item = db.query(Item).filter(Item.itemId == item_id).first()
        if not item:
            return False

        # Update usage count if applicable
        if item.usage_limit is not None:
            old_uses = item.uses_remaining
            item.uses_remaining = max(0, item.uses_remaining - 1)
            
            # Log item usage
            self.logging_service.add_log(
                db=db,
                user_id=user_id,
                action_type="retrieval",
                item_id=item_id,
                details={
                    "timestamp": timestamp.isoformat(),
                    "oldUsesRemaining": old_uses,
                    "newUsesRemaining": item.uses_remaining
                }
            )

            # Check if item became waste
            if item.uses_remaining == 0:
                item.is_waste = True
                self.logging_service.add_log(
                    db=db,
                    user_id=user_id,
                    action_type="disposal",
                    item_id=item_id,
                    details={
                        "reason": "Out of Uses",
                        "timestamp": timestamp.isoformat()
                    }
                )

        db.commit()
        return True

    def update_item_location(
        self,
        db: Session,
        item_id: str,
        user_id: str,
        container_id: str,
        position: Dict,
        timestamp: datetime
    ) -> bool:
        item = db.query(Item).filter(Item.itemId == item_id).first()
        if not item:
            return False

        old_container = item.container_id
        old_position = item.position

        # Update item location
        item.container_id = container_id
        item.position = position

        # Log location change
        self.logging_service.add_log(
            db=db,
            user_id=user_id,
            action_type="placement",
            item_id=item_id,
            details={
                "timestamp": timestamp.isoformat(),
                "oldContainer": old_container,
                "newContainer": container_id,
                "oldPosition": old_position,
                "newPosition": position
            }
        )

        db.commit()
        return True