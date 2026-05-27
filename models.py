"""
Breathe ESG — Core Data Models
================================
Design principles:
  - Every table has a tenant FK (multi-tenancy enforced at ORM layer)
  - RawEmissionRow is immutable after creation
  - All state transitions produce AuditEvent records
  - UUIDs everywhere (prevents enumeration attacks)
  - Soft deletion only (regulatory data must be recoverable)
"""

import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MinValueValidator
from django.db.models import Q


# ─── MANAGER UTILITIES ───────────────────────────────────────────────────────

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


class SoftDeleteQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


# ─── TENANTS ─────────────────────────────────────────────────────────────────

class Tenant(models.Model):
    """
    Root entity for multi-tenancy.

    Every other model in this application carries a FK to Tenant.
    The slug is used in URL routing and API paths to identify the tenant
    without exposing sequential integer IDs.

    emission_factor_methodology determines which factor database is used
    for calculation. This is set per-tenant because different frameworks
    (GHG Protocol vs. DEFRA vs. EPA) produce different numbers, and
    customers need consistent methodology within a reporting period.
    """

    class Methodology(models.TextChoices):
        GHG_PROTOCOL = "GHG_PROTOCOL", "GHG Protocol"
        DEFRA = "DEFRA", "UK DEFRA"
        EPA = "EPA", "US EPA"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    reporting_year = models.SmallIntegerField(null=True, blank=True)
    preferred_unit_system = models.CharField(
        max_length=10,
        choices=[("metric", "Metric"), ("imperial", "Imperial")],
        default="metric",
    )
    emission_factor_methodology = models.CharField(
        max_length=50,
        choices=Methodology.choices,
        default=Methodology.GHG_PROTOCOL,
    )
    timezone = models.CharField(max_length=50, default="UTC")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenant"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ─── USERS ───────────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Platform user. Email is the primary identifier, not username.

    Why extend AbstractBaseUser instead of AbstractUser?
    AbstractUser forces a username field. Enterprise B2B users identify
    by email address. Removing username eliminates a confusing redundant
    field and prevents "what do I log in with?" support tickets.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        db_table = "tenants_user"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.email


