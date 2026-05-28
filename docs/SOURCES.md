# SOURCES — Research, Data Formats, and Production Constraints

## How This Document Is Organized

Each section covers a data source type: what was researched, what a realistic integration looks like, what the typical data structure is, and — critically — what would break in production that a demo never reveals.

---

## SAP Fuel & Procurement Data

### Research Basis

- SAP FI/MM module documentation (procurement-to-pay process flow)
- SAP ECC vs. S/4HANA transaction code differences (ME21N, MB51, MIGO)
- IDoc MATMAS, INVOIC, and MBGMCR message types for goods movement
- OData service `/sap/opu/odata/sap/MM_PUR_PO_MAINT_V2_SRV` for purchasing orders
- BAPI `BAPI_MATERIAL_GETLIST` and `MB_CREATE_GOODS_MOVEMENT` signatures
- SAP S/4HANA Cloud Central Finance integration documentation

### Why Flat File Export Was Chosen

The SAP integration choice is not a technical choice — it is a procurement and organizational politics choice. Here is what actually happens when you try to do direct SAP API integration at an enterprise customer:

1. The customer's SAP BASIS team must approve all external API connections. This requires a security review, often 4-12 weeks.
2. The customer may be running SAP ECC 6.0 (legacy, pre-OData) where building an integration requires custom RFC function modules.
3. SAP licensing: many enterprise license agreements include restrictions on third-party applications calling BAPI or OData APIs without purchasing additional middleware licenses.
4. Network security: SAP application servers are typically on a private network segment. External access requires firewall rule changes that require change management approval.

Flat file export sidesteps all of this. An AP clerk with standard reporting access can run transaction `MB51` (Material Document List) or use SAP's built-in report `CKMVFM` and export to CSV. No IT involvement required.

### Typical SAP Fuel/Procurement Export Fields

```
MANDT       - Client (usually filtered to single value, can be ignored)
WERKS       - Plant code (e.g., "1000" = Hamburg Plant)
MATNR       - Material number (18 chars, right-padded with spaces — a known parsing trap)
MAKTX       - Material description
MENGE       - Quantity in base unit
MEINS       - Base unit of measure (SAP internal code, not ISO, e.g. "TO" = metric ton, "ST" = piece)
BUDAT       - Posting date (format YYYYMMDD, not ISO 8601)
BLDAT       - Document date
BWART       - Movement type ("261" = goods issue for production order)
KOSTL       - Cost center
BUKRS       - Company code
WAERS       - Currency key
DMBTR       - Amount in local currency
EBELN       - Purchase order number
EBELP       - PO item number
LIFNR       - Vendor account number
NAME1       - Vendor name (from LFA1 table, requires join — may be absent in flat export)
```

### Real-World Parsing Challenges

**Challenge 1: MATNR trailing spaces.** SAP material numbers are stored as 18-character right-padded strings. "DIESEL" is stored as "DIESEL            " (with 12 trailing spaces). A naive CSV parser will include these spaces in the value. This causes join failures when matching against a material classification table.

**Challenge 2: MEINS unit codes are SAP-internal, not ISO.** SAP uses "TO" for metric ton (ISO uses "t"), "M3" for cubic meter (ISO uses "m³"), "KG" (same as ISO), "L" (same as ISO). The unit conversion layer must map SAP units to ISO units before applying emission factors. Missing mappings silently produce wrong calculations.

**Challenge 3: BUDAT date format.** SAP exports dates as `YYYYMMDD` (e.g., `20240215`), not ISO 8601 (`2024-02-15`). Python's default `datetime.fromisoformat()` will reject this and raise an uncaught exception if not handled.

**Challenge 4: No direct link between goods movement and fuel type.** SAP material numbers map to fuel types only through the material master (table MARA/MAKT). The flat file export usually doesn't include MARA data. The mapping must be provided as a configuration file by the customer (e.g., "material 500012 = Natural Gas") or inferred from the material description, which is unreliable.

**Challenge 5: Negative quantities are valid.** Movement type "262" is a reversal of "261". A goods reversal produces a negative MENGE. These are not errors — they are valid accounting entries. The validation layer must not flag negative quantities as errors for SAP data; it must flag only unexpected negative quantities.

### Assumptions Made for This Implementation

