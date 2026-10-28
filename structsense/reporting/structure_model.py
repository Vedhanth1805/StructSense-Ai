"""Parametric, illustrative 3D frame geometry. This is not an FEA model."""
from typing import Any, Dict

def build_frame(parameters: Dict[str, Any], bays: int = 2) -> Dict[str, Any]:
    floors = max(1, int(parameters.get("num_floors", 1)))
    storey_height_m = 3.0
    bay_width_m = 5.0
    nodes, members, slabs = [], [], []
    for level in range(floors + 1):
        z = level * storey_height_m
        for x in range(bays + 1):
            for y in range(bays + 1):
                nodes.append({"x": x * bay_width_m, "y": y * bay_width_m, "z": z})
    def index(level: int, x: int, y: int) -> int:
        return level * (bays + 1) ** 2 + y * (bays + 1) + x
    for level in range(floors + 1):
        for x in range(bays + 1):
            for y in range(bays + 1):
                if level < floors:
                    members.append({"type": "column", "start": index(level,x,y), "end": index(level+1,x,y)})
                if level > 0 and x < bays:
                    members.append({"type": "beam", "start": index(level,x,y), "end": index(level,x+1,y)})
                if level > 0 and y < bays:
                    members.append({"type": "beam", "start": index(level,x,y), "end": index(level,x,y+1)})
        if level > 0:
            for x in range(bays):
                for y in range(bays):
                    slabs.append({"type": "slab", "floor": level,
                                  "corners": [index(level,x,y), index(level,x+1,y),
                                              index(level,x+1,y+1), index(level,x,y+1)],
                                  "thickness_mm": parameters.get("slab_thickness_mm")})
    return {"nodes": nodes, "members": members, "slabs": slabs, "floors": floors,
            "column_width_mm": parameters.get("column_width_mm"),
            "column_depth_mm": parameters.get("column_depth_mm"),
            "beam_depth_mm": parameters.get("beam_depth_mm"),
            "slab_thickness_mm": parameters.get("slab_thickness_mm"),
            "grid_assumptions": {"bay_width_m": bay_width_m, "storey_height_m": storey_height_m},
            "classification": "Parametric structural visualization; not FEA"}

def compare_configurations(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    return {key: {"A": first.get(key), "B": second.get(key)}
            for key in sorted(set(first) | set(second)) if first.get(key) != second.get(key)}
