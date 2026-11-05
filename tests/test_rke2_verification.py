"""Exercise production verification tasks against local fixtures; never contact VMs."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml
from test_rke2_state import module

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v1.37.1+rke2r1'


def response(ready=True, version=VERSION):
    return {'rc': 0, 'stdout': json.dumps({'items': [{'metadata': {'name': name}, 'status': {
        'conditions': [{'type': 'Ready', 'status': 'True' if ready else 'False'}],
        'nodeInfo': {'kubeletVersion': version}}} for name in ['actual-cp', 'actual-worker']]})}


class VerificationTests(unittest.TestCase):
    def test_node_validation(self):
        verify = module.verify_rke2_nodes
        self.assertTrue(verify(response(), ['actual-cp', 'actual-worker'], VERSION)['ok'])
        self.assertEqual(verify(response(), ['inventory-alias'], VERSION)['missing'], ['inventory-alias'])
        self.assertFalse(verify(response(False), ['actual-cp'], VERSION)['ok'])
        self.assertFalse(verify(response(version='v0'), ['actual-worker'], VERSION)['ok'])
        for result in [{'rc': 1, 'stderr': 'secret'}, {'rc': 0, 'stdout': 'secret'}]:
            self.assertNotIn('secret', str(verify(result, ['actual-cp'], VERSION)))

    def test_direct_context_and_kubeconfig_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            tasks = yaml.safe_load((ROOT / 'tasks/rke2-verify.yml').read_text())
            for task in tasks:
                if 'ansible.builtin.command' in task:
                    self.assertNotIn('delegate_to', task)
                    self.assertEqual(task['ansible.builtin.command']['argv'][0], '/var/lib/rancher/rke2/bin/kubectl')
                    del task['ansible.builtin.command']
                    task.pop('register')
                    task.pop('until'); task.pop('retries'); task.pop('delay')
                    task['ansible.builtin.set_fact'] = {'rke2_registered_nodes': response()}
                if 'ansible.builtin.slurp' in task:
                    self.assertNotIn('delegate_to', task)
                    del task['ansible.builtin.slurp']; task.pop('register')
                    task['ansible.builtin.set_fact'] = {'rke2_kubeconfig_source': {'content': base64.b64encode(b'server: https://127.0.0.1:6443\ncredential: fixture-secret\n').decode()}}
            inv = base / 'inventory.yml'
            inv.write_text(yaml.safe_dump({'all': {'children': {
                'control_plane': {'hosts': {'alias-cp': {'ansible_connection': 'local', 'rke2_node_name': 'actual-cp'}}},
                'worker': {'hosts': {'alias-worker': {'rke2_node_name': 'actual-worker'}}}},
                'hosts': {'localhost': {'ansible_connection': 'local'}}}}))
            play = base / 'play.yml'
            play.write_text(yaml.safe_dump([{'hosts': 'alias-cp', 'gather_facts': False, 'vars': {
                'rke2_version': VERSION, 'rke2_api_endpoint': '192.0.2.1', 'rke2_api_port': 6443,
                'rke2_kubeconfig_path': str(base / 'secure/config')}, 'tasks': tasks}]))
            env = dict(os.environ, ANSIBLE_FILTER_PLUGINS=str(ROOT / 'filter_plugins'))
            for iteration in range(2):
                run = subprocess.run(['ansible-playbook', '-i', str(inv), str(play)], cwd=ROOT, env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertNotIn('fixture-secret', run.stdout)
                if iteration:
                    self.assertIn('changed=0', run.stdout)
            config = base / 'secure/config'
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertIn('https://192.0.2.1:6443', config.read_text())

    def test_ingress_drift_and_fresh_configuration(self):
        defaults = yaml.safe_load((ROOT / 'vars/rke2.yml').read_text())
        self.assertEqual(defaults['rke2_ingress_controller'], 'none')
        self.assertEqual(defaults['rke2_cni'], 'cilium')
        self.assertNotIn('rke2-gateway-api-crd', defaults['rke2_disabled_components'])
        expected = {'cluster-init': True, 'cni': 'cilium', 'disable': [], 'tls-san': [], 'ingress-controller': 'none'}
        encode = lambda obj: {'content': base64.b64encode(json.dumps(obj).encode()).decode()}
        legacy = dict(expected); legacy.pop('ingress-controller')
        args = [{'results': [{'stat': {'exists': True}} for _ in range(4)]}, {'rc': 0, 'stdout': VERSION}]
        self.assertEqual(module.classify_rke2(*args, encode(legacy), encode(legacy), expected, VERSION, True, True)['state'], 'drifted')
        self.assertEqual(module.classify_rke2(*args, encode(expected), encode(expected), expected, VERSION, True, True)['state'], 'matching')

    def test_worker_ignores_server_ingress_setting(self):
        expected = {'server': 'https://api:9345', 'cni': 'cilium', 'disable': [], 'tls-san': [], 'ingress-controller': 'none'}
        legacy = dict(expected); legacy.pop('ingress-controller')
        encode = lambda obj: {'content': base64.b64encode(json.dumps(obj).encode()).decode()}
        result = module.classify_rke2(
            {'results': [{'stat': {'exists': True}} for _ in range(4)]},
            {'rc': 0, 'stdout': VERSION}, encode({'server': 'https://api:9345', 'token': 'secret'}),
            encode(legacy), expected, VERSION, False, False)
        self.assertEqual(result['state'], 'matching')
