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

            # Handle transaction manually
            try:
                # Clear existing items
                count = db.query(Item).delete()
                logger.info(f"Deleted {count} existing items")
                db.flush()
                
                # Debug: Check session state
                logger.info(f"Session dirty after delete: {db.dirty}")
                logger.info(f"Session new after delete: {db.new}")

                for index, row in df.iterrows():
                    try:
                        # Convert expiry date string to datetime
                        expiry_date = None
                        if pd.notna(row['Expiry Date']):
                            expiry_date = datetime.fromisoformat(row['Expiry Date']).replace(tzinfo=timezone.utc)
                            logger.info(f"Parsed expiry date: {expiry_date}")

                        # Preserve original item ID format
                        item_id = str(row['Item ID']).strip()
                        if not item_id.startswith('0'):  # If it's not already zero-padded
                            item_id = item_id.zfill(3)  # Ensure 3-digit format with leading zeros

                        # Create new item
                        item = Item(
                            id=item_id,  # Use properly formatted ID
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
                        logger.info(f"Created item object: {item.id}, {item.name}")
                        
                        db.add(item)
                        logger.info(f"Added item to session, session state: new={len(db.new)}, dirty={len(db.dirty)}")
                        db.flush()
                        items_imported += 1

                    except Exception as e:
                        logger.error(f"Error importing row {index + 1}: {str(e)}")
                        errors.append({
                            "row": index + 1,
                            "message": str(e)
                        })
                        continue

                # Verify items before commit
                pending_items = db.query(Item).all()
                logger.info(f"Items in session before commit: {[(i.id, i.name) for i in pending_items]}")
                
                # Commit transaction
                db.commit()
                logger.info(f"Committed transaction, imported {items_imported} items")
                
                # Verify after commit
                final_items = db.query(Item).all()
                logger.info(f"Items in database after commit: {[(i.id, i.name) for i in final_items]}")

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
            logger.info(f"Read CSV with columns: {df.columns.tolist()}")
            logger.info(f"First row: {df.iloc[0].to_dict()}")
            
            containers_imported = 0
            errors = []

            # Handle transaction manually
            try:
                # Clear existing containers
                db.query(Container).delete()
                db.flush()  # Ensure deletion is processed

                for index, row in df.iterrows():
                    try:
                        container = Container(
                            id=str(row['Container ID']),
                            zone=row['Zone'],
                            width=float(row['Width']),
                            depth=float(row['Depth']),
                            height=float(row['Height'])
                        )
                        logger.info(f"Created container: id={container.id}, zone={container.zone}")
                        
                        db.add(container)
                        db.flush()  # Ensure container is processed
                        containers_imported += 1

                    except Exception as e:
                        logger.error(f"Error importing row {index + 1}: {str(e)}")
                        errors.append({
                            "row": index + 1,
                            "message": str(e)
                        })
                        continue  # Continue with next row

                # Commit all changes
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