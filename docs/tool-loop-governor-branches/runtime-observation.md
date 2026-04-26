# Runtime Observation Branch

Use this branch for:
- process state
- service health
- current runtime configuration in effect
- network reachability or live system observations

## Guidance

1. Distinguish runtime observation from source-code fact.
2. Prefer current live evidence over remembered assumptions.
3. If the user asks what the system is doing now, do not answer from static code alone.
4. If one command can only partially observe the state, choose the next command that resolves the most important missing runtime fact.
5. If several commands/observations must be combined, consider switching to the script-first branch.

## Stop Conditions

You may stop when:
- the live question has a direct current observation
- repeated observations converge on the same runtime conclusion
- additional probing has low value relative to cost and risk, and uncertainty is stated explicitly
