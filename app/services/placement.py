from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
import logging
import traceback
from ..models import Item, Container
from ..schemas import Position, PlacementStep, ItemPlacement, Coordinates
from ..utils.error_handling import InventoryError

logger = logging.getLogger(__name__)

class PlacementService:
    def __init__(self):
        self.container_states: Dict[str, List[Dict]] = {}
        self.space_utilization: Dict[str, float] = {}

    def optimize_placement(
        self,
        items: List[Dict[str, Any]] | List[Item],
        containers: List[Dict[str, Any]] | List[Container]
    ) -> Tuple[List[ItemPlacement], List[PlacementStep]]:
        try:
            logger.info(f"Starting placement optimization for {len(items)} items")
            
            # Initialize space utilization tracking
            self._init_space_utilization(containers)
            
            # Convert and sort items by priority, expiry date, and volume
            sorted_items = self._prepare_items(items)
            container_models = self._prepare_containers(containers)
            
            placements = []
            rearrangements = []
            
            for item in sorted_items:
                placement = self._attempt_placement(item, container_models)
                
                if not placement:
                    # Try rearrangement with space optimization
                    success, new_placement, steps = self._optimize_rearrangement(item, container_models)
                    if success:
                        rearrangements.extend(steps)
                        placements.append(new_placement)
                        self._update_container_state(new_placement)
                        self._update_space_utilization(new_placement)
                else:
                    placements.append(placement)
                    self._update_container_state(placement)
                    self._update_space_utilization(placement)

            return placements, rearrangements
            
        except Exception as e:
            logger.error(f"Error in placement optimization: {traceback.format_exc()}")
            raise InventoryError(f"Placement optimization failed: {str(e)}")

    def _prepare_items(self, items: List[Any]) -> List[Item]:
        """Convert and sort items by priority, expiry date, and volume"""
        item_models = []
        for item in items:
            if isinstance(item, dict):
                item_data = {
                    "itemId": item["itemId"],
                    "name": item["name"],
                    "width": float(item["width"]),
                    "depth": float(item["depth"]),
                    "height": float(item["height"]),
                    "mass": item.get("mass", 1.0),
                    "priority": int(item["priority"]),
                    "preferred_zone": item["preferredZone"]
                }
                item_models.append(Item(**item_data))
            else:
                item_models.append(item)

        # Sort by priority (descending), then volume (descending for efficient packing)
        return sorted(
            item_models,
            key=lambda x: (
                -x.priority,
                x.expiry_date or datetime.max,
                -(x.width * x.depth * x.height)  # Larger items first
            )
        )

    def _optimize_rearrangement(
        self,
        item: Item,
        containers: List[Container]
    ) -> Tuple[bool, Optional[ItemPlacement], List[PlacementStep]]:
        """Optimize container space through rearrangement"""
        best_container = None
        best_utilization = float('inf')
        best_steps = []
        best_placement = None

        for container in containers:
            # Calculate current utilization
            current_util = self.space_utilization.get(container.id, 0)
            
            # Try different rearrangement strategies
            success, steps, placement, new_util = self._try_rearrangement_strategies(
                item, container, current_util
            )
            
            if success and new_util < best_utilization:
                best_container = container
                best_utilization = new_util
                best_steps = steps
                best_placement = placement

        if best_container:
            return True, best_placement, best_steps
        return False, None, []

    def _try_rearrangement_strategies(
        self,
        item: Item,
        container: Container,
        current_utilization: float
    ) -> Tuple[bool, List[PlacementStep], Optional[ItemPlacement], float]:
        strategies = [
            self._compact_items,
            self._stack_similar_items,
            self._move_low_priority_items
        ]

        best_result = (False, [], None, float('inf'))

        for strategy in strategies:
            success, steps, placement, new_util = strategy(item, container)
            if success and new_util < best_result[3]:
                best_result = (success, steps, placement, new_util)

        return best_result

    def _compact_items(
        self,
        item: Item,
        container: Container
    ) -> Tuple[bool, List[PlacementStep], Optional[ItemPlacement], float]:
        """Attempt to compact existing items to create space"""
        steps = []
        step_counter = 1
        
        # Get current items in container
        current_items = self.container_states.get(container.id, [])
        
        # Try to move items closer together
        for existing_item in current_items:
            # Find optimal position closer to container walls
            new_position = self._find_compact_position(
                existing_item,
                [i for i in current_items if i != existing_item]
            )
            
            if new_position:
                steps.append(PlacementStep(
                    step=step_counter,
                    action="move",
                    itemId=existing_item["itemId"],
                    fromContainer=container.id,
                    fromPosition=Position(**existing_item["position"]),
                    toContainer=container.id,
                    toPosition=new_position
                ))
                step_counter += 1
                existing_item["position"] = new_position.dict()

        # Try to place the new item
        new_position = self._find_position_in_container(item, container)
        if new_position:
            placement = ItemPlacement(
                itemId=item.itemId,
                containerId=container.id,
                position=new_position
            )
            return True, steps, placement, self._calculate_utilization(container.id)
            
        return False, [], None, float('inf')

    def _init_space_utilization(self, containers: List[Any]):
        """Initialize space utilization tracking"""
        for container in containers:
            cont_id = container.id if isinstance(container, Container) else container["containerId"]
            self.space_utilization[cont_id] = 0.0

    def _update_space_utilization(self, placement: ItemPlacement):
        """Update space utilization for a container after placement"""
        container_id = placement.container_id
        if container_id not in self.space_utilization:
            return

        # Calculate volume of placed item
        item_volume = (
            (placement.position.endCoordinates["width"] - placement.position.startCoordinates["width"]) *
            (placement.position.endCoordinates["depth"] - placement.position.startCoordinates["depth"]) *
            (placement.position.endCoordinates["height"] - placement.position.startCoordinates["height"])
        )

        # Update utilization
        self.space_utilization[container_id] += item_volume

    def _calculate_utilization(self, container_id: str) -> float:
        """Calculate current space utilization of a container"""
        return self.space_utilization.get(container_id, 0.0)

    def _get_possible_rotations(self, item: Item) -> List[Item]:
        """Get all possible rotations of an item"""
        rotations = []
        dimensions = [(item.width, item.depth, item.height),
                     (item.width, item.height, item.depth),
                     (item.depth, item.width, item.height),
                     (item.depth, item.height, item.width),
                     (item.height, item.width, item.depth),
                     (item.height, item.depth, item.width)]
        
        for w, d, h in dimensions:
            rotated = Item(
                itemId=item.itemId,
                name=item.name,
                width=w,
                depth=d,
                height=h,
                mass=item.mass,
                priority=item.priority,
                expiry_date=item.expiry_date,
                usage_limit=item.usage_limit,
                uses_remaining=item.uses_remaining,
                preferred_zone=item.preferred_zone
            )
            rotations.append(rotated)
        
        return rotations

    def _count_retrieval_steps(
        self,
        item: Item,
        placement: ItemPlacement,
        container: Container
    ) -> int:
        """Count number of items that need to be moved to retrieve this item"""
        steps = 0
        if not placement.position:
            return float('inf')
            
        container_items = self.container_states.get(container.id, [])
        item_depth = placement.position.startCoordinates["depth"]
        
        for existing_item in container_items:
            if existing_item["position"]["startCoordinates"]["depth"] < item_depth:
                # Check if item blocks access path
                if self._check_perpendicular_overlap(
                    placement.position.startCoordinates,
                    placement.position.endCoordinates,
                    existing_item["position"]["startCoordinates"],
                    existing_item["position"]["endCoordinates"]
                ):
                    steps += 2  # One step to remove, one to place back
                    
        return steps

    def _check_perpendicular_overlap(
        self,
        pos1_start: Dict,
        pos1_end: Dict,
        pos2_start: Dict,
        pos2_end: Dict
    ) -> bool:
        """Check if two positions overlap in the width-height plane"""
        return not (
            pos1_end["width"] <= pos2_start["width"] or
            pos1_start["width"] >= pos2_end["width"] or
            pos1_end["height"] <= pos2_start["height"] or
            pos1_start["height"] >= pos2_end["height"]
        )

    def _find_optimal_position(
        self,
        item: Item,
        containers: List[Container]
    ) -> Optional[ItemPlacement]:
        try:
            for container in containers:
                position = self._find_position_in_container(item, container)
                if position:
                    return ItemPlacement(
                        itemId=item.itemId,
                        containerId=container.id,
                        position=position
                    )
            return None
        except Exception as e:
            logger.error(f"Error finding optimal position: {traceback.format_exc()}")
            raise InventoryError(f"Position finding failed: {str(e)}")

    def _find_position_in_container(
        self,
        item: Item,
        container: Container
    ) -> Optional[Position]:
        try:
            container_state = self.container_states.get(container.id, [])
            logger.debug(f"Finding position in container {container.id} with {len(container_state)} existing items")
            
            # Check if item fits in container
            if (item.width > container.width or
                item.depth > container.depth or
                item.height > container.height):
                logger.debug(f"Item {item.itemId} is too large for container {container.id}")
                return None
                
            # Find the best position (bottom-left strategy)
            x = 0
            y = 0
            z = 0
            
            while z + item.height <= container.height:
                while y + item.depth <= container.depth:
                    while x + item.width <= container.width:
                        start_coords = Coordinates(width=float(x), depth=float(y), height=float(z))
                        end_coords = Coordinates(
                            width=float(x + item.width),
                            depth=float(y + item.depth),
                            height=float(z + item.height)
                        )
                        
                        position = Position(
                            start_coordinates=start_coords,
                            end_coordinates=end_coords
                        )
                        
                        if self._is_position_valid(position, container_state):
                            logger.debug(f"Found valid position for item {item.itemId} in container {container.id}")
                            return position
                        
                        x += 1
                    x = 0
                    y += 1
                y = 0
                z += 1
            
            logger.debug(f"No valid position found for item {item.itemId} in container {container.id}")
            return None
        except Exception as e:
            logger.error(f"Error finding position in container: {traceback.format_exc()}")
            raise InventoryError(f"Container position finding failed: {str(e)}")

    def _is_position_valid(
        self,
        position: Position,
        container_state: List[Dict]
    ) -> bool:
        try:
            for existing_item in container_state:
                if self._check_overlap(position, existing_item["position"]):
                    return False
            return True
        except Exception as e:
            logger.error(f"Error checking position validity: {traceback.format_exc()}")
            raise InventoryError(f"Position validation failed: {str(e)}")

    def _check_overlap(
        self,
        pos1: Position,
        pos2: Position
    ) -> bool:
        try:
            return not (
                pos1.endCoordinates["width"] <= pos2["startCoordinates"]["width"] or
                pos1.startCoordinates["width"] >= pos2["endCoordinates"]["width"] or
                pos1.endCoordinates["depth"] <= pos2["startCoordinates"]["depth"] or
                pos1.startCoordinates["depth"] >= pos2["endCoordinates"]["depth"] or
                pos1.endCoordinates["height"] <= pos2["startCoordinates"]["height"] or
                pos1.startCoordinates["height"] >= pos2["endCoordinates"]["height"]
            )
        except Exception as e:
            logger.error(f"Error checking overlap: {traceback.format_exc()}")
            raise InventoryError(f"Overlap check failed: {str(e)}")

    def _update_container_state(self, placement: ItemPlacement):
        try:
            if placement.container_id not in self.container_states:
                self.container_states[placement.container_id] = []
                
            self.container_states[placement.container_id].append({
                "itemId": placement.item_id,
                "position": {
                    "startCoordinates": placement.position.startCoordinates,
                    "endCoordinates": placement.position.endCoordinates
                }
            })
            logger.debug(f"Updated container state for {placement.container_id}")
        except Exception as e:
            logger.error(f"Error updating container state: {traceback.format_exc()}")
            raise InventoryError(f"Container state update failed: {str(e)}")

    def _attempt_rearrangement(
        self,
        item: Item,
        containers: List[Container]
    ) -> Tuple[bool, List[PlacementStep]]:
        try:
            # For now, implement a simple rearrangement strategy
            steps = []
            step_counter = 1
            
            # Try to find a container with enough space after rearrangement
            for container in containers:
                # Get all items in this container
                items_in_container = [
                    item for items in self.container_states.get(container.id, [])
                    for item in items if not item.get("is_waste", False)
                ]
                
                if not items_in_container:
                    continue
                    
                # Try moving each item to make space
                for existing_item in items_in_container:
                    # Remove item temporarily
                    old_position = existing_item["position"]
                    self.container_states[container.id].remove(existing_item)
                    
                    # Try to place our new item
                    new_position = self._find_position_in_container(item, container)
                    
                    if new_position:
                        # Found a valid rearrangement
                        steps.append(PlacementStep(
                            step=step_counter,
                            action="move",
                            itemId=existing_item["itemId"],
                            fromContainer=container.id,
                            fromPosition=Position(**old_position),
                            toContainer=container.id,
                            toPosition=new_position
                        ))
                        return True, steps
                    
                    # Put the existing item back
                    self.container_states[container.id].append(existing_item)
                    
            return False, []
        except Exception as e:
            logger.error(f"Error attempting rearrangement: {traceback.format_exc()}")
            raise InventoryError(f"Rearrangement failed: {str(e)}")