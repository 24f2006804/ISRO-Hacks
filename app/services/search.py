from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
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
        if item_id:
            # Check if item exists before filtering
            all_items = query.all()
            logger.info(f"All items in db: {[(item.itemId, item.name) for item in all_items]}")
            
            query = query.filter(Item.itemId == str(item_id))
            logger.info(f"Searching for item with ID: {item_id}")
            item = query.first()
            logger.info(f"Found item: {item.itemId if item else None}")
        elif item_name:
            item = query.filter(Item.name == item_name).first()
        else:
            return {
                "success": True,
                "found": False,
                "totalItems": db.query(func.count(Item.itemId)).scalar() or 0,
                "activeItems": db.query(func.count(Item.itemId)).filter(Item.is_waste == False).scalar() or 0
            }

        if not item:
            return {
                "success": True,
                "found": False,
                "totalItems": db.query(func.count(Item.itemId)).scalar() or 0,
                "activeItems": db.query(func.count(Item.itemId)).filter(Item.is_waste == False).scalar() or 0
            }

        # Generate item details
        item_details = {
            "itemId": str(item.itemId),
            "name": item.name,
            "containerId": item.container_id,
            "width": item.width,
            "depth": item.depth,
            "height": item.height,
            "mass": item.mass,
            "priority": item.priority,
            "expiryDate": item.expiry_date.isoformat() if item.expiry_date else None,
            "usageLimit": item.usage_limit,
            "usesRemaining": item.uses_remaining,
            "preferredZone": item.preferred_zone,
            "zone": item.container.zone if item.container else None,
            "position": item.position
        }

        # Calculate retrieval steps
        retrieval_steps = self._calculate_retrieval_steps(db, item)

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
        blocking_items = []
        if not target_item.container_id or not target_item.position:
            return blocking_items

        # Get all items in the same container
        container_items = db.query(Item).filter(
            Item.container_id == target_item.container_id,
            Item.itemId != target_item.itemId,
            Item.is_waste == False  # Ignore waste items
        ).all()

        target_pos = target_item.position
        target_start = target_pos["startCoordinates"]
        target_end = target_pos["endCoordinates"]

        # Check items that block perpendicular access path
        for item in container_items:
            if not item.position:
                continue

            item_pos = item.position
            item_start = item_pos["startCoordinates"]
            item_end = item_pos["endCoordinates"]

            # Check if item blocks perpendicular access path
            # An item blocks if it overlaps with the target item's projection to the container opening
            if (item_start["depth"] < target_start["depth"] and  # Item is closer to opening
                self._check_perpendicular_overlap(
                    target_start, target_end,
                    item_start, item_end
                )):
                blocking_items.append(item)

        # Sort by distance from opening (closest first) and priority (lower priority first)
        blocking_items.sort(key=lambda x: (
            x.position["startCoordinates"]["depth"],
            x.priority
        ))

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