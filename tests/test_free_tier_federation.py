import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'free_tier_federation.py'
spec = importlib.util.spec_from_file_location('free_tier_federation', SCRIPT)
module = importlib.util.module_from_spec(spec)
if spec.loader:
    spec.loader.exec_module(module)


def obs(provider, **kwargs):
    return {'provider': provider, 'source': 'provider_api', 'checked_at': '2026-11-08T14:00:00Z', **kwargs}


class FreeTierFederationTests(unittest.TestCase):
    def test_neon_free_plan_not_unlimited(self):
        result = module.assess([obs('neon', plan='free', project_count=2, suspend_timeout_seconds=[0, 0])])
        self.assertEqual(2, result['confirmed_free_resources'])
        self.assertIn('NEON_FREE_QUOTA_BOUND', {x['code'] for x in result['findings']})
        self.assertNotIn('NEON_NEVER_SUSPEND', {x['code'] for x in result['findings']})

    def test_neon_zero_is_default_not_never(self):
        result = module.assess([obs('neon', plan='free', project_count=2, suspend_timeout_seconds=[0, -1])])
        self.assertIn('NEON_NEVER_SUSPEND', {x['code'] for x in result['findings']})

    def test_render_shared_hours(self):
        result = module.assess([obs('render', plan='free', resource_count=4, free_service_count=4, shared_instance_hours=750)])
        self.assertEqual(4, result['confirmed_free_resources'])
        self.assertIn('RENDER_SHARED_HOURS', {x['code'] for x in result['findings']})

    def test_unverified_plan_not_counted_free(self):
        for provider in ('supabase', 'railway', 'vercel', 'netlify', 'sprites'):
            with self.subTest(provider=provider):
                result = module.assess([obs(provider, plan='unknown', resource_count=4)])
                self.assertEqual(0, result['confirmed_free_resources'])
                self.assertIn('PLAN_UNVERIFIED', {x['code'] for x in result['findings']})

    def test_railway_failed_deployment_not_usable(self):
        result = module.assess([obs('railway', plan='unknown', resource_count=2, failed_deployments=2)])
        self.assertIn('RAILWAY_DEPLOYMENTS_FAILED', {x['code'] for x in result['findings']})

    def test_vercel_billing_unknown_on_404(self):
        result = module.assess([obs('vercel', plan='unknown', resource_count=56, billing_readback='costs_not_found')])
        self.assertIn('BILLING_UNVERIFIED', {x['code'] for x in result['findings']})
        self.assertEqual('OPEN', result['status'])

    def test_sprites_cold_not_started(self):
        result = module.assess([obs('sprites', plan='unknown', resource_count=11, cold_count=11)])
        self.assertIn('SPRITES_COLD_PRESERVE', {x['code'] for x in result['findings']})
        self.assertEqual(0, result['provider_mutations'])

    def test_no_new_resource_or_spending_from_assessor(self):
        result = module.assess([obs('neon', plan='free', project_count=2)])
        self.assertEqual({'mutations': False, 'spending': False, 'credential_reads': False}, result['safety'])

    def test_rejects_embedded_plaintext(self):
        with self.assertRaisesRegex(ValueError, 'credential'):
            module.assess([obs('railway', plan='unknown', resource_count=1, API_KEY='sensitive')])

    def test_rejects_forged_unattributed_result(self):
        result = module.assess([{'provider': 'neon', 'plan':'free', 'project_count':99}])
        self.assertEqual(0, result['confirmed_free_resources'])
        self.assertIn('EVIDENCE_UNVERIFIED', {x['code'] for x in result['findings']})

    def test_unknown_provider_does_not_default_free(self):
        result = module.assess([obs('mystery', plan='free', resource_count=100)])
        self.assertEqual(0, result['confirmed_free_resources'])
        self.assertIn('UNSUPPORTED_PROVIDER', {x['code'] for x in result['findings']})

    def test_prevent_double_count(self):
        x=obs('neon', plan='free', project_count=2)
        result=module.assess([x,x])
        self.assertEqual(2, result['confirmed_free_resources'])
        self.assertIn('DUPLICATE_PROVIDER_EVIDENCE', {x['code'] for x in result['findings']})

    def test_aws_uses_existing_guard(self):
        calls=[]
        def guard(snapshot):
            calls.append(snapshot)
            return {'status': 'ACTION_REQUIRED', 'findings': [{'code':'BILLABLE_SECRET_ORIGINALS','severity':'ERROR','detail':'32 originals'}]}
        result=module.assess([obs('aws', snapshot={'regions':{}})], aws_assessor=guard)
        self.assertEqual(1,len(calls))
        self.assertIn('AWS_BILLABLE_SECRET_ORIGINALS', {x['code'] for x in result['findings']})

    def test_aws_requires_delegate(self):
        result=module.assess([obs('aws', snapshot={'regions':{}})])
        self.assertIn('AWS_GUARD_UNAVAILABLE', {x['code'] for x in result['findings']})

    def test_rejects_unexpected_fields_that_might_contain_secrets(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            module.assess([obs('railway', plan='unknown', resource_count=1, SERVICE_TOKEN='sensitive')])

    def test_render_free_count_cannot_exceed_total(self):
        with self.assertRaisesRegex(ValueError, 'free_service_count'):
            module.assess([obs('render', plan='free', resource_count=1, free_service_count=50)])

    def test_bad_quantities_rejected(self):
        with self.assertRaises(ValueError):
            module.assess([obs('render', plan='free', resource_count=-3, free_service_count=4)])

if __name__ == '__main__': unittest.main()
