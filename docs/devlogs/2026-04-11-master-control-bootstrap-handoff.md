# 2026-04-11 Master control bootstrap handoff

## Summary
Extended the meta-skill / master-control contract so the meta-skill must invoke the generated master control skill for first-run initialization instead of stopping at file generation.

## Key rule
- meta-skill may trigger initialization
- but any subordinate skill creation during initialization belongs to the master control skill acting in its own role

## AgentSystem updates
- added structural subordinate candidate artifact
- added first-run initialization section to `agentsystem-master-control`
- clarified that master control owns candidate evaluation and any necessary first subordinate-skill creation