class TenantMembership(models.Model):
    """
    Many-to-many between User and Tenant with role.

    A user can be an ANALYST in TenantA and a VIEWER in TenantB.
    This is common for consultants managing multiple client accounts.

    Unique constraint on (tenant, user) means each user has exactly
    one role per tenant. Role elevation requires an admin to delete
    and recreate the membership, which creates an audit trail.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        ANALYST = "ANALYST", "Analyst"
        VIEWER = "VIEWER", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=30, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )

    class Meta:
        db_table = "tenants_tenantmembership"
        unique_together = [("tenant", "user")]

    def __str__(self):
        return f"{self.user.email} @ {self.tenant.slug} [{self.role}]"


# ─── DATA SOURCES ─────────────────────────────────────────────────────────────

class DataSource(models.Model):
    """
    Configured integration endpoint per tenant.

    Separating DataSource from IngestionBatch means we can track configuration
    separately from individual upload runs. If a customer changes their
    SAP plant code mapping, we update the DataSource config without touching
    historical batch records.

    The config JSONB field stores source-specific configuration:
    - SAP: plant_country_mapping, material_fuel_mapping, encoding
    - Utility: account_facility_mapping, default_unit
    - Travel: default_class_if_missing, radiative_forcing_method
    """

    class SourceType(models.TextChoices):
        SAP_FLAT_FILE = "SAP_FLAT_FILE", "SAP Flat File Export"
        UTILITY_CSV = "UTILITY_CSV", "Utility CSV Export"
        TRAVEL_CONCUR = "TRAVEL_CONCUR", "SAP Concur Export"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="data_sources")
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
        User, on_delete=models.SET_NULL, null=True, related_name="created_sources"
    )

    class Meta:
        db_table = "ingestion_datasource"
        constraints = [
            models.CheckConstraint(check=Q(scope__in=[1, 2, 3]), name="valid_scope")
        ]

    def __str__(self):
        return f"{self.tenant.slug} / {self.name}"


# ─── INGESTION BATCHES ────────────────────────────────────────────────────────

class IngestionBatch(models.Model):
    """
    One execution of the ingestion pipeline.

    source_file_hash (SHA-256) enables deduplication: if the same file
    is uploaded twice, we detect it and warn the user instead of creating
    duplicate records.

    pipeline_version captures the semver of the ingestion code at the
    time of processing. If a bug is found in the normalization logic,
    we can identify affected batches by their pipeline_version and
    trigger reprocessing.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        SUPERSEDED = "SUPERSEDED", "Superseded"  # Replaced by a re-upload

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="batches"
    )  # Denormalized from data_source for faster tenant-scoped queries
    data_source = models.ForeignKey(
        DataSource, on_delete=models.PROTECT, related_name="batches"
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploaded_batches")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    source_filename = models.CharField(max_length=500, blank=True)
    source_file_hash = models.CharField(max_length=64, blank=True)  # SHA-256 hex
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


# ─── RAW EMISSION ROWS ────────────────────────────────────────────────────────

class RawEmissionRow(models.Model):
    """
    The immutable ledger of what was received from the source system.

    CONTRACT: This model has no update() method exposed through the
    application layer. The only permitted mutation is soft deletion
    (is_deleted = True). All analyst corrections produce a new
    NormalizedEmissionRow version — they never modify this record.

    raw_data stores the complete original row as JSONB. This ensures
    we can always re-parse from the original data if our extraction
    logic changes. It also provides a complete audit baseline: an
    auditor can always see exactly what the source system sent.

    row_index is the 0-based position in the source file. This allows
    analysts to cross-reference with the original file ("row 247 in
    the February SAP export") for manual verification.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Review"
        # NEEDS_REVIEW is set when validation finds issues but they are
        # non-blocking (WARNINGs only). The row is processable but requires
        # analyst sign-off.

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="raw_rows")
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="rows")
    row_index = models.IntegerField()
    source_type = models.CharField(max_length=30)  # Copied from DataSource at ingestion time
    scope = models.SmallIntegerField()
    raw_data = models.JSONField()  # Complete original row
    ingested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)

    # Soft deletion
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="deleted_rows"
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


# ─── NORMALIZED EMISSION ROWS ─────────────────────────────────────────────────

class NormalizedEmissionRow(models.Model):
    """
    The analyst-editable, versioned view of a raw row.

    Versioning strategy:
    - First version: parent_id=None, version=1, is_current=True
    - After analyst edit: old row gets is_current=False, new row is created
      with parent_id=old_row.id, version=old_row.version+1, is_current=True

    This preserves the complete edit history while keeping "current state"
    queries simple (filter is_current=True).

    Why store both original and normalized quantities?
    The original value from SAP might be "1200 therms". The normalized
    value is "126144 MJ". Storing both enables:
    1. Verification that the conversion is correct
    2. Re-running conversions with updated factors
    3. Showing analysts the original value alongside the normalized one
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
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    raw_row = models.ForeignKey(
        RawEmissionRow, on_delete=models.CASCADE, related_name="normalized_versions"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="child_versions"
    )
    version = models.SmallIntegerField(default=1)
    is_current = models.BooleanField(default=True)

    # Activity classification
    activity_type = models.CharField(max_length=50, choices=ActivityType.choices)

    # Normalized values (what we calculate emissions from)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit = models.CharField(max_length=30)

    # Original values as received (immutable reference)
    quantity_original = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    unit_original = models.CharField(max_length=30, blank=True)
    conversion_factor = models.DecimalField(
        max_digits=18, decimal_places=10, null=True, blank=True
    )
    conversion_source = models.CharField(max_length=100, blank=True)

    # Time period
    period_start = models.DateField()
    period_end = models.DateField()

    # Facility / location
    facility_id = models.CharField(max_length=100, blank=True)
    facility_name = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    region = models.CharField(max_length=100, blank=True)  # For grid EF selection
    supplier = models.CharField(max_length=255, blank=True)

    # Analyst metadata
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # Source-specific extras

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="normalized_rows")

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


# ─── VALIDATION ISSUES ────────────────────────────────────────────────────────

