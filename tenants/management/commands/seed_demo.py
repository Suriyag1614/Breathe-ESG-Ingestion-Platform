"""
management/commands/seed_demo.py

Creates a complete demo environment with realistic data for Q1 2024.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --reset   # Drop and recreate all demo data
"""

import uuid
from datetime import date, datetime, timezone
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


DEMO_USERS = [
    {
        "email": "admin@acme-demo.com",
        "password": "BreatheESG2024!",
        "first_name": "Alex",
        "last_name": "Jones",
        "role": "ADMIN",
    },
    {
        "email": "analyst@acme-demo.com",
        "password": "Analyst2024!",
        "first_name": "Maya",
        "last_name": "Chen",
        "role": "ANALYST",
    },
]

DEMO_TENANT = {
    "name": "Acme Corp",
    "slug": "acme-demo",
    "reporting_year": 2024,
    "preferred_unit_system": "metric",
    "emission_factor_methodology": "GHG_PROTOCOL",
    "timezone": "UTC",
}

DEMO_SOURCES = [
    {
        "name": "SAP ECC — Germany Plants (Scope 1)",
        "source_type": "SAP_FLAT_FILE",
        "scope": 1,
        "config": {
            "plant_country_mapping": {
                "1000": "DE",
                "2000": "US",
                "3000": "GB",
                "4000": "PL",
            },
            "material_fuel_mapping": {
                "500012": "natural_gas",
                "500013": "diesel",
                "500014": "lpg",
                "500015": "fuel_oil_no2",
                "500016": "gasoline",
                "500017": "hvo",
                "500018": "coal_bituminous",
            },
            "valid_plant_codes": ["1000", "2000", "3000", "4000"],
        },
    },
    {
        "name": "Utility CSV — Global Electricity (Scope 2)",
        "source_type": "UTILITY_CSV",
        "scope": 2,
        "config": {},
    },
    {
        "name": "Concur Travel — Q1 2024 (Scope 3)",
        "source_type": "TRAVEL_CONCUR",
        "scope": 3,
        "config": {
            "default_class_if_missing": "ECONOMY",
            "radiative_forcing_method": "GHG_PROTOCOL",
        },
    },
]

EMISSION_FACTORS = [
    {
        "activity_type": "FUEL_COMBUSTION",
        "fuel_type": "natural_gas",
        "unit": "m3",
        "co2_factor": "2.0200000000",
        "ch4_factor": "0.0000440000",
        "n2o_factor": "0.0000390000",
        "co2e_factor": "2.0234430000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 Conversion Factors",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FUEL_COMBUSTION",
        "fuel_type": "diesel",
        "unit": "L",
        "co2_factor": "2.6600000000",
        "ch4_factor": "0.0001290000",
        "n2o_factor": "0.0001290000",
        "co2e_factor": "2.6628430000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 Conversion Factors",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FUEL_COMBUSTION",
        "fuel_type": "fuel_oil_no2",
        "unit": "L",
        "co2_factor": "2.5400000000",
        "ch4_factor": "0.0001080000",
        "n2o_factor": "0.0001080000",
        "co2e_factor": "2.5422680000",
        "gwp_version": "AR5",
        "source": "EPA GHG Emission Factors Hub 2023",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FUEL_COMBUSTION",
        "fuel_type": "coal_bituminous",
        "unit": "t",
        "co2_factor": "2456.0000000000",
        "ch4_factor": "2.3000000000",
        "n2o_factor": "4.6000000000",
        "co2e_factor": "2578.4000000000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 Conversion Factors",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FUEL_COMBUSTION",
        "fuel_type": "lpg",
        "unit": "kg",
        "co2_factor": "2.9400000000",
        "ch4_factor": "0.0002200000",
        "n2o_factor": "0.0000640000",
        "co2e_factor": "2.9461960000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 Conversion Factors",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FUEL_COMBUSTION",
        "fuel_type": "gasoline",
        "unit": "L",
        "co2_factor": "2.3100000000",
        "ch4_factor": "0.0002730000",
        "n2o_factor": "0.0001840000",
        "co2e_factor": "2.3150490000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 Conversion Factors",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "ELECTRICITY",
        "fuel_type": "",
        "country_code": "DE",
        "unit": "kWh",
        "co2_factor": "0.3660000000",
        "ch4_factor": "0.0000120000",
        "n2o_factor": "0.0000060000",
        "co2e_factor": "0.3661620000",
        "gwp_version": "AR5",
        "source": "IEA Emission Factors 2023",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "ELECTRICITY",
        "fuel_type": "",
        "country_code": "US",
        "unit": "kWh",
        "co2_factor": "0.3860000000",
        "ch4_factor": "0.0000230000",
        "n2o_factor": "0.0000060000",
        "co2e_factor": "0.3861853000",
        "gwp_version": "AR5",
        "source": "EPA eGRID 2023",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "ELECTRICITY",
        "fuel_type": "",
        "country_code": "GB",
        "unit": "kWh",
        "co2_factor": "0.2070000000",
        "ch4_factor": "0.0000270000",
        "n2o_factor": "0.0000030000",
        "co2e_factor": "0.2071513000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 Conversion Factors",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FLIGHT",
        "fuel_type": "economy_long_haul",
        "unit": "passenger_km",
        "co2_factor": "0.1460000000",
        "ch4_factor": "0.0000000000",
        "n2o_factor": "0.0000000000",
        "co2e_factor": "0.1950000000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 — Passenger vehicles, short haul flights",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FLIGHT",
        "fuel_type": "business_long_haul",
        "unit": "passenger_km",
        "co2_factor": "0.4290000000",
        "ch4_factor": "0.0000000000",
        "n2o_factor": "0.0000000000",
        "co2e_factor": "0.4290000000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 — Passenger vehicles, long haul flights",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "FLIGHT",
        "fuel_type": "first_long_haul",
        "unit": "passenger_km",
        "co2_factor": "0.6110000000",
        "ch4_factor": "0.0000000000",
        "n2o_factor": "0.0000000000",
        "co2e_factor": "0.6110000000",
        "gwp_version": "AR5",
        "source": "DEFRA 2023 — Passenger vehicles, long haul flights",
        "valid_from": date(2023, 1, 1),
    },
]

