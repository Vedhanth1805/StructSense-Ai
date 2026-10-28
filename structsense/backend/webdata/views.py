"""Authenticated, project-scoped API endpoints for the persistent data service."""
import csv
import os
import re
import sys
import tempfile
from collections import defaultdict

from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (Project, Document, DocumentSource, ExtractedParameter, ParameterSource,
                     ParameterConflict, ParameterCorrection, AnalysisRun, StressScenario,
                     AnalysisResult, AuditEvent)
from .serializers import ProjectSerializer, DocumentSerializer, AnalysisSerializer

CORE_DIR = str(settings.BASE_DIR.parent)
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

def _project(request, project_id):
    return get_object_or_404(Project, pk=project_id, owner=request.user)

def _audit(project, actor, action, details=None):
    AuditEvent.objects.create(project=project, actor=actor, action=action, details=details or {})

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def projects(request):
    if request.method == "GET":
        qs = Project.objects.filter(owner=request.user).annotate(document_count=Count("documents"), analysis_count=Count("analyses"))
        return Response(ProjectSerializer(qs, many=True).data)
    name = str(request.data.get("name", "")).strip()
    if not name:
        return Response({"error": "Project name is required"}, status=400)
    project = Project.objects.create(owner=request.user, name=name[:200], description=str(request.data.get("description", "")))
    _audit(project, request.user, "project_created")
    return Response(ProjectSerializer(project).data, status=201)

@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def project_detail(request, project_id):
    project = _project(request, project_id)
    if request.method == "GET":
        return Response(ProjectSerializer(project).data)
    if request.method == "DELETE":
        _audit(project, request.user, "project_deleted")
        project.delete()
        return Response(status=204)
    if "name" in request.data:
        project.name = str(request.data["name"])[:200]
    if "description" in request.data:
        project.description = str(request.data["description"])
    project.save()
    _audit(project, request.user, "project_updated")
    return Response(ProjectSerializer(project).data)

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def documents(request, project_id):
    project = _project(request, project_id)
    if request.method == "GET":
        return Response(DocumentSerializer(project.documents.order_by("-uploaded_at"), many=True).data)
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response({"error": "Upload a PDF or IFC file using field 'file'"}, status=400)
    ext = os.path.splitext(uploaded.name)[1].lower()
    if ext not in (".pdf", ".ifc"):
        return Response({"error": "Only PDF and IFC files are accepted"}, status=400)
    if uploaded.size <= 0 or uploaded.size > 50 * 1024 * 1024:
        return Response({"error": "File must be between 1 byte and 50 MB"}, status=400)
    # Content signatures are checked when processing; never serve uploads publicly.
    document = Document.objects.create(project=project, uploader=request.user, file=uploaded,
        original_filename=os.path.basename(uploaded.name)[:255], file_type=ext[1:], file_size=uploaded.size)
    _audit(project, request.user, "document_uploaded", {"document_id": document.id, "filename": document.original_filename})
    return Response(DocumentSerializer(document).data, status=201)

