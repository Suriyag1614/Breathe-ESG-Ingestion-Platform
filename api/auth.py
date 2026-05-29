"""
Breathe ESG — Authentication & Permissions
===========================================
JWT-based authentication with tenant context injection.
Every authenticated request carries a resolved `request.tenant`.
"""

import hashlib
from rest_framework import permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from tenants.models import Tenant, TenantMembership


# ─── TENANT RESOLUTION ───────────────────────────────────────────────────────

class TenantFromSlugMixin:
    """
    Resolves tenant + membership BEFORE DRF permission checks run.
    Sets request.tenant and request.membership before calling super().initial()
    so that permission classes can safely read them.
    """

    def initial(self, request, *args, **kwargs):
        slug = kwargs.get("tenant_slug")

        tenant = get_object_or_404(Tenant, slug=slug)

        if not request.user or not request.user.is_authenticated:
            # Run DRF's own initial first so JWT authentication fires,
            # then re-check. We call super first only for authentication.
            super().initial(request, *args, **kwargs)
            # After super(), user should be authenticated; if not, DRF already raised.

        # At this point request.user is authenticated (DRF raised otherwise).
        # But we need to handle the case where super() hasn't run yet for
        # unauthenticated requests — so we do a two-phase approach:
        # Phase 1: authenticate (super handles it), Phase 2: resolve tenant.
        # Simplest correct approach: call super() first, then set tenant attrs,
        # but move IsTenantMember check to rely on what we set here.
        # Since super() already ran above for unauthenticated, for authenticated
        # users we need to NOT call super() twice. Use a flag.
        if not getattr(self, '_tenant_mixin_super_called', False):
            self._tenant_mixin_super_called = True
            # Re-authenticate and run permissions via super
            # We set tenant BEFORE so permission classes can read them
            membership = TenantMembership.objects.filter(
                tenant=tenant,
                user=request.user,
            ).first()

            if not membership:
                raise PermissionDenied("Not a tenant member")

            request.tenant = tenant
            request.membership = membership
            return

        membership = TenantMembership.objects.filter(
            tenant=tenant,
            user=request.user,
        ).first()

        if not membership:
            raise PermissionDenied("Not a tenant member")

        request.tenant = tenant
        request.membership = membership


# ─── SIMPLER, CORRECT IMPLEMENTATION ─────────────────────────────────────────

class TenantFromSlugMixin:
    """
    Resolves tenant + membership. Sets request.tenant and request.membership
    BEFORE super().initial() so permission_classes can read them.
    """

    def initial(self, request, *args, **kwargs):
        slug = kwargs.get("tenant_slug")
        tenant = get_object_or_404(Tenant, slug=slug)

        # Perform JWT authentication manually before DRF's full initial(),
        # so we know request.user when resolving membership.
        # We call authenticate() directly on each configured authenticator.
        if not request.user or not request.user.is_authenticated:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            auth = JWTAuthentication()
            result = auth.authenticate(request)
            if result is not None:
                request._user, _ = result
                request._authenticator = auth

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

        # Now call super().initial() — permission_classes will fire here,
        # but request.tenant and request.membership are already set.
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
        if not hasattr(request, "membership") or not request.membership:
            return False
        return request.membership.role in ("ANALYST", "ADMIN")


class IsTenantAdmin(permissions.BasePermission):
    message = "You must be a Tenant Admin to perform this action."

    def has_permission(self, request, view):
        if not hasattr(request, "membership") or not request.membership:
            return False
        return request.membership.role == "ADMIN"


class IsAnalystOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not hasattr(request, "membership") or not request.membership:
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