SAP_ROWS = [
    {
        "MANDT": "100", "WERKS": "1000", "MATNR": "500012",
        "MAKTX": "Natural Gas - Pipeline", "MENGE": "45200.000", "MEINS": "M3",
        "BUDAT": "20240115", "BLDAT": "20240114", "BWART": "261",
        "KOSTL": "COST001", "BUKRS": "DE10", "WAERS": "EUR",
        "DMBTR": "28476.00", "EBELN": "4500001234", "EBELP": "00010",
        "LIFNR": "V0001234", "NAME1": "E.ON Energy Deutschland GmbH",
    },
    {
        "MANDT": "100", "WERKS": "1000", "MATNR": "500013",
        "MAKTX": "Diesel Fuel Grade B", "MENGE": "12500.000", "MEINS": "L",
        "BUDAT": "20240115", "BLDAT": "20240114", "BWART": "261",
        "KOSTL": "COST001", "BUKRS": "DE10", "WAERS": "EUR",
        "DMBTR": "18625.00", "EBELN": "4500001235", "EBELP": "00010",
        "LIFNR": "V0001235", "NAME1": "Deutsche BP GmbH",
    },
    {
        "MANDT": "100", "WERKS": "4000", "MATNR": "500018",
        "MAKTX": "Coal - Bituminous", "MENGE": "250.000", "MEINS": "TO",
        "BUDAT": "20240120", "BLDAT": "20240118", "BWART": "201",
        "KOSTL": "COST004", "BUKRS": "PL10", "WAERS": "PLN",
        "DMBTR": "97500.00", "EBELN": "4500004010", "EBELP": "00010",
        "LIFNR": "V0004001", "NAME1": "Kompania Weglowa SA",
    },
    {
        "MANDT": "100", "WERKS": "1000", "MATNR": "999999",
        "MAKTX": "UNKNOWN MATERIAL - AUDIT", "MENGE": "500.000", "MEINS": "KG",
        "BUDAT": "20240118", "BLDAT": "20240117", "BWART": "261",
        "KOSTL": "COST001", "BUKRS": "DE10", "WAERS": "EUR",
        "DMBTR": "750.00", "EBELN": "4500001300", "EBELP": "00010",
        "LIFNR": "V0001234", "NAME1": "E.ON Energy Deutschland GmbH",
    },
    {
        "MANDT": "100", "WERKS": "2000", "MATNR": "500015",
        "MAKTX": "No. 2 Fuel Oil", "MENGE": "", "MEINS": "L",
        "BUDAT": "20240120", "BLDAT": "20240118", "BWART": "261",
        "KOSTL": "COST002", "BUKRS": "US10", "WAERS": "USD",
        "DMBTR": "0.00", "EBELN": "4500002110", "EBELP": "00010",
        "LIFNR": "V0002002", "NAME1": "ExxonMobil Corporation",
    },
    {
        "MANDT": "100", "WERKS": "5999", "MATNR": "500013",
        "MAKTX": "Diesel Fuel Grade B", "MENGE": "8000.000", "MEINS": "L",
        "BUDAT": "20240121", "BLDAT": "20240120", "BWART": "261",
        "KOSTL": "COST005", "BUKRS": "DE10", "WAERS": "EUR",
        "DMBTR": "11920.00", "EBELN": "4500001310", "EBELP": "00010",
        "LIFNR": "V0001235", "NAME1": "Deutsche BP GmbH",
    },
]

