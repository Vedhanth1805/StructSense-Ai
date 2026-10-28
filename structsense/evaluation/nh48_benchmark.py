"""Run extraction metrics against a supplied NH-48 JSONL manifest.

No NH-48 source data is bundled. Each manifest line must contain:
{"document_id":"...", "document_path":"...pdf",
 "ground_truth_parameters":{"concrete_grade":30, ...}}

Document paths are resolved relative to the manifest. This tool reports only
field extraction metrics; it does not infer missing ground truth or paper
scenario outcomes.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from document_intelligence.parameter_extractor import PARAM_SPEC, ParameterExtractor
from document_intelligence.pdf_ingester import PDFIngester


def evaluate_records(records: Iterable[Mapping[str, Any]], manifest_dir: Path,
                     tolerance: float = 1e-6) -> Dict[str, Any]:
    """Extract each supplied PDF and compare stated fields with supplied labels."""
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"expected": 0, "correct": 0, "extracted": 0})
    documents = []
    extractor = ParameterExtractor()
    ingester = PDFIngester()
    count = 0

    for line_number, record in enumerate(records, start=1):
        document_id = str(record.get("document_id", "")).strip()
        document_path = record.get("document_path")
        truth = record.get("ground_truth_parameters")
        if not document_id or not isinstance(document_path, str) or not isinstance(truth, dict) or not truth:
            raise ValueError(f"record {line_number} needs document_id, document_path, and non-empty ground_truth_parameters")
        unknown = set(truth) - set(PARAM_SPEC)
        if unknown:
            raise ValueError(f"record {line_number} has unsupported parameter keys: {', '.join(sorted(unknown))}")

        resolved_path = (manifest_dir / document_path).resolve()
        result = ingester.extract_text_from_pdf(str(resolved_path))
        if "error" in result:
            raise ValueError(f"could not read {document_id}: {result['error']}")
        extracted = extractor.extract("", result.get("full_text", ""), document_id)["parameters"]
        document_correct = 0
        for key, expected in truth.items():
            totals[key]["expected"] += 1
            observed = extracted.get(key)
            if observed is not None:
                totals[key]["extracted"] += 1
                value = observed.get("value") if isinstance(observed, dict) else observed
                try:
                    correct = math.isclose(float(value), float(expected), rel_tol=0.0, abs_tol=tolerance)
                except (TypeError, ValueError):
                    correct = False
                if correct:
                    totals[key]["correct"] += 1
                    document_correct += 1
        count += 1
        documents.append({"document_id": document_id, "page_count": result["total_pages"],
                          "extraction_quality": result["extraction_quality"],
                          "expected_fields": len(truth), "correct_fields": document_correct})

    expected_total = sum(item["expected"] for item in totals.values())
    correct_total = sum(item["correct"] for item in totals.values())
    extracted_total = sum(item["extracted"] for item in totals.values())
    return {
        "benchmark": "NH-48 user-supplied manifest",
        "source_data_available": count > 0,
        "document_count": count,
        "field_count": expected_total,
        "correct_field_count": correct_total,
        "extracted_field_count": extracted_total,
        "field_accuracy": correct_total / expected_total if expected_total else None,
        "field_coverage": extracted_total / expected_total if expected_total else None,
        "per_parameter": {
            key: {**counts,
                  "accuracy": counts["correct"] / counts["expected"] if counts["expected"] else None,
                  "coverage": counts["extracted"] / counts["expected"] if counts["expected"] else None}
            for key, counts in sorted(totals.items())
        },
        "documents": documents,
        "limitations": "Extraction metrics only; this result is not a reproduction of any paper benchmark unless the supplied manifest and labels are the original benchmark data.",
    }


def evaluate_manifest(path: Path, tolerance: float = 1e-6) -> Dict[str, Any]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("manifest contains no benchmark records")
    return evaluate_records(records, path.resolve().parent, tolerance)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSONL manifest containing source PDF paths and ground-truth parameter labels")
    parser.add_argument("--output", type=Path, help="write metrics to this JSON file (otherwise print to stdout)")
    parser.add_argument("--tolerance", type=float, default=1e-6, help="absolute numeric match tolerance (default: 1e-6)")
    args = parser.parse_args()
    report = evaluate_manifest(args.manifest, args.tolerance)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