1. The customer provides a plant-to-country mapping (plant code → ISO country code), since plant location is not always in the flat file export.
2. The customer provides a material-to-fuel-type mapping.
3. Dates are in `YYYYMMDD` format.
4. The file is UTF-8 or Latin-1 encoded (SAP defaults to Latin-1/ISO-8859-1 for older systems — this must be handled).

---

## Utility Electricity Data

### Research Basis

- Green Button Data standard (NAESB REQ.21) — XML schema for utility interval data
- ENERGY STAR Portfolio Manager API documentation
- Typical utility portal export formats from PG&E, ConEdison, Eversource, National Grid
- Utility billing period conventions (calendar month vs. meter read cycle)
- ISO 15118 for EV charging data (referenced but not used)

### Why CSV Export Was Chosen

Green Button Data (XML) is the standard, but adoption is inconsistent. Major US utilities support it; smaller regional utilities and international utilities often do not. Energy management systems (Schneider EcoStruxure, Siemens Desigo, JLL Yardi) all export CSV. PDF OCR was rejected because:

- Utility bill layouts change with every billing system upgrade (happened twice in 2022 with major US utilities)
- Multi-page bills with demand charges, power factor corrections, and tax line items produce unreliable OCR extraction
- Error rates of 5-15% for PDF OCR would create more analyst review work than the automation saves

### Typical Utility CSV Export Structure

```
account_number      - Utility account identifier (not the meter ID — a single account can have multiple meters)
meter_id            - Physical meter serial number or METASYS point identifier  
service_address     - Physical address of the meter
billing_period_start- Start date of billing period (YYYY-MM-DD)
billing_period_end  - End date of billing period (YYYY-MM-DD)
consumption_kwh     - Total kWh consumed in period
peak_demand_kw      - Peak demand (kW) — for demand-charge tariffs
consumption_therms  - Gas consumption (if dual-fuel account)
cost_usd            - Total bill amount
tariff_code         - Rate schedule code (e.g., "E-20P" = PG&E Medium Commercial)
renewable_pct       - % of supply from renewable sources (for market-based Scope 2)
supplier_name       - Utility company name
read_type           - ACTUAL / ESTIMATED / CUSTOMER_READ
```

### Real-World Challenges

**Challenge 1: Billing periods don't align with calendar months.** A meter read might occur on the 17th of each month. If you need January electricity consumption, you're actually looking at a period from Dec 17 to Jan 17. Comparing across facilities or computing monthly totals requires period proration, which the validation layer must flag as requiring analyst attention.

**Challenge 2: Estimated reads.** Utilities issue estimated bills when a meter reader can't access the site. The `read_type = ESTIMATED` rows need flagging — an estimated read for a facility that was closed for renovation is wildly wrong.

**Challenge 3: Account vs. meter granularity.** A large office building might have one utility account but 50 submeters for different floors or HVAC zones. ESG reporting typically requires building-level totals, but the ingestion system receives meter-level data. The aggregation must be correct.

**Challenge 4: Units.** US utilities use kWh. Some UK utilities export in kVAh. Some gas meters export in cubic feet, others in therms, others in MJ. The unit normalization layer must handle all of these correctly. A factor-of-3 error from therms vs. MJ is enough to materially misstate Scope 2 emissions.

**Challenge 5: Reactive power in kVAh vs. real power in kWh.** An industrial customer's submetered data might include reactive power consumption, which should not be used for emission calculations. The validation layer flags kVAh readings and requires confirmation.

### Billing Period Overlap Validation Logic

```python
def check_billing_period_overlaps(rows: list[UtilityRow], meter_id: str) -> list[ValidationIssue]:
    meter_rows = sorted(
        [r for r in rows if r.meter_id == meter_id],
        key=lambda r: r.billing_period_start
    )
    issues = []
    for i in range(len(meter_rows) - 1):
        current = meter_rows[i]
        next_row = meter_rows[i + 1]
        if current.billing_period_end > next_row.billing_period_start:
            issues.append(ValidationIssue(
                rule_code="BILLING_PERIOD_OVERLAP",
                severity="ERROR",
                message=f"Meter {meter_id}: period ending {current.billing_period_end} "
                        f"overlaps with period starting {next_row.billing_period_start}"
            ))
    return issues
```

---

## Corporate Travel Data (Concur)

### Research Basis

