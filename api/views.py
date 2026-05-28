"""
Breathe ESG — API Views
========================
All views are tenant-scoped. The URL structure is:
  /api/v1/auth/...
  /api/v1/tenants/{tenant_slug}/...

`TenantFromSlugMixin.initial()` resolves request.tenant + request.membership
before any view logic runs.
"""

import csv
import io
import uuid
from datetime import datetime

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from tenants.models import Tenant, TenantMembership
from ingestion.models import (
    DataSource, IngestionBatch, RawEmissionRow,
    NormalizedEmissionRow, ValidationIssue
)
from audit.models import AuditEvent
from emissions.models import EmissionFactor, EmissionCalculation

from .auth import (
    TenantFromSlugMixin, IsTenantMember, IsTenantAnalyst,
    IsTenantAdmin, IsAnalystOrReadOnly, get_tokens_for_user, sha256_of_file
)
from .serializers import (
    UserSerializer, UserRegistrationSerializer,
    TenantSerializer, TenantMembershipSerializer,
    DataSourceSerializer,
    IngestionBatchSerializer, FileUploadSerializer,
    RawEmissionRowListSerializer, RawEmissionRowDetailSerializer,
    RowActionSerializer, NormalizedEmissionRowSerializer,
    NormalizedRowEditSerializer, ValidationIssueSerializer,
    ResolveIssueSerializer, EmissionFactorSerializer,
    EmissionCalculationSerializer, AuditEventSerializer,
    DashboardSummarySerializer,
)

User = get_user_model()


# ─── AUTH VIEWS ───────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/"""
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(get_tokens_for_user(user), status=status.HTTP_201_CREATED)


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserTenantsView(generics.ListAPIView):
    """GET /api/v1/auth/tenants/ — list tenants the current user belongs to"""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        memberships = TenantMembership.objects.filter(
            user=request.user
        ).select_related("tenant")
        data = [
            {
                "tenant": TenantSerializer(m.tenant).data,
                "role": m.role,
            }
            for m in memberships
        ]
        return Response(data)


# ─── TENANT MANAGEMENT ────────────────────────────────────────────────────────

class TenantCreateView(generics.CreateAPIView):
    """POST /api/v1/tenants/ — create a new tenant (creates admin membership)"""
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        import re
        name = serializer.validated_data["name"]
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        # Ensure uniqueness
        base_slug = slug
        counter = 1
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        tenant = serializer.save(slug=slug)
        TenantMembership.objects.create(
            tenant=tenant,
            user=self.request.user,
            role=TenantMembership.Role.ADMIN,
        )


