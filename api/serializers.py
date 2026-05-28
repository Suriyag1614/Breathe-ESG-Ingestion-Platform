"""
Breathe ESG — API Serializers
==============================
Serializers for all models. Organized by domain.
Tenant context is injected via the request; no tenant field is writable by clients.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from tenants.models import Tenant, TenantMembership
from ingestion.models import DataSource, IngestionBatch, RawEmissionRow, NormalizedEmissionRow, ValidationIssue
from audit.models import AuditEvent
from emissions.models import EmissionFactor, EmissionCalculation

User = get_user_model()


# ─── AUTH / USER ─────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "date_joined"]
        read_only_fields = ["id", "date_joined"]

    def get_full_name(self, obj):
        return obj.get_full_name()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password", "password_confirm"]

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        return User.objects.create_user(**validated_data)


# ─── TENANT ───────────────────────────────────────────────────────────────────

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            "id", "name", "slug", "is_active", "reporting_year",
            "preferred_unit_system", "emission_factor_methodology",
            "timezone", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class TenantMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_email = serializers.EmailField(write_only=True)
    invited_by = UserSerializer(read_only=True)

    class Meta:
        model = TenantMembership
        fields = ["id", "tenant", "user", "user_email", "role", "created_at", "invited_by"]
        read_only_fields = ["id", "tenant", "user", "invited_by", "created_at"]

    def validate_user_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"No user found with email {value}.")
        return value

    def create(self, validated_data):
        email = validated_data.pop("user_email")
        user = User.objects.get(email=email)
        return TenantMembership.objects.create(user=user, **validated_data)


# ─── DATA SOURCE ──────────────────────────────────────────────────────────────

class DataSourceSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)

    class Meta:
        model = DataSource
        fields = [
            "id", "name", "source_type", "source_type_display",
            "scope", "scope_display", "config", "is_active",
            "created_at", "created_by",
        ]
        read_only_fields = ["id", "created_at", "created_by"]

    def validate_config(self, value):
        # Basic structural validation per source_type
        source_type = self.initial_data.get("source_type") or (
            self.instance.source_type if self.instance else None
        )
        if source_type == "SAP_FLAT_FILE":
            if not isinstance(value.get("plant_country_mapping", {}), dict):
                raise serializers.ValidationError("plant_country_mapping must be a dict.")
        return value


# ─── INGESTION BATCH ──────────────────────────────────────────────────────────

class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by = UserSerializer(read_only=True)
    data_source_name = serializers.CharField(source="data_source.name", read_only=True)
    source_type = serializers.CharField(source="data_source.source_type", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    error_rate = serializers.SerializerMethodField()

    class Meta:
        model = IngestionBatch
        fields = [
            "id", "data_source", "data_source_name", "source_type",
            "status", "status_display", "uploaded_by", "uploaded_at",
            "completed_at", "source_filename", "source_file_hash",
            "row_count_raw", "row_count_valid", "row_count_failed",
            "error_summary", "pipeline_version", "error_rate",
        ]
        read_only_fields = [
            "id", "uploaded_by", "uploaded_at", "completed_at",
            "source_file_hash", "row_count_raw", "row_count_valid",
            "row_count_failed", "error_summary", "pipeline_version",
        ]

    def get_error_rate(self, obj):
        if obj.row_count_raw and obj.row_count_raw > 0:
            failed = obj.row_count_failed or 0
            return round(failed / obj.row_count_raw * 100, 1)
        return None


# ─── VALIDATION ISSUE ─────────────────────────────────────────────────────────

class ValidationIssueSerializer(serializers.ModelSerializer):
    resolved_by = UserSerializer(read_only=True)

    class Meta:
        model = ValidationIssue
        fields = [
            "id", "rule_code", "severity", "field_name", "field_value",
            "message", "is_resolved", "resolved_by", "resolved_at",
            "resolution_note", "created_at",
        ]
        read_only_fields = [
            "id", "rule_code", "severity", "field_name", "field_value",
            "message", "resolved_by", "resolved_at", "created_at",
        ]


class ResolveIssueSerializer(serializers.Serializer):
    resolution_note = serializers.CharField(required=True, min_length=5)


# ─── RAW EMISSION ROW ─────────────────────────────────────────────────────────

class RawEmissionRowListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no raw_data blob)."""
    batch_filename = serializers.CharField(source="batch.source_filename", read_only=True)
    issue_count = serializers.SerializerMethodField()
    has_errors = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RawEmissionRow
        fields = [
            "id", "row_index", "source_type", "scope", "status",
            "status_display", "ingested_at", "batch", "batch_filename",
            "issue_count", "has_errors",
        ]

    def get_issue_count(self, obj):
        return obj.validation_issues.filter(is_resolved=False).count()

    def get_has_errors(self, obj):
        return obj.validation_issues.filter(severity="ERROR", is_resolved=False).exists()


