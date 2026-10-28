"""Server-rendered user workflow for project upload, validation, and analysis."""
import os
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (Project, Document, ExtractedParameter, ParameterSource, ParameterConflict,
                     ParameterCorrection, AnalysisRun, StressScenario, AnalysisResult, AuditEvent)
from .views import _audit, _valid_parameter_value, process_document_record

@login_required
def dashboard(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Enter a project name.")
        else:
            project = Project.objects.create(owner=request.user, name=name[:200],
                                             description=request.POST.get("description", ""))
            _audit(project, request.user, "project_created")
            return redirect("project-page", project_id=project.id)
    projects = list(Project.objects.filter(owner=request.user).order_by("-updated_at"))
    for project in projects:
        project.latest_analysis = project.analyses.order_by("-created_at").first()
        project.pending_parameter_count = project.parameters.exclude(
            validation_status__in=("validated", "corrected")).count()
        project.open_conflict_count = project.conflicts.filter(status="requires_engineer_review").count()
        project.report_count = project.reports.count()
    return render(request, "webdata/dashboard.html", {"projects": projects})

@login_required
def project_page(request, project_id):
    project = get_object_or_404(Project, pk=project_id, owner=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "upload":
            uploaded = request.FILES.get("file")
            ext = os.path.splitext(uploaded.name)[1].lower() if uploaded else ""
            if not uploaded or ext not in (".pdf", ".ifc") or uploaded.size <= 0 or uploaded.size > 50*1024*1024:
                messages.error(request, "Choose a non-empty PDF or IFC file (maximum 50 MB).")
            else:
                doc = Document.objects.create(project=project, uploader=request.user, file=uploaded,
                    original_filename=os.path.basename(uploaded.name)[:255], file_type=ext[1:], file_size=uploaded.size)
                _audit(project, request.user, "document_uploaded",
                       {"document_id": doc.id, "filename": doc.original_filename})
                try:
                    outcome = process_document_record(doc, request.user)
                    doc.refresh_from_db()
                    ocr_unavailable = any(page.get("method") == "tesseract_unavailable"
                        for page in doc.extraction_metadata.get("pages", []))
                    if ocr_unavailable:
                        messages.warning(request, "Processed %s, but Tesseract OCR is unavailable; no text was extracted from its scanned page(s). Install Tesseract and retry the document." % doc.original_filename)
                    else:
                        messages.success(request, "Processed %s; found %d parameters." % (doc.original_filename, len(outcome["extracted_parameters"])))
                    interpretation = doc.extraction_metadata.get("interpretation", {})
                    if interpretation.get("status") == "request_failed":
                        messages.warning(request, "Groq/LLaMA was attempted but failed (%s); explicit local extraction results were retained." % interpretation.get("failure_type", "request error"))
                except Exception as exc:
                    messages.error(request, "Document processing failed: %s" % exc)
        elif action == "review":
            from document_intelligence.parameter_extractor import PARAM_SPEC
            for name, spec in PARAM_SPEC.items():
                decision = request.POST.get("action_" + name, "skip")
                if decision == "skip":
                    continue
                had_open_conflict = project.conflicts.filter(
                    parameter_name=name, status="requires_engineer_review").exists()
                value_text = request.POST.get("value_" + name, "").strip()
                parameter = project.parameters.filter(name=name).first()
                if decision == "correct":
                    try:
                        value = float(value_text)
                    except ValueError:
                        messages.error(request, "%s needs a numeric value." % name)
                        continue
                    if not _valid_parameter_value(name, value, PARAM_SPEC):
                        messages.error(request, "%s is outside the supported range." % name)
                        continue
                    if parameter is None:
                        parameter = ExtractedParameter.objects.create(project=project, name=name,
                            value=value, unit=spec["unit"], extraction_method="engineer entered",
                            validation_status="corrected")
                        old_value = None
                    else:
                        old_value = parameter.value
                        parameter.value, parameter.validation_status = value, "corrected"
                        parameter.save()
                    ParameterCorrection.objects.create(parameter=parameter, original_value=old_value,
                        corrected_value=value, user=request.user, reason=request.POST.get("reason_" + name, ""))
                    _audit(project, request.user, "parameter_corrected",
                           {"parameter": name, "original_value": old_value, "corrected_value": value})
                    ParameterConflict.objects.filter(project=project, parameter_name=name).update(
                        status="resolved", resolved_by=request.user, resolved_at=timezone.now())
                elif parameter is not None and decision == "confirm":
                    if not _valid_parameter_value(name, parameter.value, PARAM_SPEC):
                        messages.error(request, "%s is outside its supported range; correct it before confirming." % name)
                        continue
                    parameter.validation_status = "validated"
                    parameter.save(update_fields=["validation_status", "updated_at"])
                    ParameterConflict.objects.filter(project=project, parameter_name=name).update(
                        status="resolved", resolved_by=request.user, resolved_at=timezone.now())
                elif parameter is not None and decision == "reject":
                    parameter.validation_status = "rejected"
                    parameter.save(update_fields=["validation_status", "updated_at"])
                    ParameterConflict.objects.filter(project=project, parameter_name=name).update(
                        status="rejected", resolved_by=request.user, resolved_at=timezone.now())
                elif decision in ("confirm", "reject"):
                    messages.error(request, "%s has no extracted value; use Correct to enter one." % name)
                if decision == "confirm" and parameter is not None:
                    _audit(project, request.user, "parameter_validated", {"parameter": name, "value": parameter.value})
                elif decision == "reject" and parameter is not None:
                    _audit(project, request.user, "parameter_rejected", {"parameter": name, "value": parameter.value})
                if had_open_conflict and decision in ("confirm", "correct", "reject") and parameter is not None:
                    _audit(project, request.user, "conflict_resolved",
                           {"parameter": name, "resolution": decision, "value": parameter.value})
            _audit(project, request.user, "parameter_review_submitted")
            messages.success(request, "Parameter review saved.")
        elif action == "analyze":
            params = {p.name: p.value for p in project.parameters.all()
                      if p.validation_status in ("validated", "corrected")}
            from environment.building_env import PARAM_KEYS
            from document_intelligence.parameter_extractor import PARAM_SPEC
            missing = [key for key in PARAM_KEYS if key not in params or params[key] is None]
            if missing:
                messages.error(request, "Validate or enter all 18 parameters before analysis. Still missing: " + ", ".join(missing))
            elif any(not _valid_parameter_value(key, params[key], PARAM_SPEC) for key in PARAM_KEYS):
                messages.error(request, "One or more stored parameter values are outside the supported schema. Correct them before analysis.")
            else:
                try:
                    from analysis.service import StructuralAnalysisService
                    chosen = request.POST.get("scenario", "all")
                    from environment.building_env import ACTION_NAMES
                    scenario_id = None if chosen == "all" else int(chosen)
                    if scenario_id is not None and scenario_id not in ACTION_NAMES:
                        raise ValueError("Unknown stress scenario")
                    ppo_timesteps = int(request.POST.get("ppo_timesteps", 1024))
                    if not 512 <= ppo_timesteps <= 10000:
                        raise ValueError("PPO timesteps must be between 512 and 10000")
                    result = StructuralAnalysisService().analyze({key: float(value) for key, value in params.items()},
                        scenario=scenario_id, include_ppo=request.POST.get("include_ppo") == "on",
                        ppo_timesteps=ppo_timesteps)
                    run = AnalysisRun.objects.create(project=project, initiated_by=request.user,
                        status="completed", scenario=ACTION_NAMES[scenario_id] if scenario_id is not None else "all implemented scenarios",
                        input_parameters=params, result=result)
                    AnalysisResult.objects.create(analysis=run, overall_risk=result["overall_risk_score"],
                        risk_label=result["risk_label"], result_data=result)
                    for scenario_name, scenario_result in result["scenario_results"].items():
                        StressScenario.objects.create(analysis=run, name=scenario_name,
                            inputs=params, result=scenario_result)
                    _audit(project, request.user, "analysis_completed", {"analysis_id": str(run.id)})
                    _audit(project, request.user, "scenario_analysis", {
                        "analysis_id": str(run.id), "scenario_names": list(result["scenario_results"]),
                        "scenario_count": len(result["scenario_results"])})
                    messages.success(request, "Analysis %s completed." % run.id)
                except Exception as exc:
                    failed = AnalysisRun.objects.create(project=project, initiated_by=request.user,
                        status="failed", scenario="all implemented scenarios", input_parameters=params,
                        result={"error": str(exc)[:1000]})
                    _audit(project, request.user, "analysis_failed", {"analysis_id": str(failed.id), "error": str(exc)[:300]})
                    messages.error(request, "Analysis failed: %s" % exc)
        return redirect("project-page", project_id=project.id)
    from document_intelligence.parameter_extractor import PARAM_SPEC
    existing = {p.name: p for p in project.parameters.all()}
    from environment.building_env import PARAM_KEYS
    recent_runs = list(project.analyses.filter(status="completed").order_by("-created_at")[:2])
    comparison_parameters = []
    comparison_scenarios = []
    latest_conflicts = {}
    for conflict in project.conflicts.order_by("-id"):
        latest_conflicts.setdefault(conflict.parameter_name, conflict)
    if len(recent_runs) == 2:
        modified_run, base_run = recent_runs
        comparison_ids = {"base_analysis_id": str(base_run.id),
                          "modified_analysis_id": str(modified_run.id)}
        if not any(event.details == comparison_ids for event in project.audit_events.filter(
                action="configurations_compared").only("details")):
            _audit(project, request.user, "configurations_compared", comparison_ids)
        from document_intelligence.parameter_extractor import PARAM_SPEC
        comparison_parameters = [{"name": key, "label": PARAM_SPEC[key]["label"],
            "base": base_run.input_parameters.get(key), "modified": modified_run.input_parameters.get(key)}
            for key in PARAM_KEYS]
        base_scenarios = base_run.result.get("scenario_results", {})
        modified_scenarios = modified_run.result.get("scenario_results", {})
        comparison_scenarios = [{"name": name,
            "base": "PASS" if item.get("passed") is True else "REVIEW" if item.get("passed") is False else "N/A",
            "modified": "PASS" if modified_scenarios.get(name, {}).get("passed") is True else
                        "REVIEW" if modified_scenarios.get(name, {}).get("passed") is False else "N/A"}
            for name, item in base_scenarios.items()]
    review_fields = [{"name": name, "label": spec["label"], "value": existing[name].value if name in existing else "",
        "status": existing[name].validation_status if name in existing else "unavailable",
        "min": spec["min"], "max": spec["max"], "sources": list(ParameterSource.objects.filter(
            parameter=existing[name]).select_related("document")) if name in existing else []} for name, spec in PARAM_SPEC.items()]
    return render(request, "webdata/project.html", {"project": project, "documents": project.documents.order_by("-uploaded_at"),
        "fields": review_fields, "conflicts": list(reversed(list(latest_conflicts.values()))),
        "analyses": project.analyses.order_by("-created_at")[:20], "audit": project.audit_events.order_by("-created_at")[:30],
        "comparison_runs": recent_runs, "comparison_parameters": comparison_parameters,
        "comparison_scenarios": comparison_scenarios,
        "groq_key_configured": bool(os.environ.get("GROQ_API_KEY", "").strip())})

@login_required
def project_visualization(request, project_id):
    project = get_object_or_404(Project, pk=project_id, owner=request.user)
    values = {p.name: p.value for p in project.parameters.filter(validation_status__in=("validated", "corrected"))}
    if "num_floors" not in values:
        messages.error(request, "Validate the number of floors before opening the structural model.")
        return redirect("project-page", project_id=project.id)
    from reporting.structure_model import build_frame
    latest = project.analyses.order_by("-created_at").first()
    return render(request, "webdata/model.html", {"project": project, "model": build_frame(values),
        "risks": latest.result.get("element_risks", {}) if latest else {}, "latest": latest})


@login_required
def project_demo_video(request, project_id):
    """Generate and download the fixed demo from the existing reporting module."""
    if request.method != "POST":
        return redirect("project-page", project_id=project_id)
    project = get_object_or_404(Project, pk=project_id, owner=request.user)
    try:
        from reporting.demo_video import generate_demo_video
        output_dir = settings.MEDIA_ROOT / "demo-videos" / str(uuid.uuid4())
        path = generate_demo_video(output_dir)
        _audit(project, request.user, "demo_video_generated", {"format": path.suffix.lstrip(".")})
        content_type = "video/mp4" if path.suffix == ".mp4" else "image/gif"
        return FileResponse(open(path, "rb"), as_attachment=True,
                            filename=path.name, content_type=content_type)
    except Exception as exc:
        messages.error(request, "Demo export failed: %s" % str(exc)[:300])
        return redirect("project-page", project_id=project.id)