def process_document_record(document, actor):
    document.processing_status, document.processing_error = "processing", ""
    document.save(update_fields=["processing_status", "processing_error"])
    try:
        if document.file_type == "pdf":
            with open(document.file.path, "rb") as stream:
                if b"%PDF-" not in stream.read(1024):
                    raise ValueError("File content does not match PDF format")
            from document_intelligence.pdf_ingester import PDFIngester
            ingested = PDFIngester().extract_text_from_pdf(document.file.path)
            if ingested.get("error"):
                raise ValueError(ingested["error"])
            from document_intelligence.parameter_extractor import ParameterExtractor, PARAM_SPEC
            extracted = ParameterExtractor().extract(os.environ.get("GROQ_API_KEY", ""), ingested.get("full_text", ""), document.original_filename)
            for record in extracted["parameters"].values():
                quote = " ".join(str(record.get("source_text", "")).lower().split())
                if not quote:
                    continue
                for page in ingested.get("pages", []):
                    page_text = " ".join(str(page.get("text", "")).lower().split())
                    if quote in page_text:
                        record["source_location"] = "Page %s" % page.get("page_num")
                        break
            method = ",".join(sorted({p["method"] for p in ingested.get("pages", [])})) or "pymupdf"
            metadata = {k: v for k, v in ingested.items() if k != "full_text"}
            metadata["interpretation"] = extracted["interpretation"]
            source_records = extracted["parameters"]
        else:
            with open(document.file.path, "rb") as stream:
                header = stream.read(24).decode("ascii", "ignore")
            if "ISO-10303-21" not in header:
                raise ValueError("File content does not have an IFC STEP header")
            from document_intelligence.ifc_ingester import IFCIngester
            bim = IFCIngester().extract(document.file.path)
            metadata = {"counts": bim["counts"], "object_count": len(bim["objects"]), "objects": bim["objects"],
                        "interpretation": {"provider": "not_applicable", "status": "not_applicable",
                                           "label": "Not used for IFC/BIM processing"}}
            source_records = bim["parameters"]
            method = "ifcopenshell"
        source_rows = DocumentSource.objects.filter(document=document, locator="")
        if source_rows.exists():
            source_rows.update(method=method, excerpt="")
        else:
            DocumentSource.objects.create(document=document, locator="", method=method)
        _persist_sources(document, source_records, actor)
        document.extraction_metadata = metadata
        document.processing_status = "processed"
        document.save(update_fields=["extraction_metadata", "processing_status"])
        _audit(document.project, actor, "document_processed", {"document_id": document.id, "parameter_count": len(source_records)})
        return {"document": DocumentSerializer(document).data, "extracted_parameters": source_records,
                "conflicts": list(document.project.conflicts.values("parameter_name", "competing_values", "status"))}
    except Exception as exc:
        document.processing_status, document.processing_error = "failed", str(exc)[:2000]
        document.save(update_fields=["processing_status", "processing_error"])
        _audit(document.project, actor, "document_processing_failed",
               {"document_id": document.id, "error": str(exc)[:300]})
        raise

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_document(request, document_id):
    document = get_object_or_404(Document.objects.select_related("project"), pk=document_id, project__owner=request.user)
    try:
        return Response(process_document_record(document, request.user))
    except Exception as exc:
        return Response({"error": document.processing_error or str(exc), "status": "failed"}, status=422)

@transaction.atomic
def _persist_sources(document, records, actor=None):
    project = document.project
    from document_intelligence.parameter_extractor import PARAM_SPEC
    from document_intelligence.fusion import fuse_parameter_sources
    for name, record in records.items():
        parameter, created = ExtractedParameter.objects.get_or_create(project=project, name=name,
            defaults={"value": record.get("value"), "unit": PARAM_SPEC.get(name, {}).get("unit", ""),
                      "extraction_method": record.get("method", "unknown"),
                      "confidence": record.get("confidence"), "confidence_kind": record.get("confidence_kind", "not provided")})
        previous_sources = ParameterSource.objects.filter(parameter=parameter).select_related("document")
        candidates = [{"parameters": {name: {"value": row.value,
                         "source_text": row.source_text, "source_document": row.document.original_filename,
                         "method": row.extraction_method, "confidence": row.confidence}}} for row in previous_sources]
        if not created and not candidates:
            candidates = [{"parameters": {name: {"value": parameter.value, "source_document": "previous source"}}}]
        candidates.append({"parameters": {name: record}})
        fused = fuse_parameter_sources(candidates)
        has_conflict = bool(fused["conflicts"])
        if not created and has_conflict:
            conflict = ParameterConflict.objects.filter(project=project, parameter_name=name,
                status="requires_engineer_review").order_by("id").first()
            created_conflict = conflict is None
            if conflict:
                conflict.competing_values = fused["conflicts"][0]["values"]
                conflict.save(update_fields=["competing_values"])
            else:
                ParameterConflict.objects.create(project=project, parameter_name=name,
                    competing_values=fused["conflicts"][0]["values"])
            if created_conflict and actor is not None:
                _audit(project, actor, "parameter_conflict_detected",
                       {"parameter": name, "document_id": document.id})
            parameter.validation_status = "conflict"
        elif not created and parameter.validation_status not in ("validated", "corrected"):
            parameter.validation_status = "pending"
        parameter.save()
        ParameterSource.objects.update_or_create(parameter=parameter, document=document,
            defaults={"value": record.get("value"), "source_text": str(record.get("source_text", "")),
                      "source_location": str(record.get("source_location", "")),
                      "extraction_method": record.get("method", "unknown"), "confidence": record.get("confidence")})


