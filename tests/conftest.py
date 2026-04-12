"""Test configuration — set env vars before app modules are imported."""
import os

# Phase F.4: Skip auth in test environment
os.environ.setdefault("AGENTSYSTEM_SKIP_AUTH", "1")
