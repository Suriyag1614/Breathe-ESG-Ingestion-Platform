from django.contrib import admin
from .models import DataSource, IngestionBatch, RawEmissionRow, NormalizedEmissionRow, ValidationIssue


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "source_type", "scope", "is_active", "created_at"]
    list_filter = ["source_type", "scope", "is_active"]
    search_fields = ["name", "tenant__slug"]


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ["id", "tenant", "data_source", "status", "uploaded_by", "uploaded_at", "row_count_raw"]
    list_filter = ["status", "data_source__source_type"]
    search_fields = ["source_filename", "tenant__slug"]
    readonly_fields = ["source_file_hash", "uploaded_at", "completed_at"]


@admin.register(RawEmissionRow)
class RawEmissionRowAdmin(admin.ModelAdmin):
    list_display = ["id", "tenant", "batch", "row_index", "source_type", "scope", "status", "ingested_at"]
    list_filter = ["status", "source_type", "scope", "is_deleted"]
    search_fields = ["tenant__slug"]
    readonly_fields = ["raw_data", "ingested_at"]


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = ["rule_code", "severity", "field_name", "is_resolved", "created_at"]
    list_filter = ["severity", "is_resolved"]
    search_fields = ["rule_code", "message"]
