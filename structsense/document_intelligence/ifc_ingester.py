"""Optional IfcOpenShell adapter producing source-traceable structural records."""
from __future__ import annotations

import os
from typing import Any, Dict

class IFCIngester:
    def extract(self, path: str) -> Dict[str, Any]:
        try:
            import ifcopenshell
        except ImportError as exc:
            raise RuntimeError("IFC support requires IfcOpenShell; install it from requirements.txt") from exc
        try:
            model = ifcopenshell.open(path)
        except Exception as exc:
            raise ValueError("The IFC file could not be opened") from exc
        try:
            import ifcopenshell.util.unit
            unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)
        except Exception:
            unit_scale = None
        objects = []
        counts = {"columns": 0, "beams": 0, "slabs": 0, "materials": 0, "levels": 0}
        for kind, entity in (("columns", "IfcColumn"), ("beams", "IfcBeam"), ("slabs", "IfcSlab"),
                             ("levels", "IfcBuildingStorey")):
            try:
                elements = model.by_type(entity)
            except Exception:
                elements = []
            counts[kind] = len(elements)
            for item in elements:
                row = {"global_id": getattr(item, "GlobalId", None), "type": kind,
                                "name": getattr(item, "Name", None), "object_type": getattr(item, "ObjectType", None),
                                "properties": self._properties(item)}
                if kind == "levels":
                    elevation = getattr(item, "Elevation", None)
                    if elevation is not None:
                        row["elevation_project_units"] = float(elevation)
                        if unit_scale is not None:
                            row["elevation_m"] = float(elevation) * float(unit_scale)
                objects.append(row)
        try:
            counts["materials"] = len(model.by_type("IfcMaterial"))
        except Exception:
            pass
        parameters = self._normalize(objects, unit_scale)
        for record in parameters.values():
            record["source_document"] = os.path.basename(path)
        return {"objects": objects, "counts": counts, "parameters": parameters, "source": path}

    @staticmethod
    def _properties(item: Any) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            import ifcopenshell.util.element
            result.update(ifcopenshell.util.element.get_psets(item))
            material = ifcopenshell.util.element.get_material(item)
            if material:
                result["material"] = getattr(material, "Name", None)
            placement = getattr(item, "ObjectPlacement", None)
            if placement:
                matrix = ifcopenshell.util.placement.get_local_placement(placement)
                result["location_project_units"] = [float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3])]
        except Exception:
            pass
        return result

    @staticmethod
    def _normalize(objects: list, unit_scale: Any) -> Dict[str, Any]:
        """Only emit values backed by IFC properties; no dimensions are inferred."""
        result: Dict[str, Any] = {}
        cols = [o for o in objects if o["type"] == "columns"]
        beams = [o for o in objects if o["type"] == "beams"]
        slabs = [o for o in objects if o["type"] == "slabs"]
        def prop(items: list, names: tuple[str, ...]):
            for item in items:
                stack = list(item.get("properties", {}).values())
                while stack:
                    value = stack.pop()
                    if isinstance(value, dict):
                        for name, v in value.items():
                            if name.lower().replace(" ", "") in tuple(n.replace(" ", "") for n in names) and isinstance(v, (int, float)):
                                return float(v), item, name
                            stack.append(v)
            return None, None, None
        for key, items, names in (
            ("column_width_mm", cols, ("width", "overallwidth")),
            ("column_depth_mm", cols, ("depth", "overall depth", "overallheight")),
            ("beam_depth_mm", beams, ("depth", "overallheight")),
            ("slab_thickness_mm", slabs, ("thickness", "overallthickness")),
        ):
            value, source_object, property_name = prop(items, names)
            if value is not None and unit_scale is not None:
                source_value = value
                value = value * float(unit_scale) * 1000.0
                object_label = (source_object.get("name") or source_object.get("global_id") or "unnamed object")
                result[key] = {"value": value,
                               "source_text": "IFC property %s=%s (project units)" % (property_name, source_value),
                               "source_document": "IFC",
                               "source_location": "IFC %s: %s" % (source_object.get("type", "object"), object_label),
                               "method": "ifcopenshell property", "confidence": None,
                               "confidence_kind": "not provided", "validation_status": "pending"}
        return result
