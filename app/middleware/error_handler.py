from fastapi import Request
from fastapi.responses import JSONResponse
from ..utils.error_handling import InventoryError
from sqlalchemy.exc import SQLAlchemyError
from typing import Callable
import logging

logger = logging.getLogger(__name__)

async def error_handler_middleware(request: Request, call_next: Callable):
    try:
        return await call_next(request)
    except InventoryError as e:
        logger.error(f"Inventory error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=400,
            content={
                "error": "Inventory Error",
                "message": str(e),
                "details": e.details
            }
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Database Error",
                "message": "An error occurred while accessing the database"
            }
        )
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred"
            }
        )