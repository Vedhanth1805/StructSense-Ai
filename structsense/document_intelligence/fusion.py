"""Multi-source fusion and explicit conflict detection."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

def fuse_parameter_sources(source_records: Iterable[Dict[str, Any]], tolerance: float = 0.0) -> Dict[str, Any]:
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for source in source_records:
        for name, record in source.get("parameters", {}).items():
            item = dict(record)
            item.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            by_name.setdefault(name, []).append(item)
    parameters, conflicts = {}, []
    for name, records in by_name.items():
        distinct = []
        for row in records:
            def same_value(other):
                left, right = row.get("value"), other.get("value")
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    return abs(float(left) - float(right)) <= tolerance
                return left == right
            if not any(same_value(other) for other in distinct):
                distinct.append(row)
        if len(distinct) > 1:
            conflicts.append({"parameter": name, "values": distinct, "status": "requires_engineer_review"})
            parameters[name] = {**distinct[0], "validation_status": "conflict"}
        else:
            parameters[name] = {**records[0], "sources": records, "validation_status": "pending"}
    return {"parameters": parameters, "conflicts": conflicts}

def validate_parameter_set(parameters: Dict[str, Any], corrections: Optional[Dict[str, Any]] = None,
                           confirm: Iterable[str] = ()) -> Dict[str, Any]:
    """Apply engineer confirmations/corrections; preserve the original extraction record."""
    corrections = corrections or {}
    confirmed = set(confirm)
    output = {}
    for name, record in parameters.items():
        item = dict(record)
        if name in corrections:
            item["original_value"] = item.get("value")
            item["value"] = corrections[name]
            item["validation_status"] = "corrected"
        elif name in confirmed:
            item["validation_status"] = "validated"
        output[name] = item
    return output

def validated_values(parameters: Dict[str, Any], required: Iterable[str]) -> Dict[str, float]:
    missing = [name for name in required if name not in parameters or parameters[name].get("value") is None]
    invalid = [name for name in required if name in parameters and parameters[name].get("validation_status") not in ("validated", "corrected")]
    if missing or invalid:
        raise ValueError("Analysis blocked: missing values %s; parameters requiring validation %s" % (missing, invalid))
    return {name: float(parameters[name]["value"]) for name in required}