class ValidationIssue(models.Model):
    """
    One record per validation rule failure per raw row.

    Structured as a proper entity (not a free-text log message) so the
    analyst UI can render actionable information: which field failed,
    what the offending value was, and how severe the issue is.

    severity levels:
    - ERROR: Row cannot be approved until this is resolved
    - WARNING: Row can be approved but analyst must acknowledge
    - INFO: Informational note, no action required
    """

    class Severity(models.TextChoices):
        ERROR = "ERROR", "Error"
        WARNING = "WARNING", "Warning"
        INFO = "INFO", "Info"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_row = models.ForeignKey(
        RawEmissionRow, on_delete=models.CASCADE, related_name="validation_issues"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    rule_code = models.CharField(max_length=50)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    field_name = models.CharField(max_length=100, blank=True)
    field_value = models.CharField(max_length=500, blank=True)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_issues"
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


# ─── AUDIT TRAIL ──────────────────────────────────────────────────────────────

class AuditEvent(models.Model):
    """
    Append-only log of every state-changing action.

    CONSTRAINT: Nothing is ever deleted from this table.
    The application layer enforces this: there is no delete() path
    for AuditEvent in any view or service method.

    before_state and after_state capture the full serialized state of
    the affected object at the moment of change. This enables full
    reconstruction of what changed without joining to other tables
    (which is important if related records are later soft-deleted).

    actor_ip is captured for regulatory compliance (some frameworks
    require logging the IP address of users who approve data).
    """

    class EventType(models.TextChoices):
        ROW_APPROVED = "ROW_APPROVED", "Row Approved"
        ROW_REJECTED = "ROW_REJECTED", "Row Rejected"
        ROW_EDITED = "ROW_EDITED", "Row Edited"
        ROW_DELETED = "ROW_DELETED", "Row Soft Deleted"
        BATCH_UPLOADED = "BATCH_UPLOADED", "Batch Uploaded"
        BATCH_SUPERSEDED = "BATCH_SUPERSEDED", "Batch Superseded"
        ISSUE_RESOLVED = "ISSUE_RESOLVED", "Validation Issue Resolved"
        BULK_APPROVE = "BULK_APPROVE", "Bulk Approval"
        BULK_REJECT = "BULK_REJECT", "Bulk Rejection"
        USER_INVITED = "USER_INVITED", "User Invited"
        SOURCE_CONFIGURED = "SOURCE_CONFIGURED", "Data Source Configured"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="audit_events")
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="audit_events")
    actor_ip = models.GenericIPAddressField(null=True, blank=True)
    target_type = models.CharField(max_length=50)  # Model class name
    target_id = models.UUIDField()
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    batch_event_id = models.UUIDField(null=True, blank=True)  # Groups bulk operation events

    class Meta:
        db_table = "audit_auditevent"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} by {self.actor.email} at {self.created_at}"


# ─── EMISSION FACTORS ─────────────────────────────────────────────────────────

class EmissionFactor(models.Model):
    """
    Reference data for GHG calculations. Shared across all tenants.

    GHG factors change annually (DEFRA updates every June, EPA updates
    sporadically). valid_from and valid_to allow multiple factor versions
    to coexist, and the calculation layer selects the factor valid for
    the activity period_start date.

    Storing individual gas factors (co2_factor, ch4_factor, n2o_factor)
    in addition to co2e_factor enables recomputation when GWP values
    change (e.g., IPCC AR5 → AR6 changed GWP100 for CH4 from 25 to 29.8).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_type = models.CharField(max_length=50)
    fuel_type = models.CharField(max_length=50, blank=True)
    country_code = models.CharField(max_length=2, blank=True)  # Blank = global
    region = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=30)  # The denominator unit
    co2_factor = models.DecimalField(max_digits=18, decimal_places=10)
    ch4_factor = models.DecimalField(max_digits=18, decimal_places=10, null=True, blank=True)
    n2o_factor = models.DecimalField(max_digits=18, decimal_places=10, null=True, blank=True)
    co2e_factor = models.DecimalField(max_digits=18, decimal_places=10)
    gwp_version = models.CharField(max_length=20, blank=True)  # AR4 / AR5 / AR6
    source = models.CharField(max_length=200)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "emissions_emissionfactor"
        indexes = [
            models.Index(fields=["activity_type", "valid_from"]),
            models.Index(fields=["country_code", "activity_type"]),
        ]

    def __str__(self):
        return f"{self.activity_type} / {self.fuel_type or 'n/a'} [{self.source}]"


class EmissionCalculation(models.Model):
    """
    Computed GHG output for a normalized row.

    Kept separate from NormalizedEmissionRow so calculation logic can
    be re-run when emission factors are updated without touching the
    analyst-reviewed normalized data.

    calculator_version enables identifying calculations performed with
    buggy code versions, similar to pipeline_version on IngestionBatch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    normalized_row = models.ForeignKey(
        NormalizedEmissionRow, on_delete=models.CASCADE, related_name="calculations"
    )
    emission_factor = models.ForeignKey(
        EmissionFactor, on_delete=models.PROTECT, related_name="calculations"
    )
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=6)
    co2_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    ch4_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    n2o_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    calculation_method = models.CharField(
        max_length=50,
        choices=[
            ("ACTIVITY_BASED", "Activity Based"),
            ("SPEND_BASED", "Spend Based"),
            ("DISTANCE_BASED", "Distance Based"),
        ],
        default="ACTIVITY_BASED",
    )
    calculated_at = models.DateTimeField(auto_now_add=True)
    calculator_version = models.CharField(max_length=20, default="1.0.0")

    class Meta:
        db_table = "emissions_emissioncalculation"
        indexes = [
            models.Index(fields=["tenant", "normalized_row"]),
        ]

    def __str__(self):
        return f"{self.co2e_kg} kg CO2e for NormalizedRow {self.normalized_row_id}"
