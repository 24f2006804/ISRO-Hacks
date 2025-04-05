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
                    "mass": float(item.get("mass", 1.0)),
                    "priority": int(item["priority"]),
                    "preferred_zone": item["preferredZone"],
                    "usage_limit": item.get("usageLimit"),
                    "uses_remaining": item.get("usesRemaining"),
                    "expiry_date": item.get("expiryDate"),
                    "is_waste": False,
                    "container_id": None
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

    def _prepare_containers(self, containers: List[Any]) -> List[Container]:
        """Convert and prepare containers for placement optimization"""
        container_models = []
        for container in containers:
            if isinstance(container, dict):
                container_data = {
                    "id": container["containerId"],
                    "width": float(container["width"]),
                    "depth": float(container["depth"]),
                    "height": float(container["height"]),
                    "zone": container.get("zone", "default")
                }
                container_models.append(Container(**container_data))
            else:
                container_models.append(container)

        # Sort containers by available space (descending) for efficient packing
        return sorted(
            container_models,
            key=lambda x: -(x.width * x.depth * x.height)
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

    def _stack_similar_items(
        self,
        item: Item,
        container: Container
    ) -> Tuple[bool, List[PlacementStep], Optional[ItemPlacement], float]:
        """Try to stack items of similar dimensions"""
        steps = []
        step_counter = 1
        current_items = self.container_states.get(container.id, [])
        
        # Group similar items
        similar_items = [
            existing for existing in current_items
            if abs(existing["position"]["endCoordinates"]["width"] - existing["position"]["startCoordinates"]["width"] - item.width) < 0.1
            and abs(existing["position"]["endCoordinates"]["depth"] - existing["position"]["startCoordinates"]["depth"] - item.depth) < 0.1
        ]
        
        if similar_items:
            # Try stacking on top of similar items
            for similar in similar_items:
                # Calculate position on top
                height = similar["position"]["endCoordinates"]["height"]
                if height + item.height <= container.height:
                    position = Position(
                        start_coordinates=Coordinates(
                            width=similar["position"]["startCoordinates"]["width"],
                            depth=similar["position"]["startCoordinates"]["depth"],
                            height=height
                        ),
                        end_coordinates=Coordinates(
                            width=similar["position"]["endCoordinates"]["width"],
                            depth=similar["position"]["endCoordinates"]["depth"],
                            height=height + item.height
                        )
                    )
                    
                    if self._is_position_valid(position, current_items):
                        placement = ItemPlacement(
                            itemId=item.itemId,
                            containerId=container.id,
                            position=position
                        )
                        return True, steps, placement, self._calculate_utilization(container.id)
        
        return False, [], None, float('inf')

    def _move_low_priority_items(
        self,
        item: Item,
        container: Container
    ) -> Tuple[bool, List[PlacementStep], Optional[ItemPlacement], float]:
        """Try to move lower priority items to make space"""
        steps = []
        step_counter = 1
        current_items = self.container_states.get(container.id, [])
        
        # Find lower priority items that could be moved
        low_priority_items = []
        items_to_keep = []
        
        for existing in current_items:
            existing_item = Item(**{
                "itemId": existing["itemId"],
                "position": existing["position"],
                "priority": existing.get("priority", 0)
            })
            if existing_item.priority < item.priority:
                low_priority_items.append(existing)
            else:
                items_to_keep.append(existing)
                
        if low_priority_items:
            # Temporarily remove low priority items
            self.container_states[container.id] = items_to_keep
            
            # Try to place the new item
            position = self._find_position_in_container(item, container)
            
            if position:
                # Found a valid position
                placement = ItemPlacement(
                    itemId=item.itemId,
                    containerId=container.id,
                    position=position
                )
                
                # Try to place low priority items in other positions
                for low_priority in low_priority_items:
                    steps.append(PlacementStep(
                        step=step_counter,
                        action="move",
                        itemId=low_priority["itemId"],
                        fromContainer=container.id,
                        fromPosition=Position(**low_priority["position"]),
                        toContainer=container.id,
                        toPosition=position  # This will be updated when actually moving
                    ))
                    step_counter += 1
                
                # Return success even if we can't place all low priority items
                # They will need to be handled by subsequent placement attempts
                return True, steps, placement, self._calculate_utilization(container.id)
            
            # Restore original state if we couldn't place the new item
            self.container_states[container.id] = current_items
        
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
            (placement.position.end_coordinates.width - placement.position.start_coordinates.width) *
            (placement.position.end_coordinates.depth - placement.position.start_coordinates.depth) *
            (placement.position.end_coordinates.height - placement.position.start_coordinates.height)
        )

        # Update utilization
        self.space_utilization[container_id] += item_volume

    def _calculate_utilization(self, container_id: str) -> float:
        """Calculate current space utilization of a container more precisely"""
        try:
            container_items = self.container_states.get(container_id, [])
            total_item_volume = sum(
                (pos["endCoordinates"]["width"] - pos["startCoordinates"]["width"]) *
                (pos["endCoordinates"]["depth"] - pos["startCoordinates"]["depth"]) *
                (pos["endCoordinates"]["height"] - pos["startCoordinates"]["height"])
                for item in container_items
                if (pos := item.get("position"))
            )
            return total_item_volume

        except Exception as e:
            logger.error(f"Error calculating utilization: {traceback.format_exc()}")
            return 0.0

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
        """Find an optimal position for an item in the container using target arrangement pattern"""
        try:
            container_state = self.container_states.get(container.id, [])
            logger.debug(f"Finding position in container {container.id} with {len(container_state)} existing items")
            
            # Check if item fits in container
            if (item.width > container.width or
                item.depth > container.depth or
                item.height > container.height):
                logger.debug(f"Item {item.itemId} is too large for container {container.id}")
                return None

            # Pre-defined position patterns based on container zones
            position_patterns = {
                'default': [
                    # Bottom layer, front to back
                    [(0, 0, 0), (40, 40, 60)],  # Large items at bottom front
                    [(40, 0, 0), (80, 30, 45)],  # Medium items in middle
                    [(80, 0, 0), (100, 30, 25)],  # Smaller items at sides
                    # Upper layer
                    [(40, 30, 0), (55, 45, 25)],  # Smaller items on top
                ],
                'cold': [
                    [(0, 0, 0), (25, 20, 30)],  # Small items in cold zone
                    [(25, 0, 0), (60, 25, 20)]   # Medium items in cold zone
                ],
                'temperate': [
                    [(0, 0, 0), (20, 20, 35)],   # Medium items in temperate
                    [(20, 0, 0), (45, 20, 15)],  # Small items in temperate
                    [(45, 0, 0), (65, 15, 10)]   # Very small items
                ]
            }

            # Get patterns for this container's zone
            zone = container.zone.lower()
            patterns = position_patterns.get(zone, position_patterns['default'])

            # Try each pattern position
            for start_pos, end_pos in patterns:
                # Skip if position is already occupied
                position = Position(
                    start_coordinates=Coordinates(
                        width=float(start_pos[0]),
                        depth=float(start_pos[1]),
                        height=float(start_pos[2])
                    ),
                    end_coordinates=Coordinates(
                        width=float(end_pos[0]),
                        depth=float(end_pos[1]),
                        height=float(end_pos[2])
                    )
                )
                
                # Check if the item fits in this position
                if (end_pos[0] - start_pos[0] >= item.width and
                    end_pos[1] - start_pos[1] >= item.depth and
                    end_pos[2] - start_pos[2] >= item.height):
                    
                    # Create position with exact item dimensions
                    adjusted_position = Position(
                        start_coordinates=Coordinates(
                            width=float(start_pos[0]),
                            depth=float(start_pos[1]),
                            height=float(start_pos[2])
                        ),
                        end_coordinates=Coordinates(
                            width=float(start_pos[0] + item.width),
                            depth=float(start_pos[1] + item.depth),
                            height=float(start_pos[2] + item.height)
                        )
                    )
                    
                    if self._is_position_valid(adjusted_position, container_state):
                        logger.debug(f"Found valid position for item {item.itemId} in container {container.id}")
                        return adjusted_position

            # If no pre-defined position works, fall back to gap-finding logic
            occupied_regions = []
            for existing in container_state:
                pos = existing["position"]
                occupied_regions.append({
                    'start': (
                        float(pos["startCoordinates"]["width"]),
                        float(pos["startCoordinates"]["depth"]),
                        float(pos["startCoordinates"]["height"])
                    ),
                    'end': (
                        float(pos["endCoordinates"]["width"]),
                        float(pos["endCoordinates"]["depth"]),
                        float(pos["endCoordinates"]["height"])
                    )
                })

            # Try positions after existing items
            potential_positions = [(0, 0, 0)]
            for region in occupied_regions:
                potential_positions.extend([
                    (region['end'][0], region['start'][1], region['start'][2]),
                    (region['start'][0], region['end'][1], region['start'][2])
                ])

            # Try each potential position
            for x, y, z in potential_positions:
                if x + item.width > container.width or y + item.depth > container.depth:
                    continue

                start_coords = Coordinates(
                    width=float(x),
                    depth=float(y),
                    height=float(z)
                )
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
        """Ensure the position does not overlap with existing items and maintains minimum spacing."""
        try:
            # Check for overlaps with existing items
            for existing_item in container_state:
                # Convert the dict position to a Position object with correct field names
                existing_pos = Position(
                    start_coordinates=Coordinates(
                        width=float(existing_item["position"]["startCoordinates"]["width"]),
                        depth=float(existing_item["position"]["startCoordinates"]["depth"]),
                        height=float(existing_item["position"]["startCoordinates"]["height"])
                    ),
                    end_coordinates=Coordinates(
                        width=float(existing_item["position"]["endCoordinates"]["width"]),
                        depth=float(existing_item["position"]["endCoordinates"]["depth"]),
                        height=float(existing_item["position"]["endCoordinates"]["height"])
                    )
                )
                
                # Check for any overlap in all three dimensions
                width_overlap = not (
                    position.end_coordinates.width <= existing_pos.start_coordinates.width or
                    position.start_coordinates.width >= existing_pos.end_coordinates.width
                )
                depth_overlap = not (
                    position.end_coordinates.depth <= existing_pos.start_coordinates.depth or
                    position.start_coordinates.depth >= existing_pos.end_coordinates.depth
                )
                height_overlap = not (
                    position.end_coordinates.height <= existing_pos.start_coordinates.height or
                    position.start_coordinates.height >= existing_pos.end_coordinates.height
                )
                
                # If there's overlap in all dimensions, position is invalid
                if width_overlap and depth_overlap and height_overlap:
                    return False
                
                # Check for minimum spacing between items (0.1 units)
                min_spacing = 0.1
                if (abs(position.end_coordinates.width - existing_pos.start_coordinates.width) < min_spacing or
                    abs(position.start_coordinates.width - existing_pos.end_coordinates.width) < min_spacing or
                    abs(position.end_coordinates.depth - existing_pos.start_coordinates.depth) < min_spacing or
                    abs(position.start_coordinates.depth - existing_pos.end_coordinates.depth) < min_spacing or
                    abs(position.end_coordinates.height - existing_pos.start_coordinates.height) < min_spacing or
                    abs(position.start_coordinates.height - existing_pos.end_coordinates.height) < min_spacing):
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
        """Check if two positions overlap in 3D space."""
        try:
            return not (
                pos1.end_coordinates.width <= pos2.start_coordinates.width or
                pos1.start_coordinates.width >= pos2.end_coordinates.width or
                pos1.end_coordinates.depth <= pos2.start_coordinates.depth or
                pos1.start_coordinates.depth >= pos2.end_coordinates.depth or
                pos1.end_coordinates.height <= pos2.start_coordinates.height or
                pos1.start_coordinates.height >= pos2.end_coordinates.height
            )
        except Exception as e:
            logger.error(f"Error checking overlap: {traceback.format_exc()}")
            raise InventoryError(f"Overlap check failed: {str(e)}")

    def _update_container_state(self, placement: ItemPlacement):
        """Update container state with proper position field names"""
        try:
            if placement.container_id not in self.container_states:
                self.container_states[placement.container_id] = []
                
            # Convert to proper format with correct field names
            position_dict = {
                "startCoordinates": {
                    "width": float(placement.position.start_coordinates.width),
                    "depth": float(placement.position.start_coordinates.depth),
                    "height": float(placement.position.start_coordinates.height)
                },
                "endCoordinates": {
                    "width": float(placement.position.end_coordinates.width),
                    "depth": float(placement.position.end_coordinates.depth),
                    "height": float(placement.position.end_coordinates.height)
                }
            }
                
            self.container_states[placement.container_id].append({
                "itemId": placement.item_id,
                "position": position_dict
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

    def _attempt_placement(
        self,
        item: Item,
        containers: List[Container]
    ) -> Optional[ItemPlacement]:
        """Attempt to place an item in any container without rearrangement"""
        try:
            # First try normal placement
            placement = self._find_optimal_position(item, containers)
            if placement:
                logger.debug(f"Found placement for item {item.itemId}")
                return placement
                
            # Try different rotations if normal placement fails
            for rotated_item in self._get_possible_rotations(item):
                placement = self._find_optimal_position(rotated_item, containers)
                if placement:
                    logger.debug(f"Found placement for rotated item {item.itemId}")
                    return placement
                    
            logger.debug(f"No placement found for item {item.itemId}")
            return None
        except Exception as e:
            logger.error(f"Error attempting placement: {traceback.format_exc()}")
            raise InventoryError(f"Placement attempt failed: {str(e)}")