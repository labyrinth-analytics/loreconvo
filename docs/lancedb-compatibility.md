# LanceDB compatibility

LoreConvo accepts `lancedb>=0.30.2,<=0.34.0`. The closed upper bound excludes
engines that the hybrid index tests have not verified. The application lockfile
keeps LanceDB at 0.30.2. Installed package metadata permits a shared environment
to select 0.34.0.

The Hermes lancedb-suite provider pins 0.34.0 because its BM25 admission threshold
is engine-specific. Do not lower that pin to satisfy LoreConvo. Its retention
and maintenance tests also require index metadata and `create_index(config=...)`
APIs that LanceDB 0.30.2 does not supply.

## Verification

`tests/test_lancedb_integration.py` exercises real temporary LanceDB tables:

- session writes, replacement, reopening, and deletion
- vector search and distance, full-text search, and quoted project filters
- UUID validation and project/surface-scoped vector lookup
- batched index rebuilds and excluded sessions

The default fixture supplies deterministic local vectors without a model
download. The optional fastembed test uses the production BGE-small model
from a predownloaded cache. It exercises inference, writes, and retrieval.
No API key or paid service is required.

Run against each released engine in the supported interval:

```sh
for version in 0.30.2 0.32.0 0.33.0 0.34.0; do
  python -m pip install '.[dev]' "lancedb==$version"
  python -m pip check
  python -m pytest -q tests/test_lancedb_integration.py tests/test_dependency_compatibility.py
done
```

Repeat on Python 3.10 and 3.14. The compatibility workflow uses that matrix.
To include production embedding inference, set `LORECONVO_TEST_EMBEDDING_CACHE`
to an existing fastembed cache before running the tests.

LanceDB 0.34.0 reports deprecation warnings for `create_fts_index`. That API
continues to work within the supported interval.

## Release requirement

Published LoreConvo 0.10.15 requires LanceDB 0.30.2. A source change cannot alter
that wheel's metadata. Release a new LoreConvo version and update the Hermes
integration's package pin before expecting the catalog plugins to install
together. Do not use a dependency override to bypass the published constraint.
