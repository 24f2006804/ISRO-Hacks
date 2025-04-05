import pandas as pd
import logging
from typing import List, Dict
from io import StringIO
from sqlalchemy.orm import Session
from ..models import Item, Container
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class CSVHandler:
    @staticmethod
    async def import_items(db: Session, file_content: bytes) -> Dict:
        try:
            logger.info(f"Starting item import with session {id(db)}")
            df = pd.read_csv(StringIO(file_content.decode()))
            logger.info(f"CSV columns: {df.columns.tolist()}")
            logger.info(f"Number of rows: {len(df)}")
            
            items_imported = 0
            errors = []

            try:
                # Clear existing items
                count = db.query(Item).delete()
                logger.info(f"Deleted {count} existing items")
                db.flush()

                for index, row in df.iterrows():
                    try:
                        # Format item ID to ensure 3-digit format
                        raw_id = str(row['Item ID']).strip()
                        item_id = raw_id if raw_id.startswith('0') else raw_id.zfill(3)

                        # Convert expiry date string to datetime
                        expiry_date = None
                        if pd.notna(row['Expiry Date']):
                            expiry_date = datetime.fromisoformat(row['Expiry Date']).replace(tzinfo=timezone.utc)

                        # Create new item
                        item = Item(
                            itemId=item_id,
                            name=str(row['Name']).strip(),
                            width=float(row['Width']),
                            depth=float(row['Depth']),
                            height=float(row['Height']),
                            mass=float(row['Mass']),
                            priority=int(row['Priority']),
                            expiry_date=expiry_date,
                            usage_limit=int(row['Usage Limit']) if pd.notna(row['Usage Limit']) else None,
                            uses_remaining=int(row['Usage Limit']) if pd.notna(row['Usage Limit']) else None,
                            preferred_zone=str(row['Preferred Zone']).strip(),
                            is_waste=False
                        )
                        logger.info(f"Created item with ID: {item_id}")
                        
                        db.add(item)
                        db.flush()
                        items_imported += 1

                    except Exception as e:
                        logger.error(f"Error importing row {index + 1}: {str(e)}")
                        errors.append({
                            "row": index + 1,
                            "message": str(e)
                        })
                        continue

                db.commit()
                logger.info(f"Successfully imported {items_imported} items")

                return {
                    "success": True,
                    "itemsImported": items_imported,
                    "errors": errors
                }

            except Exception as e:
                logger.error(f"Transaction error: {str(e)}")
                db.rollback()
                return {
                    "success": False,
                    "itemsImported": 0,
                    "errors": [{"message": f"Transaction error: {str(e)}"}]
                }

        except Exception as e:
            logger.error(f"File processing error: {str(e)}")
            return {
                "success": False,
                "itemsImported": 0,
                "errors": [{"message": f"File processing error: {str(e)}"}]
            }

    @staticmethod
    async def import_containers(db: Session, file_content: bytes) -> Dict:
        try:
            logger.info("Starting container import")
            df = pd.read_csv(StringIO(file_content.decode()))
            
            containers_imported = 0
            errors = []

            try:
                # Clear existing containers
                db.query(Container).delete()
                db.flush()

                for index, row in df.iterrows():
                    try:
                        # Format container ID (cont + uppercase letter)
                        raw_id = str(row['Container ID']).strip()
                        if not raw_id.startswith('cont'):
                            container_id = f"cont{chr(65 + containers_imported)}"  # A, B, C, etc.
                        else:
                            container_id = raw_id

                        container = Container(
                            id=container_id,
                            zone=row['Zone'],
                            width=float(row['Width']),
                            depth=float(row['Depth']),
                            height=float(row['Height'])
                        )
                        logger.info(f"Created container: {container_id}")
                        
                        db.add(container)
                        db.flush()
                        containers_imported += 1

                    except Exception as e:
                        logger.error(f"Error importing row {index + 1}: {str(e)}")
                        errors.append({
                            "row": index + 1,
                            "message": str(e)
                        })
                        continue

                db.commit()
                logger.info(f"Successfully imported {containers_imported} containers")

            except Exception as e:
                logger.error(f"Transaction error: {str(e)}")
                db.rollback()
                return {
                    "success": False,
                    "containersImported": 0,
                    "errors": [{"message": f"Transaction error: {str(e)}"}]
                }

            return {
                "success": True,
                "containersImported": containers_imported,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"File processing error: {str(e)}")
            return {
                "success": False,
                "containersImported": 0,
                "errors": [{"message": f"File processing error: {str(e)}"}]
            }

    @staticmethod
    def export_arrangement(db: Session) -> str:
        # Query all items with their positions
        items = db.query(Item).filter(Item.container_id.isnot(None)).all()
        
        # Prepare data for CSV
        rows = []
        for item in items:
            if item.position:
                position_str = (
                    f"({item.position['startCoordinates']['width']},"
                    f"{item.position['startCoordinates']['depth']},"
                    f"{item.position['startCoordinates']['height']}),"
                    f"({item.position['endCoordinates']['width']},"
                    f"{item.position['endCoordinates']['depth']},"
                    f"{item.position['endCoordinates']['height']})"
                )
                rows.append({
                    'Item ID': item.id,
                    'Container ID': item.container_id,
                    'Coordinates': position_str
                })
        
        # Convert to DataFrame and then to CSV
        df = pd.DataFrame(rows)
        return df.to_csv(index=False)