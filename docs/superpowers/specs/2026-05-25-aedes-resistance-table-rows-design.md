# Aedes Resistance Table Rows Design

## Goal

Promote parsed `Aedes aegypti` resistance supplement rows from `aedes_extracted_facts` into a dedicated source-grade resistance lane.

## Source Boundary

The source id is `aedes_resistance_table_rows`. Input records must already be indexed `aedes_extracted_facts` rows with `lane=resistance`, `fact_type=resistance`, `confidence=parsed`, and a non-empty `fields.table_row`. The lane does not fetch new papers or supplements; it derives from already receipted extracted-fact artifacts.

## Record Shape

Each output record uses lane `resistance` and stores:

- source extracted-fact record id
- source paper id and title
- insecticide terms
- marker or mutation terms
- assay terms
- metric fields such as mortality, knockdown, LC value, and genotype frequency
- table headers, row values, and row index
- `confidence=parsed_table_schema_validated`
- `validation_status=schema_validated`
- `human_validated=false`

Provenance points to `aedes_extracted_facts#<record_id>`, the source literature record when present, and the raw supplement row locator carried by the extracted fact.

## Query Behavior

Questions that mention parsed rows, tables, frequency, genotype, haplotype, mortality, LC50, LC90, or mutation strings such as `V1016G` route to resistance and prefer `aedes_resistance_table_rows` before marker mentions when the question asks for table-like evidence.

## Limits

The lane is schema-validated, not human-reviewed. It does not claim complete resistance-table extraction across every paper and does not replace IR Mapper, WHO guidance, or marker-candidate lanes.
