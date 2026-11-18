"""Bound an untrusted graph export to an independently recorded SHA-256 digest.

The digest detects modification between provider export and admission; it does not
authenticate the provider or confer authority on graph content.
"""
from __future__ import annotations
import hashlib
import json
import re


def canonical_bytes(rows):
    if not isinstance(rows, list):
        raise ValueError('graph export must be a JSON array')
    return json.dumps(rows, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def graph_digest(rows):
    return hashlib.sha256(canonical_bytes(rows)).hexdigest()


def verify_graph_digest(rows, expected):
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('expected SHA-256 must be 64 lowercase hex characters')
    import hmac
    actual = graph_digest(rows)
    if not hmac.compare_digest(actual, expected):
        raise ValueError('graph export digest mismatch')
    return actual
