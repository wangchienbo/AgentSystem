# Repo Introspection Branch

Use this branch for:
- codebase inspection
- configuration tracing
- implementation verification
- repository structure questions

## Guidance

1. Separate three stages clearly:
- locate candidate sources
- read or inspect the most relevant evidence
- stop and answer only after evidence is sufficient for the requested precision

2. Treat search hits as navigation, not as proof.
3. Prefer direct reading/inspection of the most relevant source once a candidate location is found.
4. If multiple candidate files conflict, read enough to resolve the conflict before answering.
5. If the user asks for implementation facts, do not stop at filename/path-level evidence.
6. If the investigation turns into repeated extraction or many dependent steps, switch to the script-first branch.

## Stop Conditions

You may stop when one of these is true:
- a directly relevant source excerpt is enough to answer at the requested precision
- multiple inspected sources align on the same conclusion
- remaining uncertainty cannot be resolved with currently available access, and this is stated explicitly

## Escalate To Script-First When

- many files must be searched and ranked
- content must be extracted repeatedly
- one step's output determines the next step's input repeatedly
- a local parsing helper would be more reliable than many tool turns
