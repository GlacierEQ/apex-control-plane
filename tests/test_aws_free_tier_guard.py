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

    def test_plaintext_credentials_in_snapshot_are_rejected_before_report(self):
        data = snapshot()
        data['regions']['us-east-1']['secrets'][0]['SecretString'] = 'NEVER_EMIT_THIS'
        with self.assertRaisesRegex(ValueError, 'Credential material detected'):
            module.assess(data)

    def test_mirror_needs_structured_iam_readback(self):
        data = snapshot(mirror_access_guard=True)
        report = module.assess(data)
        self.assertIn('MIRROR_IAM_UNVERIFIED', self.codes(report))

    def test_matching_iam_simulator_receipt_accepted_as_access_evidence(self):
        data = snapshot(mirror_access_guard={
            'source': 'aws_iam_simulator',
            'principal': 'ec2-github-runner-role',
            'observed_at': '2026-11-02T00:00:00Z',
            'decisions': {
                'ssm:GetParameter': 'explicitDeny',
                'ssm:GetParameters': 'explicitDeny',
                'ssm:GetParameterHistory': 'explicitDeny',
                'ssm:GetParametersByPath': 'explicitDeny',
            },
        })
        report = module.assess(data)
        self.assertNotIn('MIRROR_IAM_UNVERIFIED', self.codes(report))

    def test_output_contains_no_secret_values(self):
        data = snapshot()
        data['regions']['us-east-1']['secrets'][0]['SecretString'] = 'NEVER_EMIT_THIS'
        with self.assertRaises(ValueError) as context:
            module.assess(data)
        self.assertNotIn('NEVER_EMIT_THIS', str(context.exception))


class LiveMetadataCollectorTests(unittest.TestCase):
    class Session:
        def __init__(self, *, fail_secrets=False):
            self.calls = []
            self.fail_secrets = fail_secrets

        def client(self, service, region_name=None):
            outer = self

            class Client:
                def __getattr__(self, operation):
                    def call(**kwargs):
                        outer.calls.append((service, region_name, operation, kwargs))
                        if outer.fail_secrets and service == 'secretsmanager':
                            raise PermissionError('metadata unavailable')
                        if operation == 'describe_regions':
                            return {'Regions': [{'RegionName': 'us-east-1'}, {'RegionName': 'us-west-2'}]}
                        if operation == 'get_account_plan_state':
                            return {'accountPlanType': 'PAID', 'accountPlanRemainingCredits': {'amount': 0}}
                        if operation == 'get_free_tier_usage':
                            return {'freeTierUsages': [{'service': 'Amazon Simple Queue Service', 'freeTierType': 'Always Free', 'actualUsageAmount': 40, 'limit': 1000000}]}
                        if operation == 'list_secrets':
                            return {'SecretList': [{'Name': 'glaciereq/only'}] if region_name == 'us-east-1' else []}
                        if operation == 'describe_parameters':
                            return {'Parameters': [{'Name': '/glaciereq/secure-mirror/only', 'Type': 'SecureString', 'Tier': 'Standard'}] if region_name == 'us-east-1' else []}
                        if operation == 'describe_instances':
                            return {'Reservations': [{'Instances': [{'InstanceId': 'i-a', 'State': {'Name': 'stopped'}}]}]} if region_name == 'us-west-2' else {'Reservations': []}
                        if operation == 'describe_volumes':
                            return {'Volumes': [{'VolumeId': 'vol-a', 'Size': 20, 'State': 'in-use'}]} if region_name == 'us-west-2' else {'Volumes': []}
                        if operation == 'describe_addresses':
                            return {'Addresses': []}
                        if operation == 'get_caller_identity':
                            return {'Account': '123456789012'}
                        if operation == 'simulate_principal_policy':
                            return {'EvaluationResults': [{'EvalActionName': k, 'EvalDecision': 'explicitDeny'} for k in (
                                'ssm:GetParameter','ssm:GetParameters','ssm:GetParameterHistory','ssm:GetParametersByPath')]}
                        raise AssertionError((service, operation, kwargs))
                    return call
            return Client()

    def test_live_collector_only_uses_metadata_apis(self):
        session = self.Session()
        out = module.collect_live_metadata(session)
        self.assertEqual('PAID', out['plan']['type'])
        self.assertEqual(2, len(out['regions']))
        self.assertEqual(1, len(out['regions']['us-east-1']['parameters']))
        self.assertEqual('Standard', out['regions']['us-east-1']['parameters'][0]['tier'])
        self.assertEqual('aws_iam_simulator', out['mirror_access_guard']['source'])
        self.assertTrue(all(x[2] not in {'get_secret_value','get_parameter', 'put_parameter','create_secret', 'update_table','delete_secret'} for x in session.calls))
        self.assertNotIn('ce', {x[0] for x in session.calls})
        self.assertNotIn('secretsmanager-value', str(out))
        report = module.assess(out)
        self.assertNotIn('MIRROR_IAM_UNVERIFIED', {x['code'] for x in report['findings']})

    def test_live_collector_does_not_claim_success_when_provider_denies_metadata(self):
        session = self.Session(fail_secrets=True)
        with self.assertRaises(PermissionError):
            module.collect_live_metadata(session)

    def test_partial_region_request_exposes_missing_coverage(self):
        out = module.collect_live_metadata(self.Session(), requested_regions=['us-east-1'])
        self.assertEqual(['us-east-1'], list(out['regions']))
        self.assertIn('REGIONAL_INVENTORY_INCOMPLETE', {x['code'] for x in module.assess(out)['findings']})


if __name__ == '__main__':
    unittest.main()
