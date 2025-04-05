from typing import List, Optional, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..models import Log
from ..schemas import LogResponse, LogEntry

class LoggingService:
    def add_log(
        self,
        db: Session,
        user_id: str,
        action_type: str,
        item_id: str,
        details: Dict = None
    ) -> bool:
        try:
            log_entry = Log(
                timestamp=datetime.now(timezone.utc),
                user_id=user_id,
                action_type=action_type,
                item_id=item_id,  # This now references Item.itemId
                details=details
            )
            db.add(log_entry)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            return False

    def get_logs(
        self,
        db: Session,
        start_date: datetime,
        end_date: datetime,
        item_id: str = None,
        user_id: str = None,
        action_type: str = None
    ) -> Dict[str, List[Dict]]:
        # Ensure dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
            
        query = db.query(Log)
        
        # Apply date range filter
        query = query.filter(and_(
            Log.timestamp >= start_date,
            Log.timestamp <= end_date
        ))
        
        # Apply optional filters
        if item_id:
            query = query.filter(Log.item_id == item_id)
        if user_id:
            query = query.filter(Log.user_id == user_id)
        if action_type:
            query = query.filter(Log.action_type == action_type)
            
        # Order by timestamp
        query = query.order_by(Log.timestamp)
        
        # Convert to response format
        logs = query.all()
        
        return {
            "logs": [
                {
                    "timestamp": log.timestamp.isoformat(),
                    "userId": log.user_id,
                    "actionType": log.action_type,
                    "itemId": log.item_id,
                    "details": log.details or {}
                }
                for log in logs
            ]
        }