class RawEmissionRowDetailSerializer(serializers.ModelSerializer):
    """Full serializer with raw_data and nested issues."""
    validation_issues = ValidationIssueSerializer(many=True, read_only=True)
    normalized_current = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RawEmissionRow
        fields = [
            "id", "row_index", "source_type", "scope", "raw_data",
            "status", "status_display", "ingested_at", "batch",
            "validation_issues", "normalized_current",
            "is_deleted", "deleted_at",
        ]
        read_only_fields = fields  # Raw rows are never written via API

    def get_normalized_current(self, obj):
        current = obj.normalized_versions.filter(is_current=True).first()
        if current:
            return NormalizedEmissionRowSerializer(current).data
        return None


class RowActionSerializer(serializers.Serializer):
    """Used for approve/reject actions."""
    comment = serializers.CharField(required=False, allow_blank=True)


# ─── NORMALIZED EMISSION ROW ──────────────────────────────────────────────────

class NormalizedEmissionRowSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    activity_type_display = serializers.CharField(
        source="get_activity_type_display", read_only=True
    )

    class Meta:
        model = NormalizedEmissionRow
        fields = [
            "id", "version", "is_current", "activity_type", "activity_type_display",
            "quantity", "unit", "quantity_original", "unit_original",
            "conversion_factor", "conversion_source",
            "period_start", "period_end",
            "facility_id", "facility_name", "country_code", "region",
            "supplier", "notes", "metadata", "created_at", "created_by",
        ]
        read_only_fields = [
            "id", "version", "is_current", "quantity_original",
            "unit_original", "conversion_factor", "conversion_source",
            "created_at", "created_by",
        ]


class NormalizedRowEditSerializer(serializers.ModelSerializer):
    """Used when an analyst edits a normalized row — creates a new version."""

    class Meta:
        model = NormalizedEmissionRow
        fields = [
            "activity_type", "quantity", "unit",
            "period_start", "period_end",
            "facility_id", "facility_name", "country_code",
            "region", "supplier", "notes", "metadata",
        ]

    def validate(self, data):
        if data.get("period_end") and data.get("period_start"):
            if data["period_end"] <= data["period_start"]:
                raise serializers.ValidationError(
                    {"period_end": "Period end must be after period start."}
                )
        return data


# ─── EMISSION FACTOR ─────────────────────────────────────────────────────────

class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = [
            "id", "activity_type", "fuel_type", "country_code", "region",
            "unit", "co2_factor", "ch4_factor", "n2o_factor", "co2e_factor",
            "gwp_version", "source", "valid_from", "valid_to",
        ]
        read_only_fields = ["id"]


# ─── EMISSION CALCULATION ─────────────────────────────────────────────────────

class EmissionCalculationSerializer(serializers.ModelSerializer):
    emission_factor = EmissionFactorSerializer(read_only=True)

    class Meta:
        model = EmissionCalculation
        fields = [
            "id", "normalized_row", "emission_factor",
            "co2e_kg", "co2_kg", "ch4_kg", "n2o_kg",
            "calculation_method", "calculated_at", "calculator_version",
        ]
        read_only_fields = fields


# ─── AUDIT EVENT ──────────────────────────────────────────────────────────────

class AuditEventSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "event_type", "event_type_display", "actor", "actor_ip",
            "target_type", "target_id", "before_state", "after_state",
            "comment", "created_at", "batch_event_id",
        ]
        read_only_fields = fields  # Audit log is never written via API


# ─── DASHBOARD / AGGREGATION ──────────────────────────────────────────────────

class DashboardSummarySerializer(serializers.Serializer):
    """Read-only aggregated stats for the dashboard."""
    total_records = serializers.IntegerField()
    pending_review = serializers.IntegerField()
    validation_errors = serializers.IntegerField()
    approved = serializers.IntegerField()
    approval_rate_pct = serializers.FloatField()
    scope1_co2e_t = serializers.FloatField()
    scope2_co2e_t = serializers.FloatField()
    scope3_co2e_t = serializers.FloatField()
    recent_batches = IngestionBatchSerializer(many=True)


class FileUploadSerializer(serializers.Serializer):
    """Used for the file upload endpoint."""
    file = serializers.FileField()
    data_source_id = serializers.UUIDField()

    def validate_file(self, value):
        max_mb = 50
        if value.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(f"File exceeds {max_mb} MB limit.")
        name = value.name.lower()
        if not (name.endswith(".csv") or name.endswith(".tsv") or name.endswith(".txt")):
            raise serializers.ValidationError("Only CSV/TSV files are accepted.")
        return value
