"""
emissions/models.py
Contains: EmissionFactor, EmissionCalculation
"""
import uuid
from django.db import models


class EmissionFactor(models.Model):
    """
    Reference data mapping activity types to GHG emission factors.
    Shared across tenants but versioned so methodology changes are tracked.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_type = models.CharField(max_length=50)
    fuel_type = models.CharField(max_length=50, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    region = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=30)
    co2_factor = models.DecimalField(max_digits=18, decimal_places=10)
    ch4_factor = models.DecimalField(max_digits=18, decimal_places=10, null=True, blank=True)
    n2o_factor = models.DecimalField(max_digits=18, decimal_places=10, null=True, blank=True)
    co2e_factor = models.DecimalField(max_digits=18, decimal_places=10)
    gwp_version = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=200)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "emissions_emissionfactor"
        indexes = [
            models.Index(fields=["activity_type", "valid_from", "valid_to"]),
            models.Index(fields=["country_code"]),
        ]

    def __str__(self):
        return f"{self.activity_type} / {self.fuel_type} ({self.source})"


class EmissionCalculation(models.Model):
    """
    The computed GHG output for a normalized row.
    Kept separate so calculations can be re-run when emission factors update.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="calculations"
    )
    normalized_row = models.ForeignKey(
        "ingestion.NormalizedEmissionRow",
        on_delete=models.CASCADE,
        related_name="calculations",
    )
    emission_factor = models.ForeignKey(
        "emissions.EmissionFactor",
        on_delete=models.PROTECT,
        related_name="calculations",
    )
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=6)
    co2_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    ch4_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    n2o_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    calculation_method = models.CharField(
        max_length=50,
        choices=[("ACTIVITY_BASED", "Activity Based"), ("SPEND_BASED", "Spend Based")],
        default="ACTIVITY_BASED",
    )
    calculated_at = models.DateTimeField(auto_now_add=True)
    calculator_version = models.CharField(max_length=20, default="1.0.0")

    class Meta:
        db_table = "emissions_emissioncalculation"
        indexes = [
            models.Index(fields=["normalized_row"]),
            models.Index(fields=["tenant", "calculated_at"]),
        ]

    def __str__(self):
        return f"Calc {self.id} → {self.co2e_kg} kg CO2e"
