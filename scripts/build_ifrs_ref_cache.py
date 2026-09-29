#!/usr/bin/env python3
"""
Turn a local IFRS Accounting Taxonomy zip into data/reference/ifrs_ref_cache.json
(concept -> IAS/IFRS paragraph identifiers). Commit the JSON, not the zip: the cache
holds only identifiers, and the build then verifies IFRS citations with no zip and
no network.

    python3 scripts/build_ifrs_ref_cache.py path/to/IFRSAT-2024.zip
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from citation_resolver import IFRS_REF_CACHE, build_ifrs_ref_cache  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
n = build_ifrs_ref_cache(sys.argv[1])
print(f"{n} concepts indexed -> {IFRS_REF_CACHE}")
