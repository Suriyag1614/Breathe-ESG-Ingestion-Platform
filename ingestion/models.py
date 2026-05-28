"""
ingestion/models.py
Contains: DataSource, IngestionBatch, RawEmissionRow,
          NormalizedEmissionRow, ValidationIssue

All FKs to tenants app use string references to avoid circular imports.
"""
import uuid
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator


# ─── SHARED MANAGER ──────────────────────────────────────────────────────────

class TenantAwareQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)

    def active(self):
        return self.filter(is_deleted=False)


class TenantAwareManager(models.Manager):
    def get_queryset(self):
        return TenantAwareQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)

    def active_for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant).active()


# ─── DATA SOURCE ──────────────────────────────────────────────────────────────

class DataSource(models.Model):
    """
    Configured integration endpoint per tenant.
    Separates source configuration from individual upload runs.
    """

    class SourceType(models.TextChoices):
        SAP_FLAT_FILE = "SAP_FLAT_FILE", "SAP Flat File Export"
        UTILITY_CSV = "UTILITY_CSV", "Utility CSV Export"
        TRAVEL_CONCUR = "TRAVEL_CONCUR", "SAP Concur Export"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="data_sources"
    )
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    scope = models.SmallIntegerField(
        choices=[(1, "Scope 1"), (2, "Scope 2"), (3, "Scope 3")],
        validators=[MinValueValidator(1)],
    )
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "tenants.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sources",
    )

    class Meta:
        db_table = "ingestion_datasource"
        constraints = [
            models.CheckConstraint(check=Q(scope__in=[1, 2, 3]), name="valid_scope")
        ]

    def __str__(self):
        return f"{self.tenant.slug} / {self.name}"


# ─── INGESTION BATCH ──────────────────────────────────────────────────────────

class IngestionBatch(models.Model):
    """
    One execution of the ingestion pipeline.
    source_file_hash enables deduplication.
    pipeline_version enables identifying affected batches on bug fixes.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="batches"
    )
    data_source = models.ForeignKey(
        "ingestion.DataSource", on_delete=models.PROTECT, related_name="batches"
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    uploaded_by = models.ForeignKey(
        "tenants.User", on_delete=models.PROTECT, related_name="uploaded_batches"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    source_filename = models.CharField(max_length=500, blank=True)
    source_file_hash = models.CharField(max_length=64, blank=True)
    row_count_raw = models.IntegerField(null=True, blank=True)
    row_count_valid = models.IntegerField(null=True, blank=True)
    row_count_failed = models.IntegerField(null=True, blank=True)
    error_summary = models.JSONField(null=True, blank=True)
    pipeline_version = models.CharField(max_length=20, default="1.0.0")

    class Meta:
        db_table = "ingestion_ingestionbatch"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "-uploaded_at"]),
            models.Index(fields=["source_file_hash"]),
        ]

    def __str__(self):
        return f"Batch {self.id} ({self.data_source.name}, {self.status})"


# ─── RAW EMISSION ROW ─────────────────────────────────────────────────────────

class RawEmissionRow(models.Model):
    """
    The immutable ledger of what was received from the source system.
    CONTRACT: Never updated after creation. Only soft deletion is permitted.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="raw_rows"
    )
    batch = models.ForeignKey(
        "ingestion.IngestionBatch", on_delete=models.CASCADE, related_name="rows"
    )
    row_index = models.IntegerField()
    source_type = models.CharField(max_length=30)
    scope = models.SmallIntegerField()
    raw_data = models.JSONField()
    ingested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "tenants.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_rows",
    )

    objects = TenantAwareManager()

    class Meta:
        db_table = "ingestion_rawemissionrow"
        unique_together = [("batch", "row_index")]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["batch", "row_index"]),
        ]

    def __str__(self):
        return f"Row {self.row_index} / Batch {self.batch_id} [{self.status}]"


# ─── NORMALIZED EMISSION ROW ──────────────────────────────────────────────────

class NormalizedEmissionRow(models.Model):
    """
    The analyst-editable, versioned view of a raw row.
    When edited, a new version is created; old version keeps is_current=False.
    """

    class ActivityType(models.TextChoices):
        FUEL_COMBUSTION = "FUEL_COMBUSTION", "Fuel Combustion"
        ELECTRICITY = "ELECTRICITY", "Electricity"
        FLIGHT = "FLIGHT", "Business Flight"
        HOTEL = "HOTEL", "Hotel Stay"
        GROUND_TRANSPORT = "GROUND_TRANSPORT", "Ground Transport"
        DISTRICT_HEAT = "DISTRICT_HEAT", "District Heat/Steam"
        REFRIGERANT = "REFRIGERANT", "Refrigerant Leakage"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    raw_row = models.ForeignKey(
        "ingestion.RawEmissionRow",
        on_delete=models.CASCADE,
        related_name="normalized_versions",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_versions",
    )
    version = models.SmallIntegerField(default=1)
    is_current = models.BooleanField(default=True)

    activity_type = models.CharField(max_length=50, choices=ActivityType.choices)

    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit = models.CharField(max_length=30)

    quantity_original = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    unit_original = models.CharField(max_length=30, blank=True)
    conversion_factor = models.DecimalField(
        max_digits=18, decimal_places=10, null=True, blank=True
    )
    conversion_source = models.CharField(max_length=100, blank=True)

    period_start = models.DateField()
    period_end = models.DateField()

    facility_id = models.CharField(max_length=100, blank=True)
    facility_name = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    region = models.CharField(max_length=100, blank=True)
    supplier = models.CharField(max_length=255, blank=True)

    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "tenants.User", on_delete=models.PROTECT, related_name="normalized_rows"
    )

    objects = TenantAwareManager()

    class Meta:
        db_table = "ingestion_normalizedemissionrow"
        constraints = [
            models.UniqueConstraint(
                fields=["raw_row"],
                condition=Q(is_current=True),
                name="unique_current_version_per_raw_row",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "is_current", "period_start"]),
            models.Index(fields=["raw_row", "-version"]),
        ]

    def __str__(self):
        return f"NormalizedRow v{self.version} for RawRow {self.raw_row_id}"


# ─── VALIDATION ISSUE ─────────────────────────────────────────────────────────

class ValidationIssue(models.Model):
    """
    One record per validation rule failure per raw row.
    """

    class Severity(models.TextChoices):
        ERROR = "ERROR", "Error"
        WARNING = "WARNING", "Warning"
        INFO = "INFO", "Info"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_row = models.ForeignKey(
        "ingestion.RawEmissionRow",
        on_delete=models.CASCADE,
        related_name="validation_issues",
    )
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    rule_code = models.CharField(max_length=50)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    field_name = models.CharField(max_length=100, blank=True)
    field_value = models.CharField(max_length=500, blank=True)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        "tenants.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_issues",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ingestion_validationissue"
        indexes = [
            models.Index(fields=["raw_row", "is_resolved"]),
            models.Index(fields=["tenant", "severity", "is_resolved"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.rule_code} on row {self.raw_row_id}"
