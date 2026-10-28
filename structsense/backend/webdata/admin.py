from django.contrib import admin
from .models import (Project, Document, DocumentSource, ExtractedParameter, ParameterSource,
                     ParameterConflict, ParameterCorrection, AnalysisRun, StressScenario,
                     AnalysisResult, Report, AuditEvent)

for model in (Project, Document, DocumentSource, ExtractedParameter, ParameterSource,
              ParameterConflict, ParameterCorrection, AnalysisRun, StressScenario,
              AnalysisResult, Report, AuditEvent):
    admin.site.register(model)