def _valid_parameter_value(name, value, specs):
    try:
        numeric = float(value)
        if not specs[name]["min"] <= numeric <= specs[name]["max"]:
            return False
        return name not in ("num_floors", "seismic_zone", "shear_wall_present", "foundation_type") or numeric.is_integer()
    except (KeyError, TypeError, ValueError):
        return False

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def parameters(request, project_id):
    project = _project(request, project_id)
    output = []
    for p in project.parameters.order_by("name"):
        source_rows = ParameterSource.objects.filter(parameter=p).select_related("document")
        output.append({"name": p.name, "value": p.value, "unit": p.unit, "method": p.extraction_method,
            "confidence": p.confidence, "confidence_kind": p.confidence_kind, "validation_status": p.validation_status,
            "sources": [{"document": src.document.original_filename, "value": src.value, "quote": src.source_text,
                         "location": src.source_location, "method": src.extraction_method,
                         "confidence": src.confidence} for src in source_rows]})
    return Response({"parameters": output, "conflicts": list(project.conflicts.values("id", "parameter_name", "competing_values", "status"))})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def review_parameters(request, project_id):
    project = _project(request, project_id)
    updates = request.data.get("parameters", {})
    if not isinstance(updates, dict):
        return Response({"error": "parameters must be an object"}, status=400)
    from document_intelligence.parameter_extractor import PARAM_SPEC
    for name, change in updates.items():
        if not isinstance(change, dict):
            return Response({"error": "Each parameter review must be an object", "parameter": name}, status=400)
        try:
            parameter = project.parameters.get(name=name)
        except ExtractedParameter.DoesNotExist:
            if name not in PARAM_SPEC or change.get("action") != "correct" or change.get("value") is None:
                return Response({"error": "Unknown parameter must be a schema field entered with action=correct and a value: " + name}, status=400)
            if not _valid_parameter_value(name, change["value"], PARAM_SPEC):
                return Response({"error": "Value is outside the supported range", "parameter": name}, status=400)
            numeric_value = float(change["value"])
            parameter = ExtractedParameter.objects.create(project=project, name=name, value=numeric_value,
                unit=PARAM_SPEC[name]["unit"],
                extraction_method="engineer entered", validation_status="corrected")
            ParameterCorrection.objects.create(parameter=parameter, original_value=None,
                corrected_value=numeric_value, user=request.user, reason=str(change.get("reason", "")))
            _audit(project, request.user, "parameter_entered", {"parameter": name, "value": numeric_value})
            continue
        action = change.get("action")
        had_open_conflict = project.conflicts.filter(
            parameter_name=name, status="requires_engineer_review").exists()
        if action == "confirm":
            if name not in PARAM_SPEC or not _valid_parameter_value(name, parameter.value, PARAM_SPEC):
                return Response({"error": "This value is outside the supported parameter range; correct it before confirming",
                                 "parameter": name}, status=400)
            parameter.validation_status = "validated"
        elif action == "correct":
            value = change.get("value")
            if value is None:
                return Response({"error": "Correction requires a value", "parameter": name}, status=400)
            if name not in PARAM_SPEC or not _valid_parameter_value(name, value, PARAM_SPEC):
                return Response({"error": "Value is outside the supported range", "parameter": name}, status=400)
            numeric_value = float(value)
            ParameterCorrection.objects.create(parameter=parameter, original_value=parameter.value,
                corrected_value=numeric_value, user=request.user, reason=str(change.get("reason", "")))
            parameter.value, parameter.validation_status = numeric_value, "corrected"
        elif action == "reject":
            parameter.validation_status = "rejected"
        else:
            return Response({"error": "action must be confirm, correct, or reject", "parameter": name}, status=400)
        parameter.save()
        if action in ("confirm", "correct"):
            ParameterConflict.objects.filter(project=project, parameter_name=name).update(status="resolved", resolved_by=request.user, resolved_at=timezone.now())
        elif action == "reject":
            ParameterConflict.objects.filter(project=project, parameter_name=name).update(status="rejected", resolved_by=request.user, resolved_at=timezone.now())
        _audit(project, request.user, "parameter_" + action, {"parameter": name, "value": parameter.value, "reason": change.get("reason", "")})
        if action == "confirm":
            _audit(project, request.user, "parameter_validated", {"parameter": name, "value": parameter.value})
        if had_open_conflict:
            _audit(project, request.user, "conflict_resolved",
                   {"parameter": name, "resolution": action, "value": parameter.value})
    return Response({"status": "saved", "parameters": list(project.parameters.values("name", "value", "validation_status"))})

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def analyses(request, project_id):
    project = _project(request, project_id)
    if request.method == "GET":
        return Response(AnalysisSerializer(project.analyses.order_by("-created_at"), many=True).data)
    from environment.building_env import PARAM_KEYS, ACTION_NAMES
    params = {p.name: p.value for p in project.parameters.all() if p.validation_status in ("validated", "corrected")}
    missing = [k for k in PARAM_KEYS if k not in params or params[k] is None]
    if missing:
        return Response({"error": "Engineer validation is required before analysis", "unavailable_or_unvalidated": missing}, status=409)
    from document_intelligence.parameter_extractor import PARAM_SPEC
    invalid = [k for k in PARAM_KEYS if not _valid_parameter_value(k, params[k], PARAM_SPEC)]
    if invalid:
        return Response({"error": "Stored values outside the supported parameter schema must be corrected",
                         "invalid_parameters": invalid}, status=422)
    scenario = request.data.get("scenario")
    scenario_id = None
    if scenario is not None:
        if isinstance(scenario, str):
            scenario_id = next((i for i, n in ACTION_NAMES.items() if n == scenario), None)
            if scenario_id is None:
                try:
                    scenario_id = int(scenario)
                except ValueError:
                    pass
        else:
            try:
                scenario_id = int(scenario)
            except (ValueError, TypeError):
                scenario_id = None
        if scenario_id not in ACTION_NAMES:
            return Response({"error": "Unknown stress scenario"}, status=400)
    ppo_timesteps = request.data.get("ppo_timesteps", 1024)
    try:
        ppo_timesteps = max(512, min(10000, int(ppo_timesteps)))
    except (TypeError, ValueError):
        return Response({"error": "ppo_timesteps must be an integer"}, status=400)
    run = None
    try:
        from analysis.service import StructuralAnalysisService
        include_ppo = request.data.get("include_ppo", False) is True
        run = AnalysisRun.objects.create(project=project, initiated_by=request.user, status="running",
            scenario=ACTION_NAMES[scenario_id] if scenario_id is not None else "all implemented scenarios",
            input_parameters=params, result={})
        result = StructuralAnalysisService().analyze({k: float(v) for k, v in params.items()}, scenario_id,
                                                       include_ppo=include_ppo, ppo_timesteps=ppo_timesteps)
        run.status, run.result = "completed", result
        run.save(update_fields=["status", "result"])
        AnalysisResult.objects.create(analysis=run, overall_risk=result["overall_risk_score"],
                                      risk_label=result["risk_label"], result_data=result)
        for name, detail in result["scenario_results"].items():
            StressScenario.objects.create(analysis=run, name=name, inputs=params, result=detail,
                risk_result=None)
        _audit(project, request.user, "analysis_completed", {"analysis_id": str(run.id), "risk": result["overall_risk_score"]})
        _audit(project, request.user, "scenario_analysis", {
            "analysis_id": str(run.id), "scenario_names": list(result["scenario_results"]),
            "scenario_count": len(result["scenario_results"])})
        return Response(AnalysisSerializer(run).data, status=201)
    except Exception as exc:
        if run is not None:
            run.status, run.result = "failed", {"error": str(exc)[:1000]}
            run.save(update_fields=["status", "result"])
            _audit(project, request.user, "analysis_failed", {"analysis_id": str(run.id), "error": str(exc)[:300]})
        return Response({"error": str(exc), "analysis_id": str(run.id) if run else None, "status": "failed"}, status=422)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analysis_detail(request, analysis_id):
    run = get_object_or_404(AnalysisRun.objects.select_related("project"), pk=analysis_id, project__owner=request.user)
    return Response(AnalysisSerializer(run).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_csv(request, project_id):
    project = _project(request, project_id)
    _audit(project, request.user, "csv_exported")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="structsense-project-%s.csv"' % project.id
    writer = csv.writer(response)
    def safe_cell(value):
        text = str(value)
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else value
    writer.writerow(["project", "parameter", "value", "unit", "source", "method", "confidence", "validation_status", "scenario", "risk_result", "timestamp"])
    runs = list(project.analyses.order_by("created_at"))
    for parameter_record in project.parameters.order_by("name"):
        source_rows = list(ParameterSource.objects.filter(parameter=parameter_record).select_related("document"))
        source_names = ", ".join("%s%s" % (row.document.original_filename,
            (" (" + row.source_location + ")") if row.source_location else "") for row in source_rows)
        emitted = False
        for run in runs:
            scenarios = run.result.get("scenario_results", {}) or {"": {}}
            if parameter_record.name not in run.input_parameters:
                continue
            for scenario, details in scenarios.items():
                outcome = "PASS" if details.get("passed") is True else "FAIL" if details.get("passed") is False else "Unavailable"
                result = "Project score %s/100 (%s); scenario %s" % (
                    run.result.get("overall_risk_score", "Unavailable"), run.result.get("risk_label", "Unavailable"), outcome)
                writer.writerow([safe_cell(project.name), safe_cell(parameter_record.name), parameter_record.value,
                    safe_cell(parameter_record.unit), safe_cell(source_names), safe_cell(parameter_record.extraction_method),
                    parameter_record.confidence if parameter_record.confidence is not None else "",
                    safe_cell(parameter_record.validation_status), safe_cell((scenario + ": " + outcome).strip(": ")),
                    safe_cell(result), run.created_at.isoformat()])
                emitted = True
        if not emitted:
            writer.writerow([safe_cell(project.name), safe_cell(parameter_record.name), parameter_record.value,
                safe_cell(parameter_record.unit), safe_cell(source_names), safe_cell(parameter_record.extraction_method),
                parameter_record.confidence if parameter_record.confidence is not None else "",
                safe_cell(parameter_record.validation_status), "", "Analysis unavailable", ""])
    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request, project_id):
    project = _project(request, project_id)
    last = project.analyses.order_by("-created_at").first()
    return Response({"project": ProjectSerializer(project).data,
        "documents": DocumentSerializer(project.documents.all(), many=True).data,
        "parameter_count": project.parameters.count(), "conflict_count": project.conflicts.filter(status="requires_engineer_review").count(),
        "pending_validation_count": project.parameters.exclude(validation_status__in=["validated", "corrected"]).count(),
        "latest_analysis": AnalysisSerializer(last).data if last else None,
        "audit": list(project.audit_events.order_by("-created_at").values("action", "details", "created_at")[:50])})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def project_model(request, project_id):
    project = _project(request, project_id)
    values = {p.name: p.value for p in project.parameters.filter(validation_status__in=("validated", "corrected"))}
    if "num_floors" not in values:
        return Response({"error": "Engineer-validated floor count is required to build the model"}, status=409)
    from reporting.structure_model import build_frame
    return Response(build_frame(values))

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def compare(request, project_id):
    project = _project(request, project_id)
    from environment.building_env import PARAM_KEYS
    from analysis.service import StructuralAnalysisService
    from reporting.structure_model import build_frame, compare_configurations
    configs = [request.data.get("configuration_a"), request.data.get("configuration_b")]
    if not all(isinstance(c, dict) for c in configs):
        return Response({"error": "configuration_a and configuration_b objects are required"}, status=400)
    from document_intelligence.parameter_extractor import PARAM_SPEC
    for label, config in zip(("configuration_a", "configuration_b"), configs):
        missing = [key for key in PARAM_KEYS if key not in config or config[key] is None]
        if missing:
            return Response({"error": "%s is incomplete; unavailable parameters: %s" % (label, ", ".join(missing))}, status=400)
        extra = sorted(set(config) - set(PARAM_KEYS))
        if extra:
            return Response({"error": "%s includes unsupported parameter names: %s" % (label, ", ".join(extra))}, status=400)
        invalid = [key for key in PARAM_KEYS if not _valid_parameter_value(key, config[key], PARAM_SPEC)]
        if invalid:
            return Response({"error": "%s has invalid parameter values: %s" % (label, ", ".join(invalid))}, status=400)
    try:
        a, b = ({key: float(value) for key, value in config.items()} for config in configs)
        service = StructuralAnalysisService()
        result_a, result_b = service.analyze(a), service.analyze(b)
        _audit(project, request.user, "configurations_compared", {
            "configuration_a_risk": result_a["overall_risk_score"],
            "configuration_b_risk": result_b["overall_risk_score"]})
        return Response({"parameter_differences": compare_configurations(a, b),
            "model_a": build_frame(a), "model_b": build_frame(b),
            "analysis_a": result_a, "analysis_b": result_b,
            "risk_difference": result_b["overall_risk_score"] - result_a["overall_risk_score"],
            "note": "Only the repository's implemented stress checks and risk scorer are compared; visualization is illustrative, not FEA."})
    except Exception as exc:
        return Response({"error": str(exc)}, status=422)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analysis_report(request, analysis_id):
    from django.core.files.base import ContentFile
    from django.http import FileResponse
    from .models import Report
    run = get_object_or_404(AnalysisRun.objects.select_related("project"), pk=analysis_id, project__owner=request.user)
    if run.status != "completed":
        return Response({"error": "Only completed analyses can be reported", "status": run.status}, status=409)
    project = run.project
    parameter_rows = []
    for p in project.parameters.order_by("name"):
        source_rows = ParameterSource.objects.filter(parameter=p).select_related("document")
        parameter_rows.append({"name": p.name, "value": p.value, "unit": p.unit, "method": p.extraction_method,
            "confidence": p.confidence, "confidence_kind": p.confidence_kind, "status": p.validation_status,
            "sources": [row.document.original_filename for row in source_rows],
            "source_locations": [row.source_location for row in source_rows if row.source_location]})
    corrections = ParameterCorrection.objects.filter(parameter__project=project).select_related("parameter", "user").order_by("created_at")
    try:
        from reporting.service import generate_analysis_pdf
        pdf = generate_analysis_pdf(project, run, list(project.documents.order_by("uploaded_at")), parameter_rows,
                                    list(project.conflicts.order_by("id")), list(corrections),
                                    list(project.audit_events.select_related("actor").order_by("created_at")))
        report = Report(project=project, analysis=run, format="pdf")
        report.file.save("structsense-%s.pdf" % run.id, ContentFile(pdf), save=True)
        _audit(project, request.user, "report_generated", {"analysis_id": str(run.id), "report_id": report.id})
        response = FileResponse(report.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="structsense-%s.pdf"' % run.id
        return response
    except Exception as exc:
        _audit(project, request.user, "report_generation_failed",
               {"analysis_id": str(run.id), "error": str(exc)[:300]})
        return Response({"error": "Report generation failed: %s" % exc}, status=422)
