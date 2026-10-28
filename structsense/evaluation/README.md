# Paper benchmark evaluation harness

The repository does not contain the original NH-48 documents or ground-truth evaluation table, so no paper benchmark result is claimed. `nh48_benchmark.py` provides a data-driven extraction evaluation path for when authorized source documents and labels are supplied. It runs the current PDF text/OCR ingester and parameter extractor, then reports field accuracy and extraction coverage separately. It does not infer labels or manufacture paper scenario results.

Create a JSONL manifest, one record per PDF. Paths are relative to the manifest:

```json
{"document_id":"NH48-001","document_path":"documents/NH48-001.pdf","ground_truth_parameters":{"concrete_grade":30,"steel_grade":500}}
```

Then run from the repository root:

```bash
python -m evaluation.nh48_benchmark /path/to/authorized-nh48-manifest.jsonl --output /path/to/nh48-results.json
```

Only keys in the existing supported parameter schema are accepted. Numeric values use an absolute match tolerance of `1e-6` by default (`--tolerance` can override it). The output includes document count, field accuracy, field coverage, and per-parameter metrics. Any resulting score is only attributable to the dataset actually supplied; it is a reproduction of the paper benchmark only if the supplied documents and labels are the original NH-48 benchmark material.
