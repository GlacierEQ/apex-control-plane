#!/usr/bin/env python3
"""Compose provider-native, metadata-only Free Tier evidence with the APEX AWS guard.

No network operations, credentials, mutations, resource creation, or spend.
Provider plans must be proven by native source metadata before capacity is counted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

KNOWN = frozenset({'aws', 'neon', 'render', 'railway', 'supabase', 'vercel', 'netlify', 'sprites'})
FORBIDDEN_KEYS = frozenset({'api_key', 'apikey', 'token', 'secret_value', 'secretstring', 'secretbinary', 'password', 'private_key', 'authorization', 'credentials', 'plaintext'})


def _scan_sensitive(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold().replace('-', '_') in FORBIDDEN_KEYS or _scan_sensitive(nested):
                return True
    elif isinstance(value, list):
        return any(_scan_sensitive(entry) for entry in value)
    return False


def assess(records: list[dict[str, Any]], aws_assessor: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    if not isinstance(records, list) or _scan_sensitive(records):
        raise ValueError('Invalid or credential-bearing evidence')
    findings: list[dict[str, str]] = []
    covered: list[str] = []
    confirmed = 0
    seen: set[str] = set()

    def emit(provider: str, code: str, severity: str, reason: str) -> None:
        findings.append({'provider': provider, 'code': code, 'severity': severity, 'reason': reason})

    for record in records:
        if not isinstance(record, dict):
            emit('unknown', 'INVALID_EVIDENCE', 'ERROR', 'Provider entry must be a record')
            continue
        provider = record.get('provider')
        if not isinstance(provider, str) or provider not in KNOWN:
            emit(str(provider), 'UNSUPPORTED_PROVIDER', 'ERROR', 'No matching integration; capacity cannot be assumed free')
            continue
        if provider in seen:
            emit(provider, 'DUPLICATE_PROVIDER_EVIDENCE', 'ERROR', 'Duplicate provider snapshots cannot inflate counts')
            continue
        seen.add(provider)
        if record.get('source') != 'provider_api' or not isinstance(record.get('checked_at'), str) or not record['checked_at'].endswith('Z'):
            emit(provider, 'EVIDENCE_UNVERIFIED', 'ERROR', 'Native source and UTC observation timestamp required')
            continue
        quantities = ('resource_count', 'project_count', 'free_service_count', 'cold_count', 'failed_deployments', 'shared_instance_hours')
        if any(k in record and (type(record[k]) not in (int, float) or record[k] < 0) for k in quantities):
            raise ValueError('Negative, boolean, or malformed resource quantity')
        covered.append(provider)
        if provider == 'aws':
            if not isinstance(record.get('snapshot'), dict) or aws_assessor is None:
                emit(provider, 'AWS_GUARD_UNAVAILABLE', 'ERROR', 'Invoke the existing AWS guard on an actual snapshot')
                continue
            report = aws_assessor(record['snapshot'])
            for item in report.get('findings', []):
                emit(provider, 'AWS_' + str(item.get('code')), str(item.get('severity', 'WARN')), str(item.get('detail', 'AWS guard finding')))
            continue
        plan = record.get('plan', 'unknown')
        if plan != 'free':
            emit(provider, 'PLAN_UNVERIFIED', 'WARN', 'No native proof of a usable free entitlement; do not schedule new workloads')
        if provider == 'neon':
            if plan == 'free':
                confirmed += record.get('project_count', 0)
                emit(provider, 'NEON_FREE_QUOTA_BOUND', 'INFO', 'Projects have per-project CU-hour and storage/transfer limits')
            if -1 in record.get('suspend_timeout_seconds', []):
                emit(provider, 'NEON_NEVER_SUSPEND', 'WARN', 'A compute has auto-suspend disabled; can consume compute quota')
        elif provider == 'render':
            free_services = record.get('free_service_count', 0)
            confirmed += free_services
            if free_services:
                emit(provider, 'RENDER_SHARED_HOURS', 'WARN', 'Free web services share workspace free instance-hours, bandwidth, and build minutes')
            if record.get('resource_count', 0) > free_services:
                emit(provider, 'RENDER_NONFREE_SERVICES', 'WARN', 'At least one service has no verified free instance plan')
        elif provider == 'railway':
            if record.get('failed_deployments', 0):
                emit(provider, 'RAILWAY_DEPLOYMENTS_FAILED', 'WARN', 'Existing services cannot be treated as usable capacity until repaired')
            if plan == 'free':
                emit(provider, 'RAILWAY_CREDITS_LIMIT', 'WARN', 'Free tier is usage-credit-limited; verify account entitlement')
        elif provider == 'vercel':
            if record.get('billing_readback') != 'verified_free':
                emit(provider, 'BILLING_UNVERIFIED', 'WARN', 'Billing API did not prove zero-cost plan or current spend')
            if plan == 'free':
                confirmed += record.get('resource_count', 0)
                emit(provider, 'VERCEL_HOBBY_LIMITS', 'INFO', 'Hobby limits and usage policy still constrain deployments')
        elif provider == 'sprites':
            if record.get('cold_count', 0):
                emit(provider, 'SPRITES_COLD_PRESERVE', 'INFO', 'Do not wake cold machines without verified no-cost capacity')
        elif provider == 'supabase':
            if plan == 'free':
                confirmed += record.get('project_count', 0)
                emit(provider, 'SUPABASE_PROJECT_QUOTA', 'INFO', 'Project and database resource allowances apply')
        elif provider == 'netlify':
            if plan == 'free':
                confirmed += record.get('resource_count', 0)
                emit(provider, 'NETLIFY_USAGE_LIMITS', 'INFO', 'Site plan does not prove free builds, forms, and bandwidth above allowance')

    return {'schema': 'glaciereq.free-tier-federation.v1', 'status': 'OPEN', 'providers_verified': covered,
            'confirmed_free_resources': confirmed, 'provider_mutations': 0,
            'findings': findings,
            'safety': {'mutations': False, 'spending': False, 'credential_reads': False},
            'zero_cost_verified': False}


def main() -> int:
    parser = argparse.ArgumentParser(description='Assess provider-native, metadata-only account snapshots')
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding='utf-8'))
    print(json.dumps(assess(records), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