class TenantDetailView(TenantFromSlugMixin, generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/tenants/{tenant_slug}/"""
    serializer_class = TenantSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated(), IsTenantMember()]
        return [permissions.IsAuthenticated(), IsTenantAdmin()]

    def get_object(self):
        return self.request.tenant


class TenantMembersView(TenantFromSlugMixin, generics.ListCreateAPIView):
    """GET/POST /api/v1/tenants/{tenant_slug}/members/"""
    serializer_class = TenantMembershipSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsTenantMember()]
        return [permissions.IsAuthenticated(), IsTenantAdmin()]

    def get_queryset(self):
        return TenantMembership.objects.filter(
            tenant=self.request.tenant
        ).select_related("user", "invited_by")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, invited_by=self.request.user)


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

class DashboardView(TenantFromSlugMixin, APIView):
    """GET /api/v1/tenants/{tenant_slug}/dashboard/"""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get(self, request, **kwargs):
        tenant = request.tenant
        rows = RawEmissionRow.objects.for_tenant(tenant).filter(is_deleted=False)

        total = rows.count()
        pending = rows.filter(status__in=["PENDING", "NEEDS_REVIEW"]).count()
        approved = rows.filter(status="APPROVED").count()
        errors = ValidationIssue.objects.filter(
            tenant=tenant, severity="ERROR", is_resolved=False
        ).count()

        # CO2e by scope (from approved calculations)
        def scope_co2e(scope_num):
            result = EmissionCalculation.objects.filter(
                tenant=tenant,
                normalized_row__raw_row__status="APPROVED",
                normalized_row__raw_row__scope=scope_num,
                normalized_row__is_current=True,
            ).aggregate(total=Sum("co2e_kg"))
            kg = result["total"] or 0
            return round(kg / 1000, 2)  # convert to tonnes

        recent_batches = IngestionBatch.objects.filter(
            tenant=tenant
        ).order_by("-uploaded_at")[:5]

        data = {
            "total_records": total,
            "pending_review": pending,
            "validation_errors": errors,
            "approved": approved,
            "approval_rate_pct": round(approved / total * 100, 1) if total else 0,
            "scope1_co2e_t": scope_co2e(1),
            "scope2_co2e_t": scope_co2e(2),
            "scope3_co2e_t": scope_co2e(3),
            "recent_batches": IngestionBatchSerializer(recent_batches, many=True).data,
        }
        return Response(data)


# ─── DATA SOURCES ──────────────────────────────────────────────────────────────

class DataSourceViewSet(TenantFromSlugMixin, viewsets.ModelViewSet):
    """
    /api/v1/tenants/{tenant_slug}/sources/
    Admins can configure; members can list.
    """
    serializer_class = DataSourceSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated(), IsTenantMember()]
        return [permissions.IsAuthenticated(), IsTenantAdmin()]

    def get_queryset(self):
        return DataSource.objects.filter(
            tenant=self.request.tenant
        ).select_related("created_by")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, created_by=self.request.user)


# ─── INGESTION ────────────────────────────────────────────────────────────────

class IngestionBatchViewSet(TenantFromSlugMixin, viewsets.ReadOnlyModelViewSet):
    """
    /api/v1/tenants/{tenant_slug}/batches/
    Batches are created via the upload endpoint, not directly.
    """
    serializer_class = IngestionBatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        qs = IngestionBatch.objects.filter(
            tenant=self.request.tenant
        ).select_related("data_source", "uploaded_by").order_by("-uploaded_at")

        source_type = self.request.query_params.get("source_type")
        if source_type:
            qs = qs.filter(data_source__source_type=source_type)
        return qs

    @action(detail=True, methods=["post"])
    def supersede(self, request, **kwargs):
        """Mark a batch as superseded (used when re-uploading a corrected file)."""
        if request.membership.role not in ("ANALYST", "ADMIN"):
            return Response({"detail": "Analysts or Admins only."}, status=403)
        batch = self.get_object()
        batch.status = IngestionBatch.Status.SUPERSEDED
        batch.save()
        _write_audit(
            request, "BATCH_SUPERSEDED", batch,
            after={"status": "SUPERSEDED"},
            comment=request.data.get("comment", ""),
        )
        return Response({"status": "superseded"})


class FileUploadView(TenantFromSlugMixin, APIView):
    """
    POST /api/v1/tenants/{tenant_slug}/upload/
    Accepts a CSV/TSV file, runs the ingestion pipeline, returns batch summary.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated, IsTenantAnalyst]

    def post(self, request, **kwargs):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        ds_id = serializer.validated_data["data_source_id"]

        try:
            data_source = DataSource.objects.get(id=ds_id, tenant=request.tenant)
        except DataSource.DoesNotExist:
            return Response({"detail": "DataSource not found."}, status=404)

        file_hash = sha256_of_file(uploaded_file)

        # Deduplication check
        if IngestionBatch.objects.filter(
            tenant=request.tenant, source_file_hash=file_hash
        ).exists():
            return Response(
                {"detail": "This file has already been uploaded (duplicate SHA-256 hash)."},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            batch = IngestionBatch.objects.create(
                tenant=request.tenant,
                data_source=data_source,
                status=IngestionBatch.Status.PROCESSING,
                uploaded_by=request.user,
                source_filename=uploaded_file.name,
                source_file_hash=file_hash,
            )

            rows, parse_errors = _parse_csv(uploaded_file)
            batch.row_count_raw = len(rows)

            from validation import ValidationPipeline
            pipeline = ValidationPipeline()
            config = data_source.config or {}

            raw_rows_created = []
            failed = 0

            for i, row_dict in enumerate(rows):
                issues = pipeline.run(
                    [row_dict], data_source.source_type, config
                ).get(0, [])

                has_error = any(iss.severity == "ERROR" for iss in issues)
                row_status = "NEEDS_REVIEW" if issues else "PENDING"

                raw_row = RawEmissionRow.objects.create(
                    tenant=request.tenant,
                    batch=batch,
                    row_index=i,
                    source_type=data_source.source_type,
                    scope=data_source.scope,
                    raw_data=row_dict,
                    status=row_status,
                )

                for iss in issues:
                    ValidationIssue.objects.create(
                        raw_row=raw_row,
                        tenant=request.tenant,
                        rule_code=iss.rule_code,
                        severity=iss.severity,
                        field_name=iss.field_name,
                        field_value=iss.field_value,
                        message=iss.message,
                    )

                if has_error:
                    failed += 1
                raw_rows_created.append(raw_row)

            # Batch-level validators (e.g., overlap check)
            batch_issues = []
            for bv in pipeline.BATCH_VALIDATORS.get(data_source.source_type, []):
                batch_issues.extend(bv(rows))

            for iss in batch_issues:
                if iss.row_index < len(raw_rows_created):
                    ValidationIssue.objects.create(
                        raw_row=raw_rows_created[iss.row_index],
                        tenant=request.tenant,
                        rule_code=iss.rule_code,
                        severity=iss.severity,
                        field_name=iss.field_name,
                        field_value=iss.field_value,
                        message=iss.message,
                    )

            batch.row_count_valid = len(rows) - failed
            batch.row_count_failed = failed
            batch.status = IngestionBatch.Status.COMPLETED
            batch.completed_at = timezone.now()
            batch.save()

            _write_audit(
                request, "BATCH_UPLOADED", batch,
                after={
                    "status": "COMPLETED",
                    "rows_parsed": len(rows),
                    "rows_failed": failed,
                    "filename": uploaded_file.name,
                    "sha256": file_hash,
                },
            )

        return Response(IngestionBatchSerializer(batch).data, status=201)


def _parse_csv(file_obj) -> tuple[list[dict], list[str]]:
    """Decode and parse the uploaded file into a list of row dicts."""
    raw_bytes = file_obj.read()
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return [], ["Could not decode file with any supported encoding."]

    # Auto-detect delimiter
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    errors = []
    for i, row in enumerate(reader):
        # Strip whitespace from all keys and values
        clean = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items() if k}
        rows.append(clean)
    return rows, errors


