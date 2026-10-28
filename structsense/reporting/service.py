"""Auditable PDF export for persisted project analyses."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

def generate_analysis_pdf(project, analysis, documents, parameters, conflicts, corrections, audit_events=()):
    """Build a report from persisted facts; unavailable model outputs stay explicit."""
    result = analysis.result or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    story = [Paragraph("StructSense AI - Structural Risk Assessment", styles["Title"]),
             Paragraph("Decision-support / research prototype. Not a substitute for professional structural engineering, statutory approval, formal design verification, or validated FEA.", styles["BodyText"]), Spacer(1, 8)]
    story += [Paragraph("Project and analysis", styles["Heading2"]),
              _table([["Project", project.name], ["Analysis ID", str(analysis.id)], ["Created (UTC)", analysis.created_at.isoformat()],
                      ["Scenario", analysis.scenario], ["Risk score", str(result.get("overall_risk_score", "Unavailable"))],
                      ["Risk label", str(result.get("risk_label", "Unavailable"))],
                      ["Aggregate formula", str((result.get("aggregate_risk_formula") or {}).get("formula", "Historical result; formula metadata unavailable"))]])]
    story += [Paragraph("Input documents", styles["Heading2"]), _table([["Filename", "Type", "Status", "Extracted summary", "Uploaded"]] +
              [[d.original_filename, d.file_type.upper(), d.processing_status,
                str(d.extraction_metadata.get("counts",
                    {"pages": d.extraction_metadata.get("total_pages", "Unavailable"),
                     "BIM objects": d.extraction_metadata.get("object_count", "Unavailable")})),
                d.uploaded_at.isoformat()] for d in documents] or [["No documents", "", "", "", ""]])]
    bim_documents = [item for item in documents if item.file_type.lower() == "ifc"]
    if bim_documents:
        bim_rows = [["IFC/BIM document", "Object count", "Columns", "Beams", "Slabs", "Storeys"]]
        for item in bim_documents:
            counts = item.extraction_metadata.get("counts", {})
            bim_rows.append([item.original_filename, item.extraction_metadata.get("object_count", "Unavailable"),
                             counts.get("columns", "Unavailable"), counts.get("beams", "Unavailable"),
                             counts.get("slabs", "Unavailable"), counts.get("levels", "Unavailable")])
        story += [Paragraph("IFC / BIM summary", styles["Heading2"]), _table(bim_rows, small=True)]
        object_rows = [["Type", "Name", "Global ID"]]
        for item in bim_documents:
            for obj in item.extraction_metadata.get("objects", [])[:25]:
                object_rows.append([obj.get("type", "Unavailable"), obj.get("name", "Unavailable"),
                                    obj.get("global_id", "Unavailable")])
        if len(object_rows) > 1:
            story.append(_table(object_rows, small=True))
    story += [Paragraph("Parameter sources and validation", styles["Heading2"])]
    rows = [["Parameter", "Value", "Unit", "Source(s)", "Method", "Confidence (type)", "Status"]]
    for p in parameters:
        srcs = ", ".join(p["sources"])
        locations = ", ".join(p.get("source_locations", []))
        rows.append([p["name"], str(p["value"]), p.get("unit", ""),
                     (srcs + ((" · " + locations) if locations else "")) or "Engineer entered", p["method"],
                     (str(p["confidence"]) + " (" + p.get("confidence_kind", "not provided") + ")") if p["confidence"] is not None else "Unavailable", p["status"]])
    story.append(_table(rows, small=True))
    story += [Paragraph("Conflicts and engineer corrections", styles["Heading2"])]
    rows = [["Conflict", "Competing values", "Status"]]
    rows.extend([[c.parameter_name, str(c.competing_values), c.status] for c in conflicts])
    if len(rows) == 1: rows.append(["No conflicts recorded", "", ""])
    story.append(_table(rows, small=True))
    rows = [["Parameter", "Original", "Corrected", "Reason", "User", "Time"]]
    rows.extend([[c.parameter.name, str(c.original_value), str(c.corrected_value), c.reason,
                  c.user.get_username(), c.created_at.isoformat()] for c in corrections])
    if len(rows) == 1: rows.append(["No corrections recorded", "", "", "", "", ""])
    story += [Paragraph("Engineer corrections", styles["Heading3"]), _table(rows, small=True)]
    story += [Paragraph("Validated parameter set", styles["Heading2"]), _table([["Parameter", "Value", "Unit", "Validation"]] +
              [[p["name"], str(p["value"]), p.get("unit", ""), p["status"]] for p in parameters], small=True)]
    if analysis.input_parameters:
        try:
            from document_intelligence.parameter_extractor import PARAM_SPEC
            input_rows = [["Analysis parameter", "Value", "Unit"]]
            input_rows.extend([[name, str(value), PARAM_SPEC.get(name, {}).get("unit", "")]
                               for name, value in analysis.input_parameters.items()])
            story += [Paragraph("Analysis input snapshot", styles["Heading2"]), _table(input_rows, small=True)]
        except Exception:
            story += [Paragraph("Analysis input snapshot", styles["Heading2"]),
                      _table([["Parameter", "Value"]] +
                             [[name, str(value)] for name, value in analysis.input_parameters.items()], small=True)]
    story += [Paragraph("Structural checks and stress scenarios", styles["Heading2"])]
    scenario_rows = [["Scenario", "Outcome", "Details"]]
    for name, detail in result.get("scenario_results", {}).items():
        outcome = "PASS" if detail.get("passed") is True else "FAIL" if detail.get("passed") is False else "Unavailable"
        reason = detail.get("failure_reason", "")
        scenario_rows.append([name, outcome, reason or str({k:v for k,v in detail.items() if k not in ("passed", "failure_reason")})[:400]])
    if len(scenario_rows) == 1: scenario_rows.append(["No scenario results", "Unavailable", ""])
    story.append(_table(scenario_rows, small=True))
    story += [Paragraph("Risk assessment", styles["Heading2"]), _table([["Element", "Risk score (0-1)"]] +
              [[k, str(v)] for k, v in result.get("element_risks", {}).items()] or [["Unavailable", ""]])]
    if result.get("risk_contributions"):
        story += [Paragraph("Important risk factors (implemented scorer contributions)", styles["Heading3"]),
                  _table([["Factor", "Contribution"]] + [[k, str(v)] for k, v in result["risk_contributions"].items()])]
    try:
        from .structure_model import build_frame
        validated = {p["name"]: p["value"] for p in parameters if p["value"] is not None}
        frame = build_frame(validated)
        story += [Paragraph("3D visualization summary", styles["Heading2"]), _table([
            ["Representation", frame["classification"]], ["Floors", str(frame["floors"])],
            ["Illustrative nodes", str(len(frame["nodes"]))], ["Illustrative members", str(len(frame["members"]))],
            ["Illustrative slab panels", str(len(frame.get("slabs", [])))],
            ["Grid assumptions", str(frame["grid_assumptions"]) ]])]
    except Exception:
        story += [Paragraph("3D visualization summary: unavailable because validated geometry inputs are incomplete.", styles["BodyText"])]
    failed = [name for name, details in result.get("scenario_results", {}).items() if details.get("passed") is False]
    story += [Paragraph("Recommendations", styles["Heading2"])]
    if failed:
        story += [Paragraph(escape(_ascii("Have a licensed structural engineer review the failed implemented checks and their assumptions: " + ", ".join(failed) + ".")), styles["BodyText"])]
    else:
        story += [Paragraph("No scenario check failed. This simplified research assessment does not generate design recommendations.", styles["BodyText"])]
    if result.get("ppo"):
        ppo = result["ppo"]
        story += [Paragraph("PPO results", styles["Heading2"]),
                  _table([["Timesteps", str(ppo.get("training", {}).get("timesteps", "Unavailable"))],
                          ["Mean reward", str(ppo.get("evaluation", {}).get("mean_reward", "Unavailable"))],
                          ["Final mean risk", str(ppo.get("evaluation", {}).get("final_mean_risk", "Unavailable"))]])]
    else:
        story += [Paragraph("PPO results", styles["Heading2"]),
                  Paragraph("PPO training/evaluation was not run for this persisted API analysis. It remains available through the existing Streamlit research workflow; no PPO values are reported here.", styles["BodyText"])]
    dsw = result.get("neural_dsw")
    story += [Paragraph("Neural DSW", styles["Heading2"]), Paragraph(
        "Safety weight: %s. %s" % (escape(_ascii(dsw.get("safety_weight"))), escape(_ascii(dsw.get("provenance", "")))) if dsw else
        "Unavailable: Neural DSW was not run for this analysis.", styles["BodyText"]),
              Paragraph("3D visualization", styles["Heading2"]),
              Paragraph("The project model endpoint exposes parametric frame geometry derived from validated dimensions. This is an illustrative structural visualization, not FEA. The illustrative geometry is not part of the risk calculation.", styles["BodyText"]),
              Paragraph("Limitations", styles["Heading2"]), Paragraph(escape(_ascii(result.get("limitations", "Research prototype only."))), styles["BodyText"])]
    story += [Paragraph("Audit history", styles["Heading2"])]
    audit_rows = [["Time (UTC)", "User", "Action", "Details"]]
    audit_rows.extend([[event.created_at.isoformat(), event.actor.get_username() if event.actor else "Unavailable",
                        event.action, str(event.details)[:300]] for event in audit_events])
    if len(audit_rows) == 1:
        audit_rows.append(["Unavailable", "", "No audit events supplied", ""])
    story.append(_table(audit_rows, small=True))
    doc.build(story)
    return buf.getvalue()

def _table(rows, small=False):
    from reportlab.platypus import Paragraph
    cooked = [[Paragraph(escape(_ascii(value)), getSampleStyleSheet()["BodyText"]) for value in row] for row in rows]
    table = Table(cooked, colWidths=[174*mm/max(1, len(rows[0]))] * max(1, len(rows[0])), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),colors.HexColor("#13243a")),
        ("TEXTCOLOR", (0,0),(-1,0),colors.white), ("GRID",(0,0),(-1,-1),0.35,colors.grey),
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("FONTSIZE",(0,0),(-1,-1),7 if small else 9),
        ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    return table


def _ascii(value):
    return str(value).encode("ascii", "replace").decode("ascii")