- SAP Concur Expense Report API v4 documentation
- Concur Intelligence reporting module export schemas
- IATA airport code database (14,000+ codes, updated monthly)
- ICAO aircraft type codes (used for flight emission factor selection)
- GHG Protocol Corporate Value Chain Standard, Chapter 6 (Business Travel)
- DEFRA 2023 passenger transport emission factors (flights, rail, taxi)

### Concur Export Schema (Expense Report Detail)

```
report_id             - Unique expense report identifier
employee_id           - Employee ID (masked in our sample data)
cost_center           - Organizational cost center
expense_type          - AIRFARE / HOTEL / TAXI / TRAIN / CAR_RENTAL / MEAL
transaction_date      - Date of expense
amount_local          - Amount in local currency
currency_code         - ISO 4217 currency code
amount_usd            - Reimbursed USD amount
vendor_name           - Airline name, hotel name, etc.
origin_city           - For travel expenses: departure city
destination_city      - For travel expenses: arrival city
origin_airport_iata   - IATA airport code (3 letters, e.g., LHR)
destination_airport_iata - IATA airport code
departure_datetime    - For flights
arrival_datetime      - For flights
flight_class          - ECONOMY / PREMIUM_ECONOMY / BUSINESS / FIRST
hotel_city            - For hotel stays
hotel_check_in        - Date
hotel_check_out       - Date
hotel_nights          - Computed or stated
distance_km           - Stated distance (unreliable — see challenges)
```

### Flight Emission Calculation Challenges

**Challenge 1: Radiative forcing multiplier.** The GHG Protocol recommends applying a radiative forcing index (RFI) of 1.9 to flight emissions to account for high-altitude warming effects (contrails, cirrus cloud formation). DEFRA 2023 has discontinued the uplift factor, citing scientific uncertainty. This is an active methodological debate. The system must record which methodology was used.

**Challenge 2: Flight class multiplier.** A business class seat has approximately 3x the emission per km of an economy seat (due to the larger physical space per passenger). If Concur data doesn't include `flight_class`, we default to economy, which understates emissions for executive travel. The validation layer should flag missing flight class data with a WARNING (not an error) and note the defaulting assumption.

**Challenge 3: IATA airport code validation is not sufficient.** There are legitimate 3-letter codes that are not valid IATA airport codes (e.g., Concur sometimes exports city codes like "NYC" instead of the specific airport code "JFK", "LGA", or "EWR"). The validation layer must distinguish between valid IATA codes and IATA city codes, and flag city codes as needing disambiguation.

**Challenge 4: Great circle distance vs. actual flight path.** The most accurate approach is to look up the great circle distance between origin and destination airports from a database. Some customers provide a `distance_km` field from Concur, but this is sometimes the road distance between city centers, not the flight distance. Our system computes great circle distance from airport coordinates and flags large discrepancies.

**Challenge 5: Connecting flights.** A Concur report might show a single expense line for "LHR → SFO" when the actual itinerary was "LHR → JFK → SFO". The emission factors differ significantly (one long-haul flight vs. two). Without itinerary details, we calculate direct distance, which understates emissions for routing through hub airports. This is flagged as a limitation.

---

## What Would Break in Production

These are failure modes that a demo never reveals but would surface within 60 days of real customer onboarding:

1. **Timezone-naive billing periods.** The first customer in an unexpected timezone (e.g., India Standard Time with its 30-minute offset) would expose any code that assumes UTC or whole-hour offsets.

2. **Non-UTF-8 file encodings.** SAP older systems export Latin-1. Excel on Windows exports CP1252. Python's `open()` will raise `UnicodeDecodeError` on these files. The ingestion layer must detect encoding before parsing.

3. **Excel files masquerading as CSVs.** Users often export from Excel and save as `.csv`, which may be tab-delimited, pipe-delimited, or have BOM characters. The parser must auto-detect delimiter.

4. **Currency amounts with locale-specific formatting.** A German SAP system exports `1.234,56` (period as thousands separator, comma as decimal). Python's `float("1.234,56")` raises ValueError.

5. **Duplicate file uploads from different users.** Without the SHA-256 file hash deduplication check, two analysts uploading the same file from different accounts would double-count emissions.

6. **Concur data lag.** Expense reports are submitted after travel, sometimes 30-60 days later. A Scope 3 analysis for Q4 that is run in January will be materially incomplete. The system should flag that travel data may be lagged and recommend a "data freeze" date policy.
