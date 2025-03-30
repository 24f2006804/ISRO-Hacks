from typing import List, Dict, Tuple, Optional, Any
from ..models import Item, Container
from ..schemas import Position, PlacementStep, ItemPlacement
from datetime import datetime

class PlacementService:
    def __init__(self):
        self.container_states: Dict[str, List[Dict]] = {}

    def optimize_placement(
        self,
        items: List[Dict[str, Any]] | List[Item],
        containers: List[Dict[str, Any]] | List[Container]
    ) -> Tuple[List[ItemPlacement], List[PlacementStep]]:
        # Convert dictionaries to models with proper field mapping
        items_models = []
        for item in items:
            if isinstance(item, dict):
                # Map camelCase to snake_case
                item_data = {
                    "id": item["itemId"],
                    "name": item["name"],
                    "width": item["width"],
                    "depth": item["depth"],
                    "height": item["height"],
                    "priority": item["priority"],
                    "preferred_zone": item["preferredZone"]
                }
                items_models.append(Item(**item_data))
            else:
                items_models.append(item)

        container_models = []
        for cont in containers:
            if isinstance(cont, dict):
                # Map camelCase to snake_case
                cont_data = {
                    "id": cont["containerId"],
                    "zone": cont["zone"],
                    "width": cont["width"],
                    "depth": cont["depth"],
                    "height": cont["height"]
                }
                container_models.append(Container(**cont_data))
            else:
                container_models.append(cont)

        # Rest of the function remains the same
        sorted_items = sorted(
            items_models,
            key=lambda x: (-x.priority, x.expiry_date or datetime.max)
        )
        
        placements = []
        rearrangements = []
        
        for item in sorted_items:
            # Try preferred zone first
            preferred_containers = [
                c for c in container_models if c.zone == item.preferred_zone
            ]
            
            placement = self._find_optimal_position(
                item, preferred_containers
            )
            
            if not placement:
                # If no space in preferred zone, try other zones
                other_containers = [
                    c for c in container_models if c.zone != item.preferred_zone
                ]
                placement = self._find_optimal_position(item, other_containers)
            
            if placement:
                placements.append(placement)
                # Update container state
                self._update_container_state(placement)
            else:
                # Need rearrangement
                success, steps = self._attempt_rearrangement(
                    item, container_models
                )
                if success:
                    rearrangements.extend(steps)
                    # Try placement again after rearrangement
                    placement = self._find_optimal_position(
                        item, container_models
                    )
                    if placement:
                        placements.append(placement)
                        self._update_container_state(placement)
        
        return placements, rearrangements

    def _find_optimal_position(
        self,
        item: Item,
        containers: List[Container]
    ) -> Optional[ItemPlacement]:
        for container in containers:
            position = self._find_position_in_container(item, container)
            if position:
                return ItemPlacement(
                    itemId=item.id,
                    containerId=container.id,
                    position=position
                )
        return None

    def _find_position_in_container(
        self,
        item: Item,
        container: Container
    ) -> Optional[Position]:
        container_state = self.container_states.get(container.id, [])
        
        # Check if item fits in container
        if (item.width > container.width or
            item.depth > container.depth or
            item.height > container.height):
            return None
            
        # Find the best position (bottom-left strategy)
        x = 0
        y = 0
        z = 0
        
        while z + item.height <= container.height:
            while y + item.depth <= container.depth:
                while x + item.width <= container.width:
                    position = Position(
                        start_coordinates={"width": x, "depth": y, "height": z},
                        end_coordinates={"width": x + item.width, "depth": y + item.depth, "height": z + item.height}
                    )
                    
                    if self._is_position_valid(position, container_state):
                        return position
                    
                    x += 1
                x = 0
                y += 1
            y = 0
            z += 1
            
        return None

    def _is_position_valid(
        self,
        position: Position,
        container_state: List[Dict]
    ) -> bool:
        for existing_item in container_state:
            if self._check_overlap(position, existing_item["position"]):
                return False
        return True

    def _check_overlap(
        self,
        pos1: Position,
        pos2: Position
    ) -> bool:
        return not (
            pos1.endCoordinates.width <= pos2.startCoordinates.width or
            pos1.startCoordinates.width >= pos2.endCoordinates.width or
            pos1.endCoordinates.depth <= pos2.startCoordinates.depth or
            pos1.startCoordinates.depth >= pos2.endCoordinates.depth or
            pos1.endCoordinates.height <= pos2.startCoordinates.height or
            pos1.startCoordinates.height >= pos2.endCoordinates.height
        )

    def _update_container_state(self, placement: ItemPlacement):
        if placement.container_id not in self.container_states:
            self.container_states[placement.container_id] = []
            
        self.container_states[placement.container_id].append({
            "itemId": placement.item_id,
            "position": placement.position
        })

    def _attempt_rearrangement(
        self,
        item: Item,
        containers: List[Container]
    ) -> Tuple[bool, List[PlacementStep]]:
        # TODO: Implement rearrangement logic
        # This would involve moving items around to create space
        # For now, return empty rearrangement
        return False, []