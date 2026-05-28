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

from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from tenants.models import Tenant, TenantMembership


class TenantFromSlugMixin:
    """
    Resolves tenant + membership BEFORE DRF permission checks run.
    """

    def initial(self, request, *args, **kwargs):
        slug = kwargs.get("tenant_slug")

        tenant = get_object_or_404(Tenant, slug=slug)

        if not request.user or not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        membership = TenantMembership.objects.filter(
            tenant=tenant,
            user=request.user,
        ).first()

        if not membership:
            raise PermissionDenied("Not a tenant member")

        request.tenant = tenant
        request.membership = membership

        # IMPORTANT: call AFTER attaching attributes
        super().initial(request, *args, **kwargs)


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