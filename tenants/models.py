"""
tenants/models.py
Contains: Tenant, User, TenantMembership
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


# ─── USER MANAGER ────────────────────────────────────────────────────────────

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


# ─── TENANT ──────────────────────────────────────────────────────────────────

class Tenant(models.Model):
    """
    Root entity for multi-tenancy.
    Every other model carries a FK to Tenant.
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


# ─── USER ─────────────────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):
    """
    Platform user. Email is the primary identifier, not username.
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


# ─── TENANT MEMBERSHIP ────────────────────────────────────────────────────────

class TenantMembership(models.Model):
    """
    Many-to-many between User and Tenant with role.
    A user can belong to multiple tenants with different roles in each.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        ANALYST = "ANALYST", "Analyst"
        VIEWER = "VIEWER", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        "tenants.User", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=30, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        "tenants.User",
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