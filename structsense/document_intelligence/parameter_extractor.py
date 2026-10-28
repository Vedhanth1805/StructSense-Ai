"""Traceable structural parameter extraction without invented defaults."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Iterable

PARAM_SPEC = {
    "concrete_grade": {"label": "Concrete Grade (MPa)", "min": 15, "max": 60, "unit": "MPa"},
    "steel_grade": {"label": "Steel Grade (MPa)", "min": 250, "max": 550, "unit": "MPa"},
    "column_width_mm": {"label": "Column Width (mm)", "min": 200, "max": 800, "unit": "mm"},
    "column_depth_mm": {"label": "Column Depth (mm)", "min": 200, "max": 800, "unit": "mm"},
    "num_floors": {"label": "Number of Floors", "min": 1, "max": 20, "unit": ""},
    "floor_load_kn_m2": {"label": "Floor Load (kN/m²)", "min": 2, "max": 15, "unit": "kN/m²"},
    "soil_bearing_capacity_kn_m2": {"label": "Soil Bearing Capacity (kN/m²)", "min": 50, "max": 500, "unit": "kN/m²"},
    "foundation_depth_m": {"label": "Foundation Depth (m)", "min": 0.5, "max": 5, "unit": "m"},
    "seismic_zone": {"label": "Seismic Zone", "min": 1, "max": 5, "unit": ""},
    "wind_speed_kmph": {"label": "Wind Speed (km/h)", "min": 20, "max": 250, "unit": "km/h"},
    "rainfall_mm_annual": {"label": "Annual Rainfall (mm)", "min": 200, "max": 3000, "unit": "mm"},
    "building_age_years": {"label": "Building Age (years)", "min": 0, "max": 100, "unit": "years"},
    "shear_wall_present": {"label": "Shear Wall Present", "min": 0, "max": 1, "unit": "0/1"},
    "foundation_type": {"label": "Foundation Type", "min": 0, "max": 2, "unit": "0=Isolated,1=Raft,2=Pile"},
    "column_reinforcement_ratio": {"label": "Column Reinforcement Ratio", "min": 0.008, "max": 0.06, "unit": ""},
    "beam_depth_mm": {"label": "Beam Depth (mm)", "min": 300, "max": 900, "unit": "mm"},
    "slab_thickness_mm": {"label": "Slab Thickness (mm)", "min": 100, "max": 300, "unit": "mm"},
    "location_risk_index": {"label": "Location Risk Index", "min": 0, "max": 1, "unit": "0-1"},
}
INTEGER_PARAMS = {"num_floors", "seismic_zone", "shear_wall_present", "foundation_type"}

ALIASES = {
    "concrete_grade": r"(?:concrete(?:\s+grade)?|fck)\s*(?:grade)?\s*[:=\-]?\s*M?\s*(\d+(?:\.\d+)?)",
    "steel_grade": r"(?:steel(?:\s+grade)?|fy)\s*(?:grade)?\s*[:=\-]?\s*Fe?\s*(\d+(?:\.\d+)?)",
    "column_width_mm": r"column\s+(?:width|breadth)\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*mm",
    "column_depth_mm": r"column\s+(?:depth|length)\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*mm",
    "num_floors": r"(?:number\s+of\s+floors|floors|storeys|stories)\s*[:=\-]?\s*(\d+(?:\.\d+)?)",
    "floor_load_kn_m2": r"(?:floor\s+load|live\s+load)[^0-9]{0,35}(\d+(?:\.\d+)?)\s*kN\s*/?\s*m(?:2|²)",
    "soil_bearing_capacity_kn_m2": r"(?:(?:soil\s+)?(?:safe\s+)?bearing\s+capacity|SBC)[^0-9]{0,35}(\d+(?:\.\d+)?)\s*kN\s*/?\s*m(?:2|²)",
    "foundation_depth_m": r"foundation\s+depth\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*m(?:et(?:er)?s?)?\b",
    "seismic_zone": r"(?:seismic\s+)?zone\s*[:=\-]?\s*(\d+)\b",
    "wind_speed_kmph": r"wind\s+speed[^0-9]{0,35}(\d+(?:\.\d+)?)\s*(?:km/?h|kmph)",
    "rainfall_mm_annual": r"(?:annual\s+)?rainfall[^0-9]{0,35}(\d+(?:\.\d+)?)\s*mm",
    "building_age_years": r"(?:building\s+)?age[^0-9]{0,25}(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
    "column_reinforcement_ratio": r"(?:column\s+)?(?:reinforcement|steel)\s+ratio[^0-9]{0,25}(\d+(?:\.\d+)?)\s*%?",
    "beam_depth_mm": r"beam\s+depth\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*mm",
    "slab_thickness_mm": r"slab\s+thickness\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*mm",
    "location_risk_index": r"location\s+risk\s+index\s*[:=\-]?\s*(\d+(?:\.\d+)?)",
}

class ParameterExtractor:
    """Extract explicit values deterministically; optional LLM results remain traceable."""

    def extract(self, api_key: Optional[str], corpus: str, source_document: str = "document") -> Dict[str, Any]:
        records: Dict[str, Any] = {}
        interpretation = {
            "provider": "local_rule_based", "status": "not_configured", "request_made": False,
            "fields_added": 0,
            "label": "LOCAL / RULE-BASED FALLBACK — live Groq/LLaMA is not configured",
        }
        column_section = re.search(
            r"columns?[^.\n]{0,60}?(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm\b|"
            r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm[^.\n]{0,60}?columns?\b",
            corpus, re.IGNORECASE)
        for key, pattern in ALIASES.items():
            match = re.search(pattern, corpus, re.IGNORECASE)
            if not match and column_section and key in ("column_width_mm", "column_depth_mm"):
                groups = column_section.groups()
                value_group = (groups[0] or groups[2]) if key == "column_width_mm" else (groups[1] or groups[3])
                if value_group:
                    self._put(records, key, value_group, column_section.group(0), source_document, "regex", 1.0)
                continue
            if not match and key == "concrete_grade":
                match = re.search(r"\bM\s*(\d+(?:\.\d+)?)\s*(?:grade\s+)?concrete\b", corpus, re.I)
            if not match and key == "steel_grade":
                match = re.search(r"\bFe\s*(\d+(?:\.\d+)?)\b", corpus, re.I)
            if not match and key == "num_floors":
                match = re.search(r"\b(\d+(?:\.\d+)?)\s*[- ]?(?:storey|story)\b", corpus, re.I)
            if not match and key == "foundation_depth_m":
                match = re.search(r"foundation[^.\n]{0,100}?depth[^0-9]{0,20}(\d+(?:\.\d+)?)\s*m(?:et(?:er)?s?)?\b", corpus, re.I)
            if not match and key == "beam_depth_mm":
                match = re.search(r"beams?[^.\n]{0,100}?depth[^0-9]{0,20}(\d+(?:\.\d+)?)\s*mm\b", corpus, re.I)
            if not match and key == "slab_thickness_mm":
                match = re.search(r"slabs?[^.\n]{0,100}?thickness[^0-9]{0,20}(\d+(?:\.\d+)?)\s*mm\b", corpus, re.I)
            if not match and key == "foundation_type":
                match = re.search(r"\b(isolated|raft|pile)\s+foundation\b", corpus, re.I)
            if not match and key == "location_risk_index":
                match = re.search(r"location\s+risk\s+index[^0-9]{0,80}(\d+(?:\.\d+)?)", corpus, re.I)
            if not match and key in ("column_width_mm", "column_depth_mm"):
                dimension = "width" if key == "column_width_mm" else "depth"
                match = re.search(r"columns?[^.\n]{0,160}?(\d+(?:\.\d+)?)\s*mm\s+" + dimension + r"\b", corpus, re.I)
                if not match:
                    match = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+" + dimension + r"[^.\n]{0,120}columns?", corpus, re.I)
            if not match:
                continue
            value = float(match.group(1))
            if key == "column_reinforcement_ratio" and value > 0.06:
                value /= 100.0
            if key == "concrete_grade":
                value = float(match.group(1))
            self._put(records, key, value, match.group(0), source_document, "regex", 1.0)
        for key, (pattern, present_value, absent_value) in {
            "shear_wall_present": (r"shear\s+walls?", 1.0, 0.0),
        }.items():
            match = re.search(pattern, corpus, re.IGNORECASE)
            if match:
                around = corpus[max(0, match.start()-30):match.end()+30]
                value = absent_value if re.search(r"\b(?:no|without|absent)\b", around, re.I) else present_value
                self._put(records, key, value, match.group(0), source_document, "regex", 0.9)
        match = re.search(r"foundation\s+type\s*[:=\-]?\s*(isolated|raft|pile)", corpus, re.I)
        if not match:
            match = re.search(r"\b(isolated|raft|pile)\s+foundation\b", corpus, re.I)
        if match:
            value = {"isolated": 0.0, "raft": 1.0, "pile": 2.0}[match.group(1).lower()]
            self._put(records, "foundation_type", value, match.group(0), source_document, "regex", 1.0)

        # Use the repository's existing Groq model only to map document context not
        # found by explicit patterns. Missing values remain null; never defaults.
        if api_key and corpus.strip() and len(records) < len(PARAM_SPEC):
            try:
                from groq import Groq
                interpretation.update({"status": "requesting", "request_made": True,
                    "label": "LIVE GROQ/LLAMA — request in progress"})
                prompt = ("Extract only explicitly stated structural values from this text. "
                          "Return JSON object keyed by these names, values as numbers or null: "
                          + ", ".join(PARAM_SPEC) + ". Never infer or supply defaults. "
                          "Include a source_text object alongside each number as {value, source_text}.\n" + corpus[:8000])
                response = Groq(api_key=api_key).chat.completions.create(
                    model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}],
                    temperature=0, max_completion_tokens=1200,
                )
                text = response.choices[0].message.content.strip().removeprefix("```json").removesuffix("```").strip()
                mapped = json.loads(text)
                added_before = len(records)
                for key, item in mapped.items():
                    if key not in PARAM_SPEC or key in records or item is None:
                        continue
                    value = item.get("value") if isinstance(item, dict) else item
                    quote = item.get("source_text", "") if isinstance(item, dict) else ""
                    normalized_corpus = " ".join(corpus.lower().split())
                    if not quote or " ".join(str(quote).lower().split()) not in normalized_corpus:
                        continue
                    self._put(records, key, value, quote, source_document, "groq_llama", None)
                added = len(records) - added_before
                interpretation.update({"provider": "groq_llama", "status": "request_succeeded",
                    "fields_added": added,
                    "label": "LIVE GROQ/LLAMA — request succeeded; %d additional fields accepted" % added})
            except ImportError:
                interpretation.update({"status": "client_unavailable", "request_made": False,
                    "label": "LOCAL / RULE-BASED FALLBACK — Groq client package is unavailable"})
            except Exception as exc:
                # Explicit extraction results are still useful if the optional LLM fails.
                interpretation.update({"status": "request_failed", "request_made": True,
                    "failure_type": type(exc).__name__,
                    "label": "LOCAL / RULE-BASED FALLBACK — Groq/LLaMA request failed (%s)" % type(exc).__name__})
        elif api_key and corpus.strip():
            interpretation.update({"status": "not_needed",
                "label": "LOCAL / RULE-BASED EXTRACTION — all supported values were explicitly matched; Groq not called"})
        return {"parameters": records, "unavailable": [k for k in PARAM_SPEC if k not in records],
                "interpretation": interpretation}

    @staticmethod
    def _put(records: dict, key: str, value: Any, quote: str, source: str, method: str, confidence: Optional[float]) -> None:
        try:
            value = float(value)
            spec = PARAM_SPEC[key]
            if not spec["min"] <= value <= spec["max"]:
                return
            if key in INTEGER_PARAMS and not value.is_integer():
                return
        except (ValueError, TypeError):
            return
        records[key] = {"value": value, "source_text": quote, "source_document": source,
                        "method": method, "confidence": confidence,
                        "confidence_kind": "extraction score" if confidence is not None else "not provided",
                        "validation_status": "pending"}
