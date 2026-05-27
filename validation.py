"""
Breathe ESG — Validation Engine
================================

Design: Each validator is a pure function that takes a list of parsed row dicts
and returns a list of ValidationIssue-shaped dicts. Pure functions are testable
in isolation without database setup.

The ValidatorRegistry maps source types to their validator suites.
The IngestionPipeline orchestrates validation and writes issues to the DB.

Severity levels:
  ERROR   — Row cannot be approved. Must be corrected or explicitly rejected.
  WARNING — Row can be approved but analyst must acknowledge the issue.
  INFO    — Informational note. No action required.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# IATA airport code: exactly 3 uppercase letters
IATA_PATTERN = re.compile(r"^[A-Z]{3}$")

# ISO 3166-1 alpha-2 country codes (subset of most common)
VALID_COUNTRY_CODES = {
    "AD", "AE", "AF", "AG", "AL", "AM", "AO", "AR", "AT", "AU",
    "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ",
    "BN", "BO", "BR", "BS", "BT", "BW", "BY", "BZ", "CA", "CD",
    "CF", "CG", "CH", "CI", "CL", "CM", "CN", "CO", "CR", "CU",
    "CV", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC",
    "EE", "EG", "ER", "ES", "ET", "FI", "FJ", "FK", "FR", "GA",
    "GB", "GD", "GE", "GH", "GM", "GN", "GQ", "GR", "GT", "GW",
    "GY", "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IN", "IQ",
    "IR", "IS", "IT", "JM", "JO", "JP", "KE", "KG", "KH", "KI",
    "KM", "KN", "KP", "KR", "KW", "KZ", "LA", "LB", "LC", "LI",
    "LK", "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD",
    "ME", "MG", "MH", "MK", "ML", "MM", "MN", "MR", "MT", "MU",
    "MV", "MW", "MX", "MY", "MZ", "NA", "NE", "NG", "NI", "NL",
    "NO", "NP", "NR", "NZ", "OM", "PA", "PE", "PG", "PH", "PK",
    "PL", "PT", "PW", "PY", "QA", "RO", "RS", "RU", "RW", "SA",
    "SB", "SC", "SD", "SE", "SG", "SI", "SK", "SL", "SM", "SN",
    "SO", "SR", "SS", "ST", "SV", "SY", "SZ", "TD", "TG", "TH",
    "TJ", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TZ", "UA",
    "UG", "US", "UY", "UZ", "VA", "VC", "VE", "VN", "VU", "WS",
    "YE", "ZA", "ZM", "ZW",
}

# SAP unit codes → ISO units
SAP_UNIT_MAP = {
    "KG": "kg",
    "TO": "t",   # metric ton
    "LB": "lb",
    "L":  "L",
    "M3": "m3",
    "KWH": "kWh",
    "MJ": "MJ",
    "GJ": "GJ",
    "TH": "therms",  # Non-standard SAP custom unit for natural gas
}

# Valid SAP movement types for fuel/energy goods issues
# 261 = goods issue for production order (consumption)
# 201 = goods issue to cost center
# 551 = scrapping / destruction (can indicate fuel disposal)
VALID_CONSUMPTION_MOVEMENT_TYPES = {"201", "261", "551", "262", "202"}  # incl. reversals


# ─── DATA STRUCTURES ─────────────────────────────────────────────────────────

@dataclass
class ValidationIssueDict:
    rule_code: str
    severity: str  # ERROR / WARNING / INFO
    field_name: str
    field_value: str
    message: str
    row_index: int
    extra: dict = field(default_factory=dict)


# ─── SAP VALIDATORS ───────────────────────────────────────────────────────────

def validate_sap_row(row: dict, row_index: int, config: dict) -> list[ValidationIssueDict]:
    """
    Run all SAP-specific validation rules on a single row.

    config keys:
      plant_country_mapping: dict[str, str]  # e.g. {"1000": "DE", "2000": "US"}
      material_fuel_mapping: dict[str, str]  # e.g. {"500012": "natural_gas"}
      valid_plant_codes: set[str]            # Known plant codes for this tenant
    """
    issues = []

    # ── RULE SAP-001: Missing quantity ────────────────────────────────────────
    menge = row.get("MENGE", "").strip()
    if not menge:
        issues.append(ValidationIssueDict(
            rule_code="SAP_MISSING_QUANTITY",
            severity="ERROR",
            field_name="MENGE",
            field_value="",
            message="Quantity (MENGE) is blank. This row cannot be processed.",
            row_index=row_index,
        ))
    else:
        try:
            qty = float(menge.replace(",", "."))  # Handle European decimal format
            # ── RULE SAP-002: Unexpected negative (non-reversal)
            movement_type = row.get("BWART", "").strip()
            if qty < 0 and movement_type not in {"262", "202", "552"}:
                issues.append(ValidationIssueDict(
                    rule_code="SAP_UNEXPECTED_NEGATIVE_QUANTITY",
                    severity="WARNING",
                    field_name="MENGE",
                    field_value=menge,
                    message=(
                        f"Negative quantity {qty} with movement type {movement_type}. "
                        f"Negative quantities are expected for reversal movement types "
                        f"(262, 202, 552) only. Verify this is a valid correction."
                    ),
                    row_index=row_index,
                ))
            # ── RULE SAP-003: Suspiciously large quantity (order-of-magnitude check)
            if abs(qty) > 1_000_000:
                issues.append(ValidationIssueDict(
                    rule_code="SAP_QUANTITY_OUTLIER",
                    severity="WARNING",
                    field_name="MENGE",
                    field_value=menge,
                    message=(
                        f"Quantity {qty} is unusually large. Verify units are correct "
                        f"(SAP sometimes exports in base units, not purchasing units)."
                    ),
                    row_index=row_index,
                ))
        except ValueError:
            issues.append(ValidationIssueDict(
                rule_code="SAP_INVALID_QUANTITY_FORMAT",
                severity="ERROR",
                field_name="MENGE",
                field_value=menge,
                message=f"Cannot parse quantity '{menge}' as a number. Check decimal separator.",
                row_index=row_index,
            ))

    # ── RULE SAP-004: Unsupported or unmapped unit ─────────────────────────
    meins = row.get("MEINS", "").strip().upper()
    if not meins:
        issues.append(ValidationIssueDict(
            rule_code="SAP_MISSING_UNIT",
            severity="ERROR",
            field_name="MEINS",
            field_value="",
            message="Unit of measure (MEINS) is blank.",
            row_index=row_index,
        ))
    elif meins not in SAP_UNIT_MAP:
        issues.append(ValidationIssueDict(
            rule_code="SAP_UNSUPPORTED_UNIT",
            severity="ERROR",
            field_name="MEINS",
            field_value=meins,
            message=(
                f"SAP unit code '{meins}' is not in the supported unit mapping. "
                f"Supported codes: {sorted(SAP_UNIT_MAP.keys())}. "
                f"Add a mapping in the DataSource configuration to resolve."
            ),
            row_index=row_index,
        ))

    # ── RULE SAP-005: Invalid or unknown plant code ────────────────────────
    werks = row.get("WERKS", "").strip()
    valid_plants = set(config.get("valid_plant_codes", []))
    if not werks:
        issues.append(ValidationIssueDict(
            rule_code="SAP_MISSING_PLANT_CODE",
            severity="ERROR",
            field_name="WERKS",
            field_value="",
            message="Plant code (WERKS) is blank. Cannot determine emission location.",
            row_index=row_index,
        ))
    elif valid_plants and werks not in valid_plants:
        issues.append(ValidationIssueDict(
            rule_code="SAP_UNKNOWN_PLANT_CODE",
            severity="WARNING",
            field_name="WERKS",
            field_value=werks,
            message=(
                f"Plant code '{werks}' is not in the configured plant list for this data source. "
                f"This may indicate a plant from a different business unit was included in the export."
            ),
            row_index=row_index,
        ))

    # ── RULE SAP-006: Material not in fuel mapping ─────────────────────────
    matnr = row.get("MATNR", "").strip().lstrip("0")  # SAP zero-pads material numbers
    fuel_mapping = config.get("material_fuel_mapping", {})
    if fuel_mapping and matnr and matnr not in fuel_mapping:
        issues.append(ValidationIssueDict(
            rule_code="SAP_UNMAPPED_MATERIAL",
            severity="WARNING",
            field_name="MATNR",
            field_value=matnr,
            message=(
                f"Material '{matnr}' ({row.get('MAKTX', 'no description')}) is not in the "
                f"material-to-fuel-type mapping. Emission factor cannot be selected automatically."
            ),
            row_index=row_index,
        ))

    # ── RULE SAP-007: Invalid posting date format ──────────────────────────
    budat = row.get("BUDAT", "").strip()
    if budat:
        try:
            datetime.strptime(budat, "%Y%m%d")
        except ValueError:
            issues.append(ValidationIssueDict(
                rule_code="SAP_INVALID_DATE_FORMAT",
                severity="ERROR",
                field_name="BUDAT",
                field_value=budat,
                message=f"Posting date '{budat}' does not match expected SAP format YYYYMMDD.",
                row_index=row_index,
            ))

    return issues


# ─── UTILITY VALIDATORS ───────────────────────────────────────────────────────

def validate_utility_row(row: dict, row_index: int, config: dict) -> list[ValidationIssueDict]:
    issues = []

    # ── RULE UTIL-001: Negative consumption ───────────────────────────────
    kwh_str = row.get("consumption_kwh", "")
    if kwh_str != "":
        try:
            kwh = float(str(kwh_str))
            if kwh < 0:
                issues.append(ValidationIssueDict(
                    rule_code="UTIL_NEGATIVE_CONSUMPTION",
                    severity="ERROR",
                    field_name="consumption_kwh",
                    field_value=str(kwh_str),
                    message=(
                        f"Negative electricity consumption {kwh} kWh. "
                        f"Negative values are not valid for utility data "
                        f"(unlike SAP reversals). Check source data."
                    ),
                    row_index=row_index,
                ))
        except (ValueError, TypeError):
            issues.append(ValidationIssueDict(
                rule_code="UTIL_INVALID_CONSUMPTION_FORMAT",
                severity="ERROR",
                field_name="consumption_kwh",
                field_value=str(kwh_str),
                message=f"Cannot parse consumption value '{kwh_str}' as number.",
                row_index=row_index,
            ))

    # ── RULE UTIL-002: Missing meter ID ───────────────────────────────────
    meter_id = str(row.get("meter_id", "")).strip()
    if not meter_id:
        issues.append(ValidationIssueDict(
            rule_code="UTIL_MISSING_METER_ID",
            severity="ERROR",
            field_name="meter_id",
            field_value="",
            message=(
                "Meter ID is blank. Without a meter ID, this record cannot be "
                "attributed to a specific facility or deduplication cannot be performed."
            ),
            row_index=row_index,
        ))

    # ── RULE UTIL-003: Invalid billing period ─────────────────────────────
    period_start_str = str(row.get("billing_period_start", "")).strip()
    period_end_str = str(row.get("billing_period_end", "")).strip()

    period_start = None
    period_end = None

    for field_name, date_str, var_name in [
        ("billing_period_start", period_start_str, "period_start"),
        ("billing_period_end", period_end_str, "period_end"),
    ]:
        if not date_str:
            issues.append(ValidationIssueDict(
                rule_code="UTIL_MISSING_PERIOD",
                severity="ERROR",
                field_name=field_name,
                field_value="",
                message=f"Billing period date '{field_name}' is blank.",
                row_index=row_index,
            ))
        else:
            try:
                parsed = date.fromisoformat(date_str)
                if var_name == "period_start":
                    period_start = parsed
                else:
                    period_end = parsed
            except ValueError:
                issues.append(ValidationIssueDict(
                    rule_code="UTIL_INVALID_DATE_FORMAT",
                    severity="ERROR",
                    field_name=field_name,
                    field_value=date_str,
                    message=f"Date '{date_str}' is not in ISO format (YYYY-MM-DD).",
                    row_index=row_index,
                ))

    if period_start and period_end:
        if period_end <= period_start:
            issues.append(ValidationIssueDict(
                rule_code="UTIL_PERIOD_END_BEFORE_START",
                severity="ERROR",
                field_name="billing_period_end",
                field_value=period_end_str,
                message=(
                    f"Billing period end ({period_end}) is not after start ({period_start})."
                ),
                row_index=row_index,
            ))

        # ── RULE UTIL-004: Unusually long billing period ───────────────────
        days = (period_end - period_start).days
        if days > 45:
            issues.append(ValidationIssueDict(
                rule_code="UTIL_LONG_BILLING_PERIOD",
                severity="WARNING",
                field_name="billing_period_end",
                field_value=period_end_str,
                message=(
                    f"Billing period is {days} days. Standard periods are 28-35 days. "
                    f"This may indicate two bills were merged, a skipped read, or a data error."
                ),
                row_index=row_index,
            ))

    # ── RULE UTIL-005: Estimated read ─────────────────────────────────────
    read_type = str(row.get("read_type", "")).strip().upper()
    if read_type == "ESTIMATED":
        issues.append(ValidationIssueDict(
            rule_code="UTIL_ESTIMATED_READ",
            severity="WARNING",
            field_name="read_type",
            field_value=read_type,
            message=(
                "This is an estimated meter read. The actual consumption may differ "
                "significantly. Review against the subsequent actual read."
            ),
            row_index=row_index,
        ))

    return issues


def validate_utility_batch_overlaps(rows: list[dict]) -> list[ValidationIssueDict]:
    """
    Check for overlapping billing periods per meter across the entire batch.
    Must be run after all row-level validation — requires the full row list.
    """
    issues = []
    by_meter: dict[str, list] = {}

    for i, row in enumerate(rows):
        meter_id = str(row.get("meter_id", "")).strip()
        if not meter_id:
            continue
        try:
            ps = date.fromisoformat(str(row.get("billing_period_start", "")))
            pe = date.fromisoformat(str(row.get("billing_period_end", "")))
            by_meter.setdefault(meter_id, []).append((ps, pe, i))
        except ValueError:
            continue  # Row-level validator already flagged the bad date

    for meter_id, periods in by_meter.items():
        sorted_periods = sorted(periods, key=lambda x: x[0])
        for j in range(len(sorted_periods) - 1):
            curr_end = sorted_periods[j][1]
            next_start = sorted_periods[j + 1][0]
            next_row_index = sorted_periods[j + 1][2]
            if curr_end > next_start:
                issues.append(ValidationIssueDict(
                    rule_code="UTIL_BILLING_PERIOD_OVERLAP",
                    severity="ERROR",
                    field_name="billing_period_start",
                    field_value=str(next_start),
                    message=(
                        f"Meter {meter_id}: billing period starting {next_start} overlaps "
                        f"with the previous period ending {curr_end}. "
                        f"This would double-count electricity consumption."
                    ),
                    row_index=next_row_index,
                ))

    return issues


# ─── TRAVEL VALIDATORS ────────────────────────────────────────────────────────

# Airport coordinate database (abbreviated — production uses full IATA DB)
# format: IATA_CODE -> (lat, lon)
AIRPORT_COORDS: dict[str, tuple[float, float]] = {
    "LHR": (51.4775, -0.4614),
    "JFK": (40.6413, -73.7781),
    "LAX": (33.9425, -118.4081),
    "SFO": (37.6213, -122.3790),
    "ORD": (41.9742, -87.9073),
    "DFW": (32.8998, -97.0403),
    "ATL": (33.6407, -84.4277),
    "CDG": (49.0097, 2.5479),
    "AMS": (52.3086, 4.7639),
    "FRA": (50.0379, 8.5622),
    "DXB": (25.2532, 55.3657),
    "SIN": (1.3644, 103.9915),
    "HKG": (22.3080, 113.9185),
    "NRT": (35.7720, 140.3929),
    "SYD": (33.9399, 151.1753),
    "BOM": (19.0896, 72.8656),
    "DEL": (28.5562, 77.1000),
    "GRU": (23.4356, -46.4731),
    "YYZ": (43.6777, -79.6248),
    "MEX": (19.4363, -99.0721),
}

# IATA city codes that are commonly confused for airport codes
IATA_CITY_CODES = {"NYC", "LON", "PAR", "TYO", "CHI", "WAS", "MIL", "BUE"}

VALID_FLIGHT_CLASSES = {"ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance in km using Haversine formula."""
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_travel_row(row: dict, row_index: int, config: dict) -> list[ValidationIssueDict]:
    issues = []

    origin = str(row.get("origin_airport_iata", "")).strip().upper()
    destination = str(row.get("destination_airport_iata", "")).strip().upper()

    # ── RULE TRVL-001: Invalid or missing airport codes ───────────────────
    for field_name, code in [("origin_airport_iata", origin), ("destination_airport_iata", destination)]:
        if not code:
            issues.append(ValidationIssueDict(
                rule_code="TRVL_MISSING_AIRPORT_CODE",
                severity="ERROR",
                field_name=field_name,
                field_value="",
                message=f"Airport code {field_name} is blank. Cannot calculate flight distance.",
                row_index=row_index,
            ))
        elif not IATA_PATTERN.match(code):
            issues.append(ValidationIssueDict(
                rule_code="TRVL_INVALID_AIRPORT_CODE_FORMAT",
                severity="ERROR",
                field_name=field_name,
                field_value=code,
                message=(
                    f"'{code}' is not a valid IATA airport code format (3 uppercase letters). "
                    f"Check the Concur expense report for the correct airport code."
                ),
                row_index=row_index,
            ))
        elif code in IATA_CITY_CODES:
            issues.append(ValidationIssueDict(
                rule_code="TRVL_CITY_CODE_NOT_AIRPORT",
                severity="WARNING",
                field_name=field_name,
                field_value=code,
                message=(
                    f"'{code}' is an IATA city code, not an airport code. "
                    f"For accurate distance calculation, use the specific airport code "
                    f"(e.g., NYC → JFK, LGA, or EWR)."
                ),
                row_index=row_index,
            ))
        elif code not in AIRPORT_COORDS:
            issues.append(ValidationIssueDict(
                rule_code="TRVL_UNKNOWN_AIRPORT_CODE",
                severity="WARNING",
                field_name=field_name,
                field_value=code,
                message=(
                    f"Airport code '{code}' is not in the distance calculation database. "
                    f"Emission factor will be estimated from stated distance if available."
                ),
                row_index=row_index,
            ))

    # ── RULE TRVL-002: Impossible distance check ─────────────────────────
    if origin in AIRPORT_COORDS and destination in AIRPORT_COORDS and origin != destination:
        gc_distance = haversine_km(*AIRPORT_COORDS[origin], *AIRPORT_COORDS[destination])
        stated_distance_str = str(row.get("distance_km", "")).strip()
        if stated_distance_str:
            try:
                stated_distance = float(stated_distance_str)
                ratio = stated_distance / gc_distance if gc_distance > 0 else 0
                if stated_distance < gc_distance * 0.5:
                    issues.append(ValidationIssueDict(
                        rule_code="TRVL_DISTANCE_TOO_SHORT",
                        severity="WARNING",
                        field_name="distance_km",
                        field_value=stated_distance_str,
                        message=(
                            f"Stated distance {stated_distance:.0f} km is less than 50% of the "
                            f"great circle distance {gc_distance:.0f} km ({origin}→{destination}). "
                            f"The stated distance may be in miles, or may be a road distance."
                        ),
                        row_index=row_index,
                    ))
                elif stated_distance > gc_distance * 2.5:
                    issues.append(ValidationIssueDict(
                        rule_code="TRVL_DISTANCE_TOO_LONG",
                        severity="WARNING",
                        field_name="distance_km",
                        field_value=stated_distance_str,
                        message=(
                            f"Stated distance {stated_distance:.0f} km is more than 2.5× the "
                            f"great circle distance {gc_distance:.0f} km. "
                            f"This may indicate a multi-leg itinerary entered as a single row."
                        ),
                        row_index=row_index,
                    ))
            except ValueError:
                pass  # distance_km not parseable, no comparison possible

    # ── RULE TRVL-003: Origin equals destination ──────────────────────────
    if origin and destination and origin == destination and IATA_PATTERN.match(origin):
        issues.append(ValidationIssueDict(
            rule_code="TRVL_SAME_ORIGIN_DESTINATION",
            severity="ERROR",
            field_name="destination_airport_iata",
            field_value=destination,
            message=(
                f"Origin and destination are both '{origin}'. "
                f"A flight cannot depart and arrive at the same airport."
            ),
            row_index=row_index,
        ))

    # ── RULE TRVL-004: Missing trip dates ────────────────────────────────
    departure = str(row.get("departure_datetime", "")).strip()
    if not departure:
        issues.append(ValidationIssueDict(
            rule_code="TRVL_MISSING_DEPARTURE_DATE",
            severity="ERROR",
            field_name="departure_datetime",
            field_value="",
            message=(
                "Departure date is blank. Cannot assign this trip to a reporting period."
            ),
            row_index=row_index,
        ))

    # ── RULE TRVL-005: Missing flight class (non-blocking) ───────────────
    flight_class = str(row.get("flight_class", "")).strip().upper()
    if not flight_class:
        issues.append(ValidationIssueDict(
            rule_code="TRVL_MISSING_FLIGHT_CLASS",
            severity="INFO",
            field_name="flight_class",
            field_value="",
            message=(
                "Flight class is not specified. Defaulting to ECONOMY for emission calculation. "
                "Business class seats have ~3× higher emissions per km. "
                "If executive travel is significant, obtain class data from booking records."
            ),
            row_index=row_index,
        ))
    elif flight_class not in VALID_FLIGHT_CLASSES:
        issues.append(ValidationIssueDict(
            rule_code="TRVL_INVALID_FLIGHT_CLASS",
            severity="WARNING",
            field_name="flight_class",
            field_value=flight_class,
            message=(
                f"'{flight_class}' is not a recognized flight class. "
                f"Valid values: {sorted(VALID_FLIGHT_CLASSES)}."
            ),
            row_index=row_index,
        ))

    return issues