UTILITY_ROWS = [
    {
        "account_number": "ACC-001-2024", "meter_id": "MTR-DE-001",
        "service_address": "Industriestrasse 45, 60329 Frankfurt, DE",
        "billing_period_start": "2024-01-01", "billing_period_end": "2024-01-31",
        "consumption_kwh": "245800.00", "peak_demand_kw": "512.00",
        "cost_usd": "29496.00", "tariff_code": "I-RBT-01", "renewable_pct": "18.5",
        "supplier_name": "E.ON Energie Deutschland", "read_type": "ACTUAL", "notes": "",
    },
    {
        "account_number": "ACC-004-2024", "meter_id": "MTR-US-002",
        "service_address": "1200 Commerce St, Dallas TX 75201, US",
        "billing_period_start": "2024-01-05", "billing_period_end": "2024-02-04",
        "consumption_kwh": "89400.00", "peak_demand_kw": "195.00",
        "cost_usd": "8940.00", "tariff_code": "LGS-TOU", "renewable_pct": "2.1",
        "supplier_name": "Oncor Electric Delivery", "read_type": "ESTIMATED",
        "notes": "Meter access issue",
    },
    {
        "account_number": "ACC-008-2024", "meter_id": "MTR-US-004",
        "service_address": "500 Grant St, Pittsburgh PA 15219, US",
        "billing_period_start": "2024-01-01", "billing_period_end": "2024-01-31",
        "consumption_kwh": "-1200.00", "peak_demand_kw": "0.00",
        "cost_usd": "-120.00", "tariff_code": "LGS-TOU", "renewable_pct": "0.0",
        "supplier_name": "Duquesne Light", "read_type": "ACTUAL",
        "notes": "Credit adjustment",
    },
    {
        "account_number": "ACC-009-2024", "meter_id": "MTR-US-005",
        "service_address": "100 Main St, Denver CO 80203, US",
        "billing_period_start": "2024-01-10", "billing_period_end": "2024-02-10",
        "consumption_kwh": "9200.00", "peak_demand_kw": "24.00",
        "cost_usd": "920.00", "tariff_code": "COM-01", "renewable_pct": "28.0",
        "supplier_name": "Xcel Energy", "read_type": "ACTUAL",
        "notes": "OVERLAPPING PERIOD - SHOULD FAIL VALIDATION",
    },
]

TRAVEL_ROWS = [
    {
        "report_id": "RPT-2024-00412", "employee_id": "EMP-1042",
        "cost_center": "CC-SALES-DE", "expense_type": "AIRFARE",
        "transaction_date": "2024-01-08", "amount_local": "892.00",
        "currency_code": "EUR", "amount_usd": "978.24", "vendor_name": "Lufthansa",
        "origin_city": "Frankfurt", "destination_city": "New York",
        "origin_airport_iata": "FRA", "destination_airport_iata": "JFK",
        "departure_datetime": "2024-01-08T07:45:00",
        "arrival_datetime": "2024-01-08T11:20:00",
        "flight_class": "ECONOMY", "distance_km": "6197", "notes": "",
    },
    {
        "report_id": "RPT-2024-00414", "employee_id": "EMP-3201",
        "cost_center": "CC-EXEC-GB", "expense_type": "AIRFARE",
        "transaction_date": "2024-01-14", "amount_local": "4200.00",
        "currency_code": "GBP", "amount_usd": "5334.00", "vendor_name": "British Airways",
        "origin_city": "London", "destination_city": "Singapore",
        "origin_airport_iata": "LHR", "destination_airport_iata": "SIN",
        "departure_datetime": "2024-01-14T22:00:00",
        "arrival_datetime": "2024-01-15T18:30:00",
        "flight_class": "BUSINESS", "distance_km": "10841", "notes": "",
    },
    {
        "report_id": "RPT-2024-00419", "employee_id": "EMP-8001",
        "cost_center": "CC-EXEC-GB", "expense_type": "AIRFARE",
        "transaction_date": "2024-02-20", "amount_local": "0.00",
        "currency_code": "GBP", "amount_usd": "0.00", "vendor_name": "British Airways",
        "origin_city": "London", "destination_city": "London",
        "origin_airport_iata": "LHR", "destination_airport_iata": "LHR",
        "departure_datetime": "2024-02-20T09:00:00",
        "arrival_datetime": "2024-02-20T10:00:00",
        "flight_class": "ECONOMY", "distance_km": "0",
        "notes": "VALIDATION ERROR: Same origin/destination",
    },
    {
        "report_id": "RPT-2024-00420", "employee_id": "EMP-9112",
        "cost_center": "CC-MKTG-US", "expense_type": "AIRFARE",
        "transaction_date": "2024-02-22", "amount_local": "890.00",
        "currency_code": "USD", "amount_usd": "890.00", "vendor_name": "American Airlines",
        "origin_city": "New York", "destination_city": "Sydney",
        "origin_airport_iata": "NYC", "destination_airport_iata": "SYD",
        "departure_datetime": "2024-02-22T23:00:00",
        "arrival_datetime": "2024-02-24T08:00:00",
        "flight_class": "ECONOMY", "distance_km": "16248",
        "notes": "CITY CODE not airport code for NYC",
    },
]


