from datetime import datetime, timezone, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from ..models import Item
from ..schemas import SimulationRequest, SimulationResponse
from .logging import LoggingService

class SimulationService:
    def __init__(self):
        self.logging_service = LoggingService()

    def simulate_time(
        self,
        db: Session,
        request: SimulationRequest
    ) -> SimulationResponse:
        current_date = datetime.now(timezone.utc)
        target_date = None

        if request.num_of_days:
            target_date = current_date + timedelta(days=request.num_of_days)
        elif request.to_timestamp:
            target_date = request.to_timestamp
        else:
            raise ValueError("Either num_of_days or to_timestamp must be provided")

        changes = {
            "itemsUsedToday": [],
            "itemsDepletedToday": [],
            "itemsExpiredToday": []
        }

        # Process daily item usage
        for item_usage in request.items_to_be_used_per_day:
            item_id = item_usage.get("itemId")
            if not item_id:
                continue

            item = db.query(Item).filter(Item.id == str(item_id)).first()
            if not item or item.is_waste:
                continue

            # Calculate total uses (one use per day)
            total_uses = request.num_of_days
            if item.usage_limit is not None and item.uses_remaining is not None:
                old_uses = item.uses_remaining
                item.uses_remaining = max(0, old_uses - total_uses)

                # Record usage in changes
                changes["itemsUsedToday"].append({
                    "itemId": item.id,
                    "name": item.name,
                    "remainingUses": item.uses_remaining,
                    "usesConsumed": min(total_uses, old_uses)  # Don't report more uses than available
                })

                # Check if item was depleted during simulation
                if item.uses_remaining == 0 and old_uses > 0:
                    changes["itemsDepletedToday"].append({
                        "itemId": item.id,
                        "name": item.name,
                        "depleted_at": (current_date + timedelta(days=old_uses)).isoformat()
                    })
                    item.is_waste = True

                    # Log depletion
                    self.logging_service.add_log(
                        db=db,
                        user_id="simulation",
                        action_type="disposal",
                        item_id=item.id,
                        details={
                            "reason": "Out of Uses",
                            "simulatedDate": target_date.isoformat(),
                            "originalUses": old_uses,
                            "depleted_at": (current_date + timedelta(days=old_uses)).isoformat()
                        }
                    )

                # Log each day's usage separately
                for day in range(min(total_uses, old_uses)):
                    usage_date = current_date + timedelta(days=day)
                    self.logging_service.add_log(
                        db=db,
                        user_id="simulation",
                        action_type="retrieval",
                        item_id=item.id,
                        details={
                            "simulatedDate": usage_date.isoformat(),
                            "oldUsesRemaining": old_uses - day,
                            "newUsesRemaining": old_uses - day - 1,
                            "simulated": True
                        }
                    )

        # Check for expired items
        expired_items = db.query(Item).filter(
            Item.expiry_date <= target_date,
            Item.is_waste == False
        ).all()

        for item in expired_items:
            changes["itemsExpiredToday"].append({
                "itemId": item.id,
                "name": item.name,
                "expiryDate": item.expiry_date.isoformat()
            })
            item.is_waste = True

            # Log expiration
            self.logging_service.add_log(
                db=db,
                user_id="simulation",
                action_type="disposal",
                item_id=item.id,
                details={
                    "reason": "Expired",
                    "expiryDate": item.expiry_date.isoformat(),
                    "simulatedDate": target_date.isoformat()
                }
            )

        db.commit()

        return SimulationResponse(
            success=True,
            newDate=target_date,
            changes=changes
        )