# ─── VALIDATOR REGISTRY ───────────────────────────────────────────────────────

class ValidationPipeline:
    """
    Orchestrates validation for a batch of rows.
    Returns structured issues suitable for database insertion.
    """

    ROW_VALIDATORS = {
        "SAP_FLAT_FILE": validate_sap_row,
        "UTILITY_CSV": validate_utility_row,
        "TRAVEL_CONCUR": validate_travel_row,
    }

    BATCH_VALIDATORS = {
        "UTILITY_CSV": [validate_utility_batch_overlaps],
    }

    def run(
        self,
        rows: list[dict],
        source_type: str,
        config: dict,
    ) -> dict[int, list[ValidationIssueDict]]:
        """
        Returns: dict mapping row_index → list of issues for that row.
        """
        row_validator = self.ROW_VALIDATORS.get(source_type)
        if not row_validator:
            raise ValueError(f"No validator registered for source_type '{source_type}'")

        issues_by_row: dict[int, list[ValidationIssueDict]] = {}

        # Row-level validation
        for i, row in enumerate(rows):
            row_issues = row_validator(row, i, config)
            if row_issues:
                issues_by_row[i] = row_issues

        # Batch-level validation (cross-row checks)
        for batch_validator in self.BATCH_VALIDATORS.get(source_type, []):
            batch_issues = batch_validator(rows)
            for issue in batch_issues:
                issues_by_row.setdefault(issue.row_index, []).append(issue)

        return issues_by_row

    def has_blocking_errors(self, issues: list[ValidationIssueDict]) -> bool:
        return any(i.severity == "ERROR" for i in issues)

    def determine_row_status(self, issues: list[ValidationIssueDict]) -> str:
        """Returns the RawEmissionRow status based on validation results."""
        if not issues:
            return "PENDING"  # No issues → ready for approval
        if self.has_blocking_errors(issues):
            return "NEEDS_REVIEW"  # Has errors → must be reviewed
        # Warnings only → flag but allow approval
        return "NEEDS_REVIEW"