# ─── REVIEW QUEUE ─────────────────────────────────────────────────────────────

class ReviewQueueViewSet(TenantFromSlugMixin, viewsets.ReadOnlyModelViewSet):
    """
    /api/v1/tenants/{tenant_slug}/rows/
    The analyst review queue. Supports filtering and row-level actions.
    """
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RawEmissionRowDetailSerializer
        return RawEmissionRowListSerializer

    def get_queryset(self):
        qs = (
            RawEmissionRow.objects
            .for_tenant(self.request.tenant)
            .filter(is_deleted=False)
            .select_related("batch")
            .prefetch_related("validation_issues")
            .order_by("-ingested_at")
        )

        # Filtering
        params = self.request.query_params
        if source := params.get("source_type"):
            qs = qs.filter(source_type=source)
        if st := params.get("status"):
            qs = qs.filter(status=st)
        if scope := params.get("scope"):
            qs = qs.filter(scope=scope)
        if batch := params.get("batch"):
            qs = qs.filter(batch_id=batch)
        if q := params.get("search"):
            qs = qs.filter(raw_data__icontains=q)

        return qs

    @action(detail=True, methods=["post"], permission_classes=[
        permissions.IsAuthenticated, IsTenantAnalyst
    ])
    def approve(self, request, **kwargs):
        row = self.get_object()
        if row.validation_issues.filter(severity="ERROR", is_resolved=False).exists():
            return Response(
                {"detail": "Cannot approve a row with unresolved ERROR-level issues."},
                status=400,
            )
        ser = RowActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        before = {"status": row.status}
        row.status = RawEmissionRow.Status.APPROVED
        row.save()

        _write_audit(request, "ROW_APPROVED", row,
                     before=before, after={"status": "APPROVED"},
                     comment=ser.validated_data.get("comment", ""))

        return Response({"status": "approved"})

    @action(detail=True, methods=["post"], permission_classes=[
        permissions.IsAuthenticated, IsTenantAnalyst
    ])
    def reject(self, request, **kwargs):
        row = self.get_object()
        ser = RowActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        before = {"status": row.status}
        row.status = RawEmissionRow.Status.REJECTED
        row.save()

        _write_audit(request, "ROW_REJECTED", row,
                     before=before, after={"status": "REJECTED"},
                     comment=ser.validated_data.get("comment", ""))

        return Response({"status": "rejected"})

    @action(detail=False, methods=["post"], permission_classes=[
        permissions.IsAuthenticated, IsTenantAnalyst
    ])
    def bulk_approve(self, request, **kwargs):
        """Approve multiple rows by ID (WARNING-only rows only)."""
        row_ids = request.data.get("ids", [])
        if not row_ids or len(row_ids) > 500:
            return Response({"detail": "Provide 1–500 row IDs."}, status=400)

        rows = RawEmissionRow.objects.for_tenant(request.tenant).filter(
            id__in=row_ids, is_deleted=False
        )
        batch_event_id = uuid.uuid4()
        approved_count = 0

        with transaction.atomic():
            for row in rows:
                if row.validation_issues.filter(severity="ERROR", is_resolved=False).exists():
                    continue
                before = {"status": row.status}
                row.status = RawEmissionRow.Status.APPROVED
                row.save()
                _write_audit(request, "BULK_APPROVE", row,
                             before=before, after={"status": "APPROVED"},
                             batch_event_id=batch_event_id)
                approved_count += 1

        return Response({"approved": approved_count, "batch_event_id": str(batch_event_id)})


