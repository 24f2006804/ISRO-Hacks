from fastapi import HTTPException
from typing import Dict, Any
from datetime import datetime

class InventoryError(Exception):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

def handle_database_error(error: Exception) -> HTTPException:
    """Convert database errors to HTTP responses"""
    return HTTPException(
        status_code=500,
        detail=f"Database error: {str(error)}"
    )

def handle_validation_error(error: Exception) -> HTTPException:
    """Convert validation errors to HTTP responses"""
    return HTTPException(
        status_code=400,
        detail=f"Validation error: {str(error)}"
    )

def validate_container_space(width: float, depth: float, height: float) -> None:
    """Validate container dimensions"""
    if width <= 0 or depth <= 0 or height <= 0:
        raise InventoryError(
            "Invalid container dimensions",
            {"width": width, "depth": depth, "height": height}
        )

def validate_item_dimensions(
    item_width: float,
    item_depth: float,
    item_height: float,
    container_width: float,
    container_depth: float,
    container_height: float
) -> None:
    """Validate that item can fit in container"""
    if (item_width > container_width or
        item_depth > container_depth or
        item_height > container_height):
        raise InventoryError(
            "Item dimensions exceed container dimensions",
            {
                "item": {"width": item_width, "depth": item_depth, "height": item_height},
                "container": {"width": container_width, "depth": container_depth, "height": container_height}
            }
        )

def validate_position_in_container(
    position: Dict[str, Any],
    container_width: float,
    container_depth: float,
    container_height: float
) -> None:
    """Validate that position is within container bounds"""
    if (position["endCoordinates"]["width"] > container_width or
        position["endCoordinates"]["depth"] > container_depth or
        position["endCoordinates"]["height"] > container_height):
        raise InventoryError(
            "Position exceeds container bounds",
            {
                "position": position,
                "container": {
                    "width": container_width,
                    "depth": container_depth,
                    "height": container_height
                }
            }
        )

def validate_date_range(start_date: datetime, end_date: datetime) -> None:
    """Validate that date range is valid"""
    if start_date > end_date:
        raise InventoryError(
            "Invalid date range",
            {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat()
            }
        )

def validate_priority(priority: int) -> None:
    """Validate priority value"""
    if not 0 <= priority <= 100:
        raise InventoryError(
            "Priority must be between 0 and 100",
            {"priority": priority}
        )