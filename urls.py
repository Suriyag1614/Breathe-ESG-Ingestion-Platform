"""
Breathe ESG — URL Configuration
=================================
URL structure:
  /api/v1/auth/          — Authentication (JWT + user management)
  /api/v1/tenants/       — Tenant management
  /api/v1/tenants/{slug}/... — All tenant-scoped endpoints
  /api/v1/emission-factors/ — Global reference data
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.views import (
    RegisterView, MeView, UserTenantsView,
    TenantCreateView, TenantDetailView, TenantMembersView,
    DashboardView, DataSourceViewSet, IngestionBatchViewSet,
    FileUploadView, ReviewQueueViewSet, NormalizedRowEditView,
    ValidationIssueResolveView, AuditEventListView,
    EmissionFactorListView,
)

# ─── ROUTERS (nested under tenant slug) ──────────────────────────────────────

# Each router is instantiated fresh to avoid shared state
def make_tenant_router():
    router = DefaultRouter()
    router.register("sources", DataSourceViewSet, basename="datasource")
    router.register("batches", IngestionBatchViewSet, basename="batch")
    router.register("rows", ReviewQueueViewSet, basename="row")
    return router

tenant_router = make_tenant_router()

# ─── AUTH URLS ────────────────────────────────────────────────────────────────

auth_urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", TokenObtainPairView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("tenants/", UserTenantsView.as_view(), name="auth-tenants"),
]

# ─── TENANT-SCOPED URLS ───────────────────────────────────────────────────────

tenant_urlpatterns = [
    # Router-based (viewsets)
    path("", include(tenant_router.urls)),

    # Dashboard
    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    # File upload
    path("upload/", FileUploadView.as_view(), name="upload"),

    # Members
    path("members/", TenantMembersView.as_view(), name="tenant-members"),

    # Row-level actions (separate from the viewset router actions)
    path("rows/<uuid:row_pk>/edit/", NormalizedRowEditView.as_view(), name="row-edit"),

    # Issue resolution
    path("issues/<uuid:issue_pk>/resolve/", ValidationIssueResolveView.as_view(), name="issue-resolve"),

    # Audit trail
    path("audit/", AuditEventListView.as_view(), name="audit"),
]

# ─── TOP-LEVEL v1 URLS ────────────────────────────────────────────────────────

urlpatterns = [
    path("auth/", include(auth_urlpatterns)),
    path("tenants/", TenantCreateView.as_view(), name="tenant-create"),
    path("tenants/<slug:tenant_slug>/", TenantDetailView.as_view(), name="tenant-detail"),
    path("tenants/<slug:tenant_slug>/", include(tenant_urlpatterns)),
    path("emission-factors/", EmissionFactorListView.as_view(), name="emission-factors"),
]
