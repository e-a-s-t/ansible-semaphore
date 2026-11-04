"""Offline tests of the production classification filter."""
import base64
import importlib.util
import json
import pathlib
import unittest
import yaml
from jinja2 import Environment

spec = importlib.util.spec_from_file_location('rke2_state', pathlib.Path(__file__).resolve().parents[1] / 'filter_plugins/rke2_state.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'cluster-init': True, 'cni': 'cilium', 'disable': ['ingress'], 'tls-san': ['api', 'extra']}
        self.version = 'v1.37.1+rke2r1'

    def classify(self, config=None, marker=None, exists=(True, True, True, True), bootstrap=True, control=True, version=None):
        def content(value):
            return {'content': base64.b64encode(value.encode()).decode()}
        return module.classify_rke2(
            {'results': [{'stat': {'exists': e}} for e in exists]},
            {'stdout': version or self.version, 'rc': 0},
            content(json.dumps(self.expected) if config is None else config),
            content(json.dumps(self.expected) if marker is None else marker),
            self.expected, self.version, bootstrap, control)

    def test_successful_bootstrap_and_rerun(self):
        self.assertEqual(self.classify(exists=(False, False, False, False))['state'], 'new')
        # Same content written by bootstrap configuration/marker tasks.
        self.assertEqual(self.classify()['state'], 'matching')
        self.assertEqual(self.classify()['state'], 'matching')

    def test_production_bootstrap_template_rerun(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        plays = yaml.safe_load((root / 'playbooks/install-rke2.yml').read_text())
        tasks = next(p['tasks'] for p in plays if p['name'] == 'Bootstrap or preserve the explicit bootstrap node')
        content = next(t['ansible.builtin.copy']['content'] for t in tasks
                       if t.get('name') == 'Configure a new embedded-etcd bootstrap server')
        rendered = Environment().from_string(content).render(
            rke2_cni='cilium', rke2_disabled_components=['ingress'],
            rke2_api_endpoint='api', rke2_tls_sans=['extra'], rke2_join_token='')
        self.assertEqual(self.classify(config=rendered)['state'], 'matching')
        self.assertEqual(self.classify(config=rendered)['state'], 'matching')

    def test_marker_format_and_unordered_lists(self):
        marker = dict(self.expected, **{'tls-san': ['extra', 'api']})
        self.assertEqual(self.classify(marker=json.dumps(marker, indent=1))['state'], 'matching')

    def test_actual_drift(self):
        for key, value in [('cluster-init', False), ('cni', 'other'), ('disable', []), ('tls-san', [])]:
            with self.subTest(key=key):
                result = self.classify(config=json.dumps(dict(self.expected, **{key: value})))
                self.assertEqual(result['state'], 'drifted')
                self.assertIn(key, result['differences'])
        self.assertEqual(self.classify(version='v1.36.0+rke2r1')['state'], 'drifted')

    def test_inspection_errors_are_sanitized(self):
        for config in ['token: [secret', 'null', '[]', 'disable: secret', 'tls-san: [123]']:
            result = self.classify(config=config)
            self.assertEqual(result['state'], 'inspection_error')
            self.assertNotIn('secret', str(result))
        self.assertEqual(self.classify(marker='token-secret')['state'], 'inspection_error')

    def test_unreadable_config_fails_without_values(self):
        result = module.classify_rke2(
            {'results': [{'stat': {'exists': True}} for _ in range(4)]},
            {'rc': 0, 'stdout': self.version}, {'failed': True}, {},
            self.expected, self.version, True, True)
        self.assertEqual(result['state'], 'inspection_error')
        self.assertEqual(result['error_category'], 'read_or_parse')

    def test_partial_and_ambiguous_state(self):
        self.assertEqual(self.classify(exists=(True, False, False, False))['state'], 'incomplete_install')
        self.assertEqual(self.classify(exists=(True, False, True, False))['state'], 'unknown')
        self.assertEqual(self.classify(exists=(True, True, True, False))['state'], 'matching')

    def test_worker_config_and_endpoint_drift(self):
        self.expected = {'server': 'https://api:9345', 'cni': 'cilium', 'disable': [], 'tls-san': ['api']}
        self.assertEqual(self.classify(config='server: https://api:9345\ntoken: secret', bootstrap=False, control=False)['state'], 'matching')
        self.assertEqual(self.classify(config='server: https://wrong:9345', bootstrap=False, control=False)['state'], 'drifted')


if __name__ == '__main__':
    unittest.main()
