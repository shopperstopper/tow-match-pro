# Build 13 — Apache Current Inventory Integration

## Purpose
Replace the Build 12 legacy inventory compatibility path with the user's current Apache scraper sample and a conservative normalization layer, while hardening the production scraper path around the VDP-aware Apache adapter.

## Source review
The supplied scraper is a useful improvement: it outputs Category and Condition, preserves missing weights, attempts explicit feet/inches length parsing, and includes status/location/image/URL. The supplied 276-row sample exposed four data-quality issues that must not flow directly into Tow Match qualification/presentation:

- catalog-title category detection produced no Fifth Wheel rows;
- 31 compact InteractRV lengths remained encoded as values such as 253/417;
- every price was `$199`, caused by the first-dollar-on-page regex;
- material RV specifications remain legitimately incomplete (70 UVW, 163 GVWR, 89 hitch/pin missing).

## Changes
### Current sample is now the interface inventory
`apache_full_inventory.csv` is the supplied current 276-row sample. `interface_logic.py` no longer reads `apache_full_inventory_legacy.csv` and no longer contains the Build 12 legacy classifier/length shim.

### Apache CSV normalization adapter
Added `adapters/apache_csv.py`.

It:
- maps current scraper columns into the Tow Match engine contract;
- repairs only constrained compact length encodings (253 -> 25'3", 417 -> 41'7");
- normalizes dealer locations and pipeline status;
- treats the sample's `$199` values as unknown rather than presenting a false RV selling price;
- preserves missing UVW/GVWR/hitch values as missing;
- compensates for the sample scraper's catalog-title category limitation with temporary title hints.

The current sample normalizes to:
- 191 Travel Trailer
- 16 Fifth Wheel
- 69 Truck Camper

Those title hints are an interim importer repair, not the desired commercial category source.

### Production Apache scraper path hardened
The production `scrape_apache_specs.py` now invokes the existing VDP-aware `adapters.apache_inventory` scraper rather than the simpler catalog-title-only sample scraper. The user's supplied scraper is retained as `scrape_apache_specs_user_sample.py` for comparison/history.

The VDP-aware path:
- determines category from the VDP page rather than only the catalog anchor title;
- extracts labeled price rather than the first dollar amount anywhere on the page;
- handles compact length normalization;
- logs per-URL extraction/network failures;
- captures broad VDP specifications and provenance;
- never invents missing matching values.

## Architecture
The intended pipeline remains:

Apache website/feed -> Apache acquisition -> normalized Tow Match inventory -> independent matching engine -> salesperson UI

Dealer-specific acquisition/repair stays outside the matching engine.

## Verification
`python -m pytest -q`

Result: **121 passed**.

Additional sample checks:
- 276 rows loaded;
- all three Tow Match RV categories present after normalization;
- no normalized length exceeds 60 ft;
- missing RV weights remain missing;
- bogus `$199` values do not become Tow Match prices;
- pipeline/location normalization verified.

## Next step
Run the salesperson interface against this current normalized sample, then harden the live VDP extraction with representative current Apache pages/fixtures where the sample demonstrates missing or ambiguous data. The interface is no longer dependent on the old inventory snapshot.
