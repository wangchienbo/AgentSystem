# Stop Rules Branch

Use this branch when deciding whether to continue calling tools, stop and answer, or switch to a script.

## Continue Calling Tools When

- a concrete unresolved question remains
- the next action is likely to materially reduce uncertainty
- current evidence is only navigational or partial

## Stop And Answer When

- the user-requested precision has been achieved
- the next tool call has low expected value
- more actions are unlikely to change the conclusion materially

## Switch To Script When

- the task is becoming a dependency chain
- many serial tool turns are emerging
- structured extraction or aggregation is the real task

## Avoid

- calling more tools without a named unresolved question
- answering just because some relevant-looking evidence appeared
- continuing to probe after the requested precision is already achieved
