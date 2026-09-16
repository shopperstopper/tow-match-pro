# Build 02 — Apache Adapter Validation

## Result
The normalized adapter architecture is ready to serve as the ingestion boundary for Tow Match Pro. It now has offline regression fixtures for all three v1 RV categories and a reusable inventory-completeness reporter.

## Representative Apache patterns validated

### Travel Trailer
Observed live Apache VDP fields include Sleeps, Slides, Length, Hitch Weight, GVWR, Dry Weight, Cargo Capacity, fresh/gray/black water, tire size, axle weight/count, LP data and VIN. Both correctly formatted lengths (for example 24 ft 2 in) and malformed compact InteractRV values (for example 330 ft) occur.

### Fifth Wheel
Observed live Apache VDPs use the same core towable weight labels as Travel Trailers, including Hitch Weight (treated by the later matching engine as published pin data), GVWR, Dry Weight and Cargo Capacity.

### Truck Camper
Observed live Apache VDPs can include Dry Weight, Fresh Water Capacity, Truck Bed Size, Body Style, LP data and Center of Gravity Front. Not every camper publishes every weight field; missing values must therefore survive ingestion as missing so Rule 106 can later distinguish Unable to Verify from Not Match.

## Fix added during validation
`Center of Gravity Front` is now recognized as a truck-camper CG source label. The parser already supported `CG Front`; Apache uses both kinds of terminology across manufacturer data.

## Tests
9 tests pass, including representative TT, Fifth Wheel and Truck Camper VDP fixtures, compact-length normalization, category detection, and the prohibition on silent matching defaults.

## Commercial architecture implication
The Apache scraper is only one adapter. Future dealer feeds should map into the same `InventoryRecord` schema and run through the same completeness checks. No matching-engine code should know whether inventory came from Apache HTML, CSV, XML, JSON, an API, or a DMS/website feed.
