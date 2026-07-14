# Ask Insects to Ask Monarch Context Bridge Plan

1. Add failing tests for package validation, exact-species selection,
   deterministic hashing, provenance, bounded selectors, and private-field
   rejection.
2. Add the versioned assay-context configuration and package builder.
3. Add local and hosted `context-package` surfaces.
4. Add completion-gate, source-map, and operator documentation checks.
5. Run focused tests, the full Ask Insects suite, and
   `python3 scripts/verify_complete.py`.
6. Merge and deploy Ask Insects, then verify the package through the installed
   hosted CLI.
7. Import the exact hosted package into a new Ask Monarch
   `ask_insects_context` source lane with receipts and atomic SQLite units.
8. Add the explicit private assay-family to scientific-species map.
9. Add a hosted private experiment-interpretation endpoint and CLI command.
10. Add natural Ask Monarch routing and skill guidance for experiment
    interpretation.
11. Build a blinded historical evaluation across SWD, mosquito, and DBM cases.
12. Fix every provenance, calibration, mapping, and interpretation failure
    until the bridge beats the baseline without regressions or unsupported
    claims.
13. Merge, deploy, refresh installed skills, and verify the complete live path.
