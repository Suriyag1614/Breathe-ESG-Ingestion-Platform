from django.contrib import admin
from .models import EmissionFactor, EmissionCalculation


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = [
        "activity_type", "fuel_type", "country_code",
        "unit", "co2e_factor", "source", "valid_from", "valid_to",
    ]
    list_filter = ["activity_type", "gwp_version", "country_code"]
    search_fields = ["activity_type", "fuel_type", "source"]


@admin.register(EmissionCalculation)
class EmissionCalculationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "tenant", "normalized_row", "co2e_kg",
        "calculation_method", "calculated_at", "calculator_version",
    ]
    list_filter = ["calculation_method", "calculator_version"]
    search_fields = ["tenant__slug"]
    readonly_fields = ["id", "calculated_at"]
