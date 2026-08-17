# Track B Operator Guide

## First-run workflow

1. Open a GeoPilot Project.
2. Choose **Open Track B Command Center**.
3. Select an existing Site, or leave Site empty and enable **Auto-create challenge Site from raster extent** on the first upload.
4. Register the urban T1/T2 organizer evidence.
5. Register the rural T1/T2 organizer evidence.
6. Use the same Site for both dates of a location.
7. Select the before and after datasets.
8. Run `Auto detect` first.
9. If the organizer task specifically requires vegetation, water, built-up or class change, run the corresponding explicit engine.
10. Inspect the change map, metrics, evidence lineage and limitations.
11. Generate the evidence PDF.

## Ingestion choices

### Processed / multiband
Use for a single GeoTIFF/JP2 file. If its internal band descriptions are absent, supply comma-separated band names.

### Band bundle
Use when raw imagery is delivered as separate band files. Supply one band name per file in the same order. Mixed band resolution is supported.

### Sentinel ZIP / SAFE
Upload the organizer archive directly. GeoPilot chooses the highest-resolution candidate available for B02/B03/B04/B08/B11/SCL and preserves the source archive checksum.

## Do not do this during Track B

- Do not use the public Copernicus acquisition provider from the competition workflow.
- Do not import Google Earth or third-party basemap evidence.
- Do not manually type a changed area or percentage into an AI answer.
- Do not mix urban and rural datasets in one temporal pair.
- Do not compare raw T1 against processed T2.
- Do not treat NDVI/NDBI/NDWI change as proof of causation without professional interpretation.

## Acceptance before a judge-facing run
1. Open Track B Command Center and read the **Competition Acceptance Gate**.
2. Do not start the judge mission while status is `BLOCKED`.
3. Confirm both Urban and Rural pairs show ready, the organizer dataset count is non-zero, and closed-evidence mode is enabled.
4. Resolve every blocker shown by the server. The readiness gate validates stored artifact checksums rather than trusting the browser registry alone.
5. Run the full mission only after the gate reports `READY`.

The local demo-fixture generator is for engineering acceptance only. Synthetic fixtures are excluded by the server from automatic Hackathon Mission pairing.