# ─── NORMALIZED ROW EDITS ─────────────────────────────────────────────────────

class NormalizedRowEditView(TenantFromSlugMixin, APIView):
    """
    POST /api/v1/tenants/{tenant_slug}/rows/{row_pk}/edit/
    Create a new version of the normalized row. Old version is kept.
    """
    permission_classes = [permissions.IsAuthenticated, IsTenantAnalyst]

    def post(self, request, tenant_slug, row_pk):
        raw_row = generics.get_object_or_404(
            RawEmissionRow.objects.for_tenant(request.tenant), pk=row_pk
        )
        current = raw_row.normalized_versions.filter(is_current=True).first()
        ser = NormalizedRowEditSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            if current:
                before_state = NormalizedEmissionRowSerializer(current).data
                current.is_current = False
                current.save()
                new_version = current.version + 1
                parent = current
            else:
                before_state = None
                new_version = 1
                parent = None

            new_row = NormalizedEmissionRow.objects.create(
                tenant=request.tenant,
                raw_row=raw_row,
                parent=parent,
                version=new_version,
                is_current=True,
                created_by=request.user,
                **ser.validated_data,
            )

            _write_audit(
                request, "ROW_EDITED", raw_row,
                before=before_state,
                after=NormalizedEmissionRowSerializer(new_row).data,
                comment=request.data.get("comment", ""),
            )

        return Response(NormalizedEmissionRowSerializer(new_row).data, status=201)


# ─── VALIDATION ISSUES ────────────────────────────────────────────────────────

class ValidationIssueResolveView(TenantFromSlugMixin, APIView):
    """POST /api/v1/tenants/{tenant_slug}/issues/{issue_pk}/resolve/"""
    permission_classes = [permissions.IsAuthenticated, IsTenantAnalyst]

    def post(self, request, tenant_slug, issue_pk):
        issue = generics.get_object_or_404(
            ValidationIssue, pk=issue_pk, tenant=request.tenant
        )
        ser = ResolveIssueSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        issue.is_resolved = True
        issue.resolved_by = request.user
        issue.resolved_at = timezone.now()
        issue.resolution_note = ser.validated_data["resolution_note"]
        issue.save()

        _write_audit(
            request, "ISSUE_RESOLVED", issue.raw_row,
            after={"resolved_issue": issue.rule_code,
                   "note": ser.validated_data["resolution_note"]},
        )

        return Response(ValidationIssueSerializer(issue).data)


# ─── AUDIT TRAIL ──────────────────────────────────────────────────────────────

class AuditEventListView(TenantFromSlugMixin, generics.ListAPIView):
    """GET /api/v1/tenants/{tenant_slug}/audit/"""
    serializer_class = AuditEventSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        qs = AuditEvent.objects.filter(
            tenant=self.request.tenant
        ).select_related("actor").order_by("-created_at")

        params = self.request.query_params
        if et := params.get("event_type"):
            qs = qs.filter(event_type=et)
        if actor := params.get("actor"):
            qs = qs.filter(actor__email__icontains=actor)
        if tt := params.get("target_type"):
            qs = qs.filter(target_type=tt)
        if tid := params.get("target_id"):
            qs = qs.filter(target_id=tid)

        return qs


# ─── EMISSION FACTORS (READ-ONLY) ─────────────────────────────────────────────

class EmissionFactorListView(generics.ListAPIView):
    """GET /api/v1/emission-factors/"""
    serializer_class = EmissionFactorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = EmissionFactor.objects.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=datetime.today())
        )
        params = self.request.query_params
        if at := params.get("activity_type"):
            qs = qs.filter(activity_type=at)
        if cc := params.get("country_code"):
            qs = qs.filter(country_code=cc)
        return qs


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _write_audit(request, event_type, target_obj, before=None, after=None,
                 comment="", batch_event_id=None):
    """Write a single audit event record."""
    AuditEvent.objects.create(
        tenant=request.tenant,
        event_type=event_type,
        actor=request.user,
        actor_ip=_get_client_ip(request),
        target_type=target_obj.__class__.__name__,
        target_id=target_obj.pk,
        before_state=before,
        after_state=after,
        comment=comment,
        batch_event_id=batch_event_id,
    )


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
