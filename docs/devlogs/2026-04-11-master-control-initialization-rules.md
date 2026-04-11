# 2026-04-11 Master control initialization rules

## Summary
Strengthened the contract so the generated master control skill must carry its own explicit initialization rules.

## Key rule
The meta-skill may create and enter the master control skill, but the master control skill must define and execute initialization in its own role.

## Initialization expectations
On first activation, the master control skill should automatically:
- read anchor and control artifacts
- scan repository structure and key project documents
- reconcile generated control state against repository reality
- identify initial governed scopes
- decide whether first structural subordinate skills should be created
- create the necessary first subordinate skills in its own role
- update control-plane artifacts accordingly
