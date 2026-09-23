# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python ETL engine (`etl_pmc`, package under `src/`) that runs as an **Azure Container Apps Job**, replacing only the *transformation engine* portion of an ADF Mapping Data Flow for a Pago Mis Cuentas (PMC) batch process: reads a fixed-width SAP TXT (header/detail/footer), validates records and file-level control totals, enriches detail records from a SQL extract CSV already materialized by ADF, applies PMC business rules, and writes a Banelco/PMC fixed-width output TXT. ADF keeps responsibility for detecting the input file, the SQL bulk extraction, invoking this job, and post-run archival — this container is **not** a web service (no FastAPI/ingress/polling loop), it's a finite batch job.

The full authoritative spec is `docs/Prompt_Container_Apps_ETL_Equivalente_ADF_Poc.md` — read it before changing business rules, the manifest contract, the output layout, or the error taxonomy. `docs/matriz_equivalencia.md` records, field by field, which rules are `CONFIRMADA_ADF` / `PROPUESTA_GUIA` / `SUPUESTO_POC` / `POSTERGADA` and why; `docs/supuestos_y_pendientes.md` lists known limitations and what has actually been run. Treat these three docs as living documents — update them when a rule's status or a limitation changes, don't let them drift from the code.

**No reliable ADF export is available** (the owner withdrew a draft export because the ADF flow itself isn't finished yet). Because of that: the `adf_actual` profile is declared in `etl_pmc.config.layouts` but deliberately has no loadable layout — selecting it raises a clear `LayoutError` rather than silently falling back to `poc_pmc`. Everything implemented runs under `poc_pmc`, whose input-layout positions were derived from the prompt's own tables plus empirical verification against the one real sample file (`docs/entrada_real_1000.txt`, also copied to `tests/fixtures/real/`) — see matrix section 1 for how that verification worked (a control-total cross-check across all 1000 detail records). Don't reintroduce assumptions from a deleted/untrusted source; don't promote anything to `adf_actual` without a real export to back it.

## Commands

```bash
pip install -e ".[dev]"        # editable install + pytest
pytest -q                      # full suite (139 tests as of last run), no Azure needed
pytest -q tests/unit/test_layout_totales.py -k control_de_totales   # single test
etl-pmc run --manifest <path> --local-root <dir> --result-out <path>   # local end-to-end run
compare-adf --adf <file> --container <file> [--redact] [--semantic]
generate-fixture --cantidad 1000 --seed 42 --out <file> --out-enrichment <file>
docker build -t etl-pmc:0.1.0 .
```

## Architecture

`src/etl_pmc/` is organized by pipeline stage, matching the spec's required separation of concerns (raw line → extracted field → typed value → business validation, kept as distinct dataclasses in `models.py`):

- `config/layouts.py` + `config/layout_data/*.json` — declarative fixed-width layouts, versioned per profile. All 1-based-position→Python-slice conversion happens in exactly one place (`FieldSpec.slice()`); nowhere else should do positional arithmetic on a raw line.
- `parsing/` — `reader.py` (streaming line reader: BOM/CRLF/LF policy, no full-file buffering), `identify.py` (record type from layout, not hardcoded digits), `cabecera.py`/`detalle.py`/`pie.py` (extraction + typed conversion), `conversions.py` (the actual typed converters: dates, `Decimal` amounts via comma-decimal parsing, never `float`).
- `validation/detalle.py` — per-record business validity flags + rejection reasons.
- `control/totales.py` — file-level control totals; note `AcumuladorControlArchivo` is the streaming-accumulator version used by the pipeline (population = *all* detail lines read, not just valid ones — a documented POC decision, see matrix §6), while `calcular_control_archivo` is the pure/testable wrapper around it. `control/cabecera.py` is the analogous file-level header check.
- `enrichment/` — `single_configuration.py` (the mode actually wired into output formatting: resolves `CodBancoFinal`/`CodigoServicioFinal`) and `record_join.py` (index-building and validation implemented and tested, but *not* wired to any output field — the poc_pmc output layout doesn't define one; don't invent a field for it).
- `rules/pmc.py` — the 30-day and max-2-per-client filters. Order matters: rank-per-client is computed over the *entire* authorized population first, filters are applied jointly afterward — never "filter then re-rank the survivors" (would silently change which receipts survive).
- `formatting/output.py` — builds the fixed 280-char cabecera/detalle/pie lines. Overflow (an ID or amount that doesn't fit its field) raises `OutputFormatError` rather than silently truncating.
- `manifest.py` — parses/validates the execution manifest (see `examples/manifiesto.example.json`); rejects placeholders, string-typed booleans, wrong-width codes, and path traversal before anything is downloaded.
- `storage/` — `base.py` (the `StorageAdapter` interface the pipeline programs against), `local.py` (filesystem, container=subdir), `azure_blob.py` (real streaming download via a chunked `RawIOBase` wrapper, publish via temp-blob + server-side copy + poll, never assumes copy+delete is atomic), `tempdb.py` (SQLite-backed detail store for the two-pass design — cents stored as `INTEGER`, never `REAL`; pass 2 reads back sorted by `referencia_cliente, primer_vencimiento, id_deuda` which serves both the business-rule ranking order *and* the final output order).
- `pipeline.py` — orchestrates the two passes end to end and produces a `ResultadoEjecucion` (`audit/result.py`; states `SUCCEEDED` / `SUCCEEDED_WITH_REJECTIONS` / `REJECTED` / `FAILED` / `ALREADY_PROCESSED`, mapped to process exit codes — technical success never hides a business-level rejection). Known scaling limitation: pass 2 still materializes the authorized-detail set in Python objects for ranking (fine at ~1000 records, a pending optimization at the ~630k target — see `docs/supuestos_y_pendientes.md`).
- `idempotency.py` — key derived from input hash + enrichment-snapshot hash + profile + layout version + relevant parameters, never just `run_id` or filename.
- `cli.py` — `etl-pmc run`; same core for local and Azure modes. In Azure mode, `--manifest` is `container/blob` and `--storage-account-url` is used *only* to fetch the manifest itself (ADF passes just a manifest location, per the spec).
- `tools/compare_adf.py` / `tools/generate_fixture.py` — the `compare-adf` and `generate-fixture` console scripts (registered in `pyproject.toml`).

`tests/unit/` mirrors this module layout. `tests/integration/` has the full pipeline and CLI run end-to-end against real (`entrada_real_1000.txt`) and synthetic (`generate_fixture`) data, entirely through `LocalStorageAdapter` — no Azure credentials needed to run the suite.

## Working in this codebase

- Money is always `Decimal`, never `float`; centavos in SQLite are `INTEGER`.
- Don't add a rule, field, or default that isn't in the prompt or explicitly confirmed empirically — if something's genuinely unknown, it should surface as a `ConfigurationError`/`EnrichmentError` with a clear message, not a guessed fallback.
- When a POC decision has no ADF confirmation (most of the business-rule/output-layout code), it must already be traceable to a section in `docs/matriz_equivalencia.md` — extend that doc in the same change, don't leave new behavior undocumented.
- No secrets in manifests, images, args, or logs (`storage/azure_blob.py` uses `DefaultAzureCredential`/managed identity only).
- Don't delete or move anything under an `inbound` container from this codebase — that stays ADF's job.
