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
        self,  # Add self parameter
        db: Session,
        item_id: Optional[str] = None,
        item_name: Optional[str] = None
    ) -> Dict[str, Any]:
        query = db.query(Item)
        if item_id:
            # Check if item exists before filtering
            all_items = query.all()
            logger.info(f"All items in db: {[(item.id, item.name) for item in all_items]}")
            
            query = query.filter(Item.id == str(item_id))
            logger.info(f"Searching for item with ID: {item_id}")
            item = query.first()
            logger.info(f"Found item: {item.id if item else None}")
        elif item_name:
            item = query.filter(Item.name == item_name).first()
        else:
            return {
                "success": True,
                "found": False,
                "totalItems": db.query(func.count(Item.id)).scalar() or 0,
                "activeItems": db.query(func.count(Item.id)).filter(Item.is_waste == False).scalar() or 0
            }

        if not item:
            return {
                "success": True,
                "found": False,
                "totalItems": db.query(func.count(Item.id)).scalar() or 0,
                "activeItems": db.query(func.count(Item.id)).filter(Item.is_waste == False).scalar() or 0
            }

        # Generate item details
        item_details = {
            "itemId": str(item.id),
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
            "totalItems": db.query(func.count(Item.id)).scalar() or 0,
            "activeItems": db.query(func.count(Item.id)).filter(Item.is_waste == False).scalar() or 0
        }

    def _calculate_retrieval_steps(
        self,
        db: Session,
        target_item: Item
    ) -> List[RetrievalStep]:
        steps = []
        step_counter = 1

        if not target_item.position:
            return steps

        # Find items that need to be moved to access the target item
        blocking_items = self._find_blocking_items(db, target_item)

        # Generate steps for moving blocking items
        for blocking_item in blocking_items:
            # Add step to remove blocking item
            steps.append(RetrievalStep(
                step=step_counter,
                action="remove",
                itemId=blocking_item.id,
                itemName=blocking_item.name
            ))
            step_counter += 1

            # Add step to set aside blocking item
            steps.append(RetrievalStep(
                step=step_counter,
                action="setAside",
                itemId=blocking_item.id,
                itemName=blocking_item.name
            ))
            step_counter += 1

        # Add step to retrieve target item
        steps.append(RetrievalStep(
            step=step_counter,
            action="retrieve",
            itemId=target_item.id,
            itemName=target_item.name
        ))
        step_counter += 1

        # Add steps to place back blocking items in reverse order
        for blocking_item in reversed(blocking_items):
            steps.append(RetrievalStep(
                step=step_counter,
                action="placeBack",
                itemId=blocking_item.id,
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
            Item.id != target_item.id
        ).all()

        target_pos = target_item.position
        target_depth = target_pos["startCoordinates"]["depth"]

        # Find items that block access to the target item
        for item in container_items:
            if not item.position:
                continue

            item_pos = item.position
            item_depth = item_pos["startCoordinates"]["depth"]

            # Check if item is in front of target item
            if item_depth < target_depth:
                # Check if item overlaps with target item's access path
                if self._check_path_overlap(item_pos, target_pos):
                    blocking_items.append(item)

        # Sort blocking items by their depth (items closer to the opening first)
        blocking_items.sort(
            key=lambda x: x.position["startCoordinates"]["depth"]
        )

        return blocking_items

    def _check_path_overlap(
        self,
        item_pos: Dict,
        target_pos: Dict
    ) -> bool:
        """Check if an item blocks the access path to the target item"""
        # Check if there's any overlap in the width and height dimensions
        return not (
            item_pos["endCoordinates"]["width"] <= target_pos["startCoordinates"]["width"] or
            item_pos["startCoordinates"]["width"] >= target_pos["endCoordinates"]["width"] or
            item_pos["endCoordinates"]["height"] <= target_pos["startCoordinates"]["height"] or
            item_pos["startCoordinates"]["height"] >= target_pos["endCoordinates"]["height"]
        )

    def log_retrieval(
        self,
        db: Session,
        item_id: str,
        user_id: str,
        timestamp: datetime
    ) -> bool:
        item = db.query(Item).filter(Item.id == item_id).first()
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
        item = db.query(Item).filter(Item.id == item_id).first()
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