import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional
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

                        # Convert expiry date string to timezone-aware datetime
                        expiry_date = None
                        if pd.notna(row['Expiry Date']):
                            try:
                                # Try parsing as ISO format first
                                expiry_date = datetime.fromisoformat(row['Expiry Date'])
                            except ValueError:
                                # Fall back to parsing common date formats
                                expiry_date = datetime.strptime(str(row['Expiry Date']), '%Y-%m-%d')
                            
                            # Ensure timezone awareness
                            if expiry_date.tzinfo is None:
                                expiry_date = expiry_date.replace(
                                    hour=23, minute=59, second=59,  # Set to end of day
                                    tzinfo=timezone.utc
                                )

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
    def verify_arrangement(item_id: str, container_id: str, position: dict) -> Tuple[bool, Optional[str]]:
        """Verify if an item's position matches the arrangement in the CSV file"""
        try:
            with open("/home/agnij/Downloads/arrangement_2025-04-04.csv", "r") as f:
                lines = f.readlines()[1:]  # Skip header
                for line in lines:
                    csv_item_id, csv_container_id, coords = line.strip().split(",")
                    if csv_item_id == item_id:
                        # Remove quotes and parentheses from coordinates
                        coords = coords.strip('"()')
                        try:
                            start_coords, end_coords = coords.split("),(")
                            csv_start = tuple(map(float, start_coords.split(",")))
                            csv_end = tuple(map(float, end_coords.split(",")))
                            
                            # Check container match
                            if csv_container_id != container_id:
                                return False, f"Container mismatch: expected {csv_container_id}, found {container_id}"
                            
                            # Check coordinate matches with tolerance
                            tolerance = 0.1
                            if (abs(float(position["startCoordinates"]["width"]) - csv_start[0]) > tolerance or
                                abs(float(position["startCoordinates"]["depth"]) - csv_start[1]) > tolerance or
                                abs(float(position["startCoordinates"]["height"]) - csv_start[2]) > tolerance or
                                abs(float(position["endCoordinates"]["width"]) - csv_end[0]) > tolerance or
                                abs(float(position["endCoordinates"]["depth"]) - csv_end[1]) > tolerance or
                                abs(float(position["endCoordinates"]["height"]) - csv_end[2]) > tolerance):
                                return False, "Position coordinates do not match expected values"
                            
                            return True, None
                        except (ValueError, IndexError) as e:
                            return False, f"Invalid coordinate format in CSV: {str(e)}"
                        
                return False, f"Item {item_id} not found in arrangement CSV"
            
        except FileNotFoundError:
            return False, "Arrangement CSV file not found"
        except Exception as e:
            logger.error(f"Error verifying arrangement: {str(e)}")
            return False, f"Error verifying arrangement: {str(e)}"

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