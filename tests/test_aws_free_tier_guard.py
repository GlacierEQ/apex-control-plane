from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts' / 'aws_free_tier_guard.py'
SPEC = importlib.util.spec_from_file_location('aws_free_tier_guard', SOURCE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def snapshot(**overrides):
    base = {
        'plan': {'type': 'PAID', 'remaining_credits_usd': 0},
        'free_usage': [{'service': 'SQS', 'used': 14975, 'limit': 1000000, 'tier': 'Always Free'}],
        'regions': {
            'us-east-1': {
                'secrets': [{'name': f'glaciereq/item-{n}'} for n in range(32)],
                'parameters': [{'name': f'/glaciereq/secure-mirror/item-{n}', 'type': 'SecureString', 'tier': 'Standard'} for n in range(24)],
                'instances': [], 'volumes': [], 'addresses': [],
            },
            'us-west-2': {
                'secrets': [], 'parameters': [],
                'instances': [{'id': 'i-stopped', 'state': 'stopped', 'has_public_ip': False}],
                'volumes': [{'id': 'vol-a', 'size_gb': 20, 'state': 'in-use'}],
                'addresses': [],
            },
        },
    }
    base.update(overrides)
    return base


class FreeTierGuardTests(unittest.TestCase):
    def codes(self, report):
        return {entry['code'] for entry in report['findings']}

    def test_detects_unmirrored_secrets_without_claiming_cutover(self):
        report = module.assess(snapshot())
        self.assertIn('BILLABLE_SECRET_ORIGINALS', self.codes(report))
        self.assertIn('SECRET_MIRROR_INCOMPLETE', self.codes(report))
        self.assertEqual(8, report['inventory']['unmirrored_secret_count'])
        self.assertEqual(32, report['inventory']['billable_secret_count'])
        self.assertFalse(report['accepted_zero_recurring'])

    def test_complete_mirror_does_not_mean_secret_cost_removed(self):
        data = snapshot()
        data['regions']['us-east-1']['parameters'] = [
            {'name': '/glaciereq/secure-mirror/item-' + str(n), 'type': 'SecureString', 'tier': 'Standard'} for n in range(32)
        ]
        report = module.assess(data)
        self.assertNotIn('SECRET_MIRROR_INCOMPLETE', self.codes(report))
        self.assertIn('BILLABLE_SECRET_ORIGINALS', self.codes(report))
        self.assertFalse(report['accepted_zero_recurring'])

    def test_rejects_plaintext_or_advanced_mirror(self):
        data = snapshot()
        data['regions']['us-east-1']['parameters'][0]['type'] = 'String'
        data['regions']['us-east-1']['parameters'][1]['tier'] = 'Advanced'
        report = module.assess(data)
        self.assertIn('UNSAFE_SECRET_MIRROR', self.codes(report))
        self.assertEqual(10, report['inventory']['unmirrored_secret_count'])

    def test_detects_running_ec2_and_public_ipv4_separately(self):
        data = snapshot()
        data['regions']['us-west-2']['instances'][0]['state'] = 'running'
        data['regions']['us-west-2']['instances'][0]['has_public_ip'] = True
        report = module.assess(data)
        self.assertIn('RUNNING_EC2_REVIEW_BILLING', self.codes(report))
        self.assertIn('PUBLIC_IPV4_REVIEW_BILLING', self.codes(report))

    def test_stopped_ec2_is_not_falsely_marked_free_storage(self):
        report = module.assess(snapshot())
        self.assertNotIn('RUNNING_EC2_REVIEW_BILLING', self.codes(report))
        self.assertIn('EBS_STORAGE_REMAINS', self.codes(report))
        self.assertEqual(20, report['inventory']['ebs_gb'])

    def test_no_budget_cap_or_cost_explorer_required(self):
        report = module.assess(snapshot())
        self.assertEqual('usage_quotas_not_dollar_budget', report['policy'])
        self.assertNotIn('monthly_budget', report['inventory'])

    def test_missing_region_or_invalid_metadata_fails_closed(self):
        report = module.assess({'plan': {'type': 'PAID'}, 'regions': {}})
        self.assertIn('NO_REGION_EVIDENCE', self.codes(report))
        self.assertFalse(report['accepted_zero_recurring'])

    def test_flags_approaching_free_limit_without_imposing_dollar_budget(self):
        data = snapshot(free_usage=[{'service': 'SQS', 'used': 950000, 'limit': 1000000, 'tier': 'Always Free'}])
        report = module.assess(data)
        self.assertIn('ALWAYS_FREE_QUOTA_NEAR_LIMIT', self.codes(report))
        self.assertEqual('usage_quotas_not_dollar_budget', report['policy'])

    def test_no_resource_billed_does_not_imply_provider_truth(self):
        data = snapshot()
        data['regions']['us-east-1']['secrets'] = []
        data['regions']['us-east-1']['parameters'] = []
        data['regions']['us-west-2']['volumes'] = []
        report = module.assess(data)
        self.assertFalse(report['accepted_zero_recurring'])
        self.assertIn('COST_STATUS_NOT_PROVEN_FROM_RESOURCE_METADATA', self.codes(report))

    def test_external_namespace_secrets_count_as_billable_too(self):
        data = snapshot()
        data['regions']['us-east-1']['secrets'].append({'name': 'other-team/forgotten'})
        report = module.assess(data)
        self.assertEqual(33, report['inventory']['billable_secret_count'])
        self.assertIn('OUT_OF_SCOPE_BILLABLE_SECRETS', self.codes(report))

    def test_elastic_ip_not_double_counted_as_instance_ip(self):
        data = snapshot()
        data['regions']['us-west-2']['instances'][0]['has_public_ip'] = True
        data['regions']['us-west-2']['addresses'] = [{'allocation_id': 'eip-123'}]
        report = module.assess(data)
        self.assertEqual(1, report['inventory']['instance_public_ipv4_assignments'])
        self.assertEqual(1, report['inventory']['allocated_elastic_ips'])
        self.assertNotIn('public_ipv4_count', report['inventory'])

    def test_region_coverage_not_assumed_complete(self):
        data = snapshot(expected_regions=['us-east-1', 'us-west-2', 'eu-west-1'])
        report = module.assess(data)
        self.assertIn('REGIONAL_INVENTORY_INCOMPLETE', self.codes(report))
        self.assertEqual(1, report['inventory']['missing_region_count'])

    def test_output_contains_no_secret_values(self):
        data = snapshot()
        data['regions']['us-east-1']['secrets'][0]['SecretString'] = 'NEVER_EMIT_THIS'
        report = module.assess(data)
        self.assertNotIn('NEVER_EMIT_THIS', str(report))


if __name__ == '__main__':
    unittest.main()
