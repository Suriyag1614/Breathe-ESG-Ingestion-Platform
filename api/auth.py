"""
Breathe ESG — Authentication & Permissions
===========================================
JWT-based authentication with tenant context injection.
Every authenticated request carries a resolved `request.tenant`.
"""

import hashlib
from rest_framework import permissions, exceptions
from rest_framework_simplejwt.tokens import RefreshToken

from tenants.models import Tenant, TenantMembership


# ─── TENANT RESOLUTION ───────────────────────────────────────────────────────

class TenantFromSlugMixin:
    """
    Resolves the active tenant from the URL kwarg `tenant_slug`.
    Injects `request.tenant` and `request.membership` for downstream use.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        slug = kwargs.get("tenant_slug")
        if not slug:
            raise exceptions.NotFound("Tenant not specified.")

        try:
            tenant = Tenant.objects.get(slug=slug, is_active=True)
        except Tenant.DoesNotExist:
            raise exceptions.NotFound("Tenant not found or inactive.")

        if not request.user or not request.user.is_authenticated:
            raise exceptions.NotAuthenticated()

        try:
            membership = TenantMembership.objects.get(tenant=tenant, user=request.user)
        except TenantMembership.DoesNotExist:
            raise exceptions.PermissionDenied("You are not a member of this tenant.")

        request.tenant = tenant
        request.membership = membership


# ─── PERMISSION CLASSES ───────────────────────────────────────────────────────

class IsTenantMember(permissions.BasePermission):
    message = "You must be a member of this tenant."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and hasattr(request, "tenant")
            and hasattr(request, "membership")
        )


class IsTenantAnalyst(permissions.BasePermission):
    message = "You must be an Analyst or Admin to perform this action."

    def has_permission(self, request, view):
        if not hasattr(request, "membership"):
            return False
        return request.membership.role in ("ANALYST", "ADMIN")


class IsTenantAdmin(permissions.BasePermission):
    message = "You must be a Tenant Admin to perform this action."

    def has_permission(self, request, view):
        if not hasattr(request, "membership"):
            return False
        return request.membership.role == "ADMIN"


class IsAnalystOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not hasattr(request, "membership"):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.membership.role in ("ANALYST", "ADMIN")


# ─── TOKEN HELPERS ────────────────────────────────────────────────────────────

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.get_full_name(),
        },
    }


# ─── FILE HASH UTILITY ────────────────────────────────────────────────────────

def sha256_of_file(file_obj) -> str:
    """Compute SHA-256 of an uploaded file without loading it fully into memory."""
    h = hashlib.sha256()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(8192), b""):
        h.update(chunk)
    file_obj.seek(0)
    return h.hexdigest()