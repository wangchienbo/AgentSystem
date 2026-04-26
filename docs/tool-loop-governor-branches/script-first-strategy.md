# Script-First Strategy Branch

Use this branch when the task is better solved by writing and running a script than by many fragmented tool calls.

## Strong Signals For Script-First

- second-step input depends on first-step output
- repeated parsing / filtering / extraction is needed
- many files or commands must be traversed and summarized
- structured aggregation is needed before an answer can be produced
- the same logic may be reusable for later validation or regression

## Guidance

1. Prefer a small, local, purpose-built script over a long tool-call chain.
2. Keep the script narrow and auditable.
3. Write the script so its output is directly useful for the answer.
4. If possible, make the script emit structured output.
5. After script execution, answer from the script result rather than mentally recomputing from raw intermediate fragments.

## Safety / Discipline

- keep the script scoped to the current task
- prefer reversible/local effects unless the task explicitly requires mutation
- preserve the script when it may be useful for regression or repeated validation
