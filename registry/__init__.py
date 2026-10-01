"""Mock CMR registry: a separate relational database mimicking the real one.

This package is a SIBLING of the agent (``harness/``), not a child of it:
nothing in here imports from ``harness/``, and nothing in ``harness/``
reaches past ``harness/tools/connector.py``. When the real NPF registry
replaces the mock, this whole directory is deleted and the connector is
repointed - one cut, visible in the tree.

Layout: ``schema.sql`` (canonical DDL) -> ``models.py`` (SQLAlchemy,
same tables) -> ``database.py`` (engine/session) -> ``repository.py``
(typed queries, no agent concepts) -> ``seed.py`` (deterministic world).
"""
