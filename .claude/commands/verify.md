---
description: Run the independent verifier on a candidate solution CSV
allowed-tools: Bash(python:*), Bash(python3:*)
---
Run the verifier on the candidate at $ARGUMENTS (default ./network.csv). Report: N, the 3 datasets,
whether induced directed isomorphism holds across all three, whether it is weakly connected, and the
detected structure type. If it FAILS, show exactly which check failed and the offending pair/edge/component.
Do not modify any files.