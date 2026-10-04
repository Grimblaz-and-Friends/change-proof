# Proof v1 fixture provenance

The original schema and these two inputs came from
`Grimblaz-and-Friends/tradecraft@17f0f3abfabc843de1d1258f8a974ff105e01a6b`:

- `skills/work/references/proof-fixtures/v1-valid.json`
- `skills/work/references/proof-fixtures/v1-negative-cases.json`

The pinned `proof-v1.schema.json` extends that revision's schema with optional,
nullable `policy.floor`; the original documents remain valid.

`v1-ci-floor.json` is the shared gate/entrance floor corpus created for change-proof
#44. Each case carries base/head identities and policy content, absence or read
failure; conflicting holder/override inputs; raw paginated run, job and check
records; observation time; a document patch; and expected obligation, selected
check identities and gate verdict. `proof_mode` cases exercise document selection
with standalone historical markers present. Expectations are assertions, never
runtime authority. The corpus includes the exact stall boundary without sleeping.
Repair cases cover dynamic workflows and API-created checks, red runs without jobs,
the current gate's partial rerun and attempt clock, and selection per triggering
event. Run records carry their event; expected executions assert it. Optional
`current_run_id` and `current_run_attempt` model the running gate's identity.
Tradecraft copies this file and schema after the gate half lands.

The gate implements the schema independently. Fixtures are interoperability inputs,
not runtime dependencies.
