"""
Breathe ESG — URL Configuration
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

tenant_router = DefaultRouter()
tenant_router.register("sources", DataSourceViewSet, basename="datasource")
tenant_router.register("batches", IngestionBatchViewSet, basename="batch")
tenant_router.register("rows", ReviewQueueViewSet, basename="row")

auth_urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", TokenObtainPairView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("tenants/", UserTenantsView.as_view(), name="auth-tenants"),
]

tenant_urlpatterns = [
    path("", include(tenant_router.urls)),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("upload/", FileUploadView.as_view(), name="upload"),
    path("members/", TenantMembersView.as_view(), name="tenant-members"),
    path("rows/<uuid:row_pk>/edit/", NormalizedRowEditView.as_view(), name="row-edit"),
    path("issues/<uuid:issue_pk>/resolve/", ValidationIssueResolveView.as_view(), name="issue-resolve"),
    path("audit/", AuditEventListView.as_view(), name="audit"),
]

urlpatterns = [
    path("auth/", include(auth_urlpatterns)),
    path("tenants/", TenantCreateView.as_view(), name="tenant-create"),
    path("tenants/<slug:tenant_slug>/", TenantDetailView.as_view(), name="tenant-detail"),
    path("tenants/<slug:tenant_slug>/", include(tenant_urlpatterns)),
    path("emission-factors/", EmissionFactorListView.as_view(), name="emission-factors"),
]