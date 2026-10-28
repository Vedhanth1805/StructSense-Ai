from rest_framework import serializers
from .models import Project, Document, AnalysisRun

class ProjectSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True)
    analysis_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Project
        fields = ["id", "name", "description", "created_at", "updated_at", "document_count", "analysis_count"]

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "original_filename", "file_type", "file_size", "processing_status", "processing_error", "extraction_metadata", "uploaded_at"]

class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisRun
        fields = ["id", "status", "scenario", "result", "created_at"]