class Command(BaseCommand):
    help = "Seed the database with demo data for Breathe ESG"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before seeding",
        )

    def handle(self, *args, **options):
        from tenants.models import Tenant, TenantMembership
        from ingestion.models import DataSource, IngestionBatch, RawEmissionRow, ValidationIssue
        from audit.models import AuditEvent
        from emissions.models import EmissionFactor
        from validation import ValidationPipeline

        if options["reset"]:
            self.stdout.write("Resetting demo data...")
            try:
                tenant = Tenant.objects.get(slug="acme-demo")
                AuditEvent.objects.filter(tenant=tenant).delete()
                ValidationIssue.objects.filter(tenant=tenant).delete()
                RawEmissionRow.objects.filter(tenant=tenant).delete()
                IngestionBatch.objects.filter(tenant=tenant).delete()
                DataSource.objects.filter(tenant=tenant).delete()
                TenantMembership.objects.filter(tenant=tenant).delete()
                tenant.delete()
                self.stdout.write("  ✓ Tenant and all related data deleted")
            except Tenant.DoesNotExist:
                pass
            for u in DEMO_USERS:
                User.objects.filter(email=u["email"]).delete()
            EmissionFactor.objects.all().delete()
            self.stdout.write("  ✓ Demo users and emission factors deleted")

        with transaction.atomic():
            users = {}
            for u in DEMO_USERS:
                user, created = User.objects.get_or_create(
                    email=u["email"],
                    defaults={
                        "first_name": u["first_name"],
                        "last_name": u["last_name"],
                        "is_active": True,
                    },
                )
                if created:
                    user.set_password(u["password"])
                    user.save()
                    self.stdout.write(f"  ✓ Created user: {u['email']}")
                else:
                    self.stdout.write(f"  ~ User already exists: {u['email']}")
                users[u["role"]] = user

            tenant, created = Tenant.objects.get_or_create(
                slug=DEMO_TENANT["slug"],
                defaults=DEMO_TENANT,
            )
            if created:
                self.stdout.write(f"  ✓ Created tenant: {tenant.name}")
            else:
                self.stdout.write(f"  ~ Tenant already exists: {tenant.name}")

            for u in DEMO_USERS:
                TenantMembership.objects.get_or_create(
                    tenant=tenant,
                    user=users[u["role"]],
                    defaults={"role": u["role"]},
                )

            for ef_data in EMISSION_FACTORS:
                EmissionFactor.objects.get_or_create(
                    activity_type=ef_data["activity_type"],
                    fuel_type=ef_data.get("fuel_type", ""),
                    country_code=ef_data.get("country_code", ""),
                    valid_from=ef_data["valid_from"],
                    defaults=ef_data,
                )
            self.stdout.write(f"  ✓ Seeded {len(EMISSION_FACTORS)} emission factors")

            sources = {}
            for s in DEMO_SOURCES:
                ds, _ = DataSource.objects.get_or_create(
                    tenant=tenant,
                    name=s["name"],
                    defaults={**s, "created_by": users["ADMIN"]},
                )
                sources[s["source_type"]] = ds
            self.stdout.write(f"  ✓ Created {len(DEMO_SOURCES)} data sources")

            pipeline = ValidationPipeline()

            def create_batch(source_type, filename, rows_data, uploaded_by):
                ds = sources[source_type]
                batch = IngestionBatch.objects.create(
                    tenant=tenant,
                    data_source=ds,
                    status=IngestionBatch.Status.COMPLETED,
                    uploaded_by=uploaded_by,
                    source_filename=filename,
                    source_file_hash=str(uuid.uuid4()).replace("-", ""),
                    row_count_raw=len(rows_data),
                    pipeline_version="1.0.0",
                )

                failed = 0
                raw_rows = []
                for i, row_dict in enumerate(rows_data):
                    issues_by_row = pipeline.run([row_dict], source_type, ds.config or {})
                    issues = issues_by_row.get(0, [])
                    has_error = any(iss.severity == "ERROR" for iss in issues)
                    row_status = "NEEDS_REVIEW" if issues else "PENDING"

                    raw_row = RawEmissionRow.objects.create(
                        tenant=tenant,
                        batch=batch,
                        row_index=i,
                        source_type=source_type,
                        scope=ds.scope,
                        raw_data=row_dict,
                        status=row_status,
                    )
                    for iss in issues:
                        ValidationIssue.objects.create(
                            raw_row=raw_row,
                            tenant=tenant,
                            rule_code=iss.rule_code,
                            severity=iss.severity,
                            field_name=iss.field_name,
                            field_value=iss.field_value,
                            message=iss.message,
                        )
                    if has_error:
                        failed += 1
                    raw_rows.append(raw_row)

                for bv in pipeline.BATCH_VALIDATORS.get(source_type, []):
                    for iss in bv(rows_data):
                        if iss.row_index < len(raw_rows):
                            ValidationIssue.objects.create(
                                raw_row=raw_rows[iss.row_index],
                                tenant=tenant,
                                rule_code=iss.rule_code,
                                severity=iss.severity,
                                field_name=iss.field_name,
                                field_value=iss.field_value,
                                message=iss.message,
                            )

                batch.row_count_valid = len(rows_data) - failed
                batch.row_count_failed = failed
                batch.save()
                return batch, raw_rows

            sap_batch, sap_rows = create_batch(
                "SAP_FLAT_FILE", "sap_fuel_q1_2024.csv", SAP_ROWS, users["ANALYST"]
            )
            util_batch, util_rows = create_batch(
                "UTILITY_CSV", "utility_electricity_q1_2024.csv", UTILITY_ROWS, users["ANALYST"]
            )
            travel_batch, travel_rows = create_batch(
                "TRAVEL_CONCUR", "travel_concur_q1_2024.csv", TRAVEL_ROWS, users["ANALYST"]
            )
            self.stdout.write(
                f"  ✓ Created 3 ingestion batches "
                f"({len(sap_rows) + len(util_rows) + len(travel_rows)} rows total)"
            )

            approvable = [
                r for r in (sap_rows + util_rows + travel_rows)
                if r.status == "PENDING"
            ]
            for row in approvable:
                row.status = "APPROVED"
                row.save()
                AuditEvent.objects.create(
                    tenant=tenant,
                    event_type="ROW_APPROVED",
                    actor=users["ANALYST"],
                    actor_ip="203.0.113.42",
                    target_type="RawEmissionRow",
                    target_id=row.pk,
                    before_state={"status": "PENDING"},
                    after_state={"status": "APPROVED"},
                    comment="Reviewed and confirmed. Values within expected range.",
                )

            for batch in (sap_batch, util_batch, travel_batch):
                AuditEvent.objects.create(
                    tenant=tenant,
                    event_type="BATCH_UPLOADED",
                    actor=users["ANALYST"],
                    actor_ip="203.0.113.42",
                    target_type="IngestionBatch",
                    target_id=batch.pk,
                    after_state={
                        "status": "COMPLETED",
                        "filename": batch.source_filename,
                        "rows_parsed": batch.row_count_raw,
                        "rows_failed": batch.row_count_failed,
                    },
                )

        self.stdout.write(self.style.SUCCESS("\n✓ Demo seeding complete\n"))
        self.stdout.write("=" * 56)
        self.stdout.write("DEMO CREDENTIALS")
        self.stdout.write("=" * 56)
        for u in DEMO_USERS:
            self.stdout.write(f"  Role:     {u['role']}")
            self.stdout.write(f"  Email:    {u['email']}")
            self.stdout.write(f"  Password: {u['password']}")
            self.stdout.write("")
        self.stdout.write(f"  Tenant:   {DEMO_TENANT['slug']}")
        self.stdout.write("=" * 56)