"""Offline execution of production per-target systemd verification and reporting."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = '''
import json
from pathlib import Path
from ansible.plugins.action import ActionBase
class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        v = task_vars
        host = v['inventory_hostname']
        path = Path(v['fixture_events'])
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        count = sum(e['host'] == host for e in events)
        with path.open('a') as stream:
            stream.write(json.dumps({'host': host, 'argv': self._task.args['argv']}) + '\\n')
        states = v.get('fixture_states', {}).get(host, [['loaded', 'active', 'enabled']])
        state = states[min(count, len(states) - 1)]
        lines = [key + '=' + value for key, value in zip(['LoadState', 'ActiveState', 'UnitFileState'], state)]
        return {'changed': False, 'rc': v.get('fixture_rc', 0), 'stdout_lines': lines,
                'stdout': '\\n'.join(lines), 'stderr': 'fixture-secret'}
'''


class ServiceTests(unittest.TestCase):
    def run_case(self, states=None, check=False, rc=0, stale='inactive'):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            base = Path(directory)
            actions = base / 'actions'
            actions.mkdir()
            (actions / 'service_fixture.py').write_text(ACTION)
            tasks = yaml.safe_load((ROOT / 'tasks/rke2-service-verify.yml').read_text())
            for task in tasks:
                self.assertNotIn('delegate_to', task)
                self.assertNotIn('run_once', task)
                self.assertTrue(set(task) & {'ansible.builtin.command', 'ansible.builtin.set_fact', 'ansible.builtin.assert'})
                if 'ansible.builtin.command' in task:
                    argv = task.pop('ansible.builtin.command')['argv']
                    self.assertEqual(argv[:2], ['systemctl', 'show'])
                    task['service_fixture'] = {'argv': argv}
            (base / 'service.yml').write_text(yaml.safe_dump(tasks))
            production = yaml.safe_load((ROOT / 'playbooks/install-rke2.yml').read_text())
            verification = next(p for p in production if p['name'].startswith('Independently verify RKE2 services'))
            self.assertTrue(verification['any_errors_fatal'])
            self.assertLess(production.index(verification), next(i for i, p in enumerate(production) if p['name'] == 'Verify API and extract kubeconfig'))
            for task in verification['tasks']:
                key = 'ansible.builtin.include_tasks'
                original = task[key]
                task[key] = str(base / 'service.yml') if original.endswith('rke2-service-verify.yml') else str(ROOT / 'tasks' / Path(original).name)
            verification['vars_files'] = [str(ROOT / 'vars/rke2.yml')]
            # Exercise the production report expression after a simulated Ready API gate.
            report = production[-1]
            report['vars_files'] = [str(ROOT / 'vars/rke2.yml')]
            plays = [{'hosts': 'localhost', 'gather_facts': False, 'tasks': [
                {'ansible.builtin.set_fact': {'rke2_target_hosts': ['cp', 'worker']}}]}, verification, {'hosts': 'cp', 'gather_facts': False, 'tasks': [
                {'ansible.builtin.debug': {'msg': 'API_READY_KUBECONFIG_GATE'}}]}, report]
            playbook = base / 'play.yml'
            playbook.write_text(yaml.safe_dump(plays))
            shared = {'ansible_connection': 'local', 'rke2_state': 'matching',
                      'rke2_preflight_ready': True, 'rke2_installation_complete': True,
                      'ansible_facts': {'services': {
                          'rke2-server.service': {'state': stale, 'status': 'disabled'},
                          'rke2-agent.service': {'state': 'running', 'status': 'enabled'}}}}
            inventory = {'all': {'vars': shared, 'children': {
                'control_plane': {'hosts': {'cp': {}}}, 'worker': {'hosts': {'worker': {}}}},
                'hosts': {'localhost': {'rke2_target_hosts': ['cp', 'worker'], 'rke2_selected_source': 'cp',
                    'rke2_bootstrap_complete': True, 'rke2_source_ready': True, 'rke2_token_ready': True,
                    'rke2_cluster_token': 'fixture-secret'}}}}
            inv = base / 'inventory.yml'
            inv.write_text(yaml.safe_dump(inventory))
            events = base / 'events'
            variables = {'rke2_bootstrap_node': 'cp', 'rke2_api_wait_retries': 2, 'rke2_api_wait_delay': 0,
                         'fixture_events': str(events), 'fixture_states': states or {}, 'fixture_rc': rc}
            command = ['ansible-playbook', '-i', str(inv), str(playbook), '-e', json.dumps(variables)]
            if check:
                command.append('--check')
            env = dict(os.environ, ANSIBLE_ACTION_PLUGINS=str(actions), ANSIBLE_STDOUT_CALLBACK='default',
                       ANSIBLE_LOCAL_TEMP=str(base / 'local'))
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
            output = run.stdout + run.stderr
            self.assertNotIn('fixture-secret', output)
            self.assertTrue(events.exists(), output)
            recorded = [json.loads(line) for line in events.read_text().splitlines()]
            for event in recorded:
                self.assertEqual(event['argv'][2], 'rke2-server.service' if event['host'] == 'cp' else 'rke2-agent.service')
            return run.returncode, output, recorded

    def test_direct_role_reporting_ignores_stale_facts(self):
        rc, output, events = self.run_case()
        self.assertEqual(rc, 0, output)
        self.assertIn('service=rke2-server.service=active | enabled=enabled', output)
        self.assertIn('service=rke2-agent.service=active | enabled=enabled', output)
        self.assertEqual({e['host'] for e in events}, {'cp', 'worker'})
        self.assertIn('changed=0', output)

    def test_startup_retries_then_succeeds(self):
        rc, output, events = self.run_case({'worker': [['loaded', 'activating', 'enabled'], ['loaded', 'active', 'enabled']]})
        self.assertEqual(rc, 0, output)
        self.assertEqual(sum(e['host'] == 'worker' for e in events), 2)

    def test_bad_services_fail_despite_healthy_cached_facts(self):
        for host, state in [('worker', ['loaded', 'inactive', 'enabled']),
                            ('cp', ['loaded', 'active', 'disabled']),
                            ('worker', ['not-found', 'inactive', '']),
                            ('worker', ['loaded', 'active']),
                            ('worker', ['loaded', 'active', 'enabled-runtime'])]:
            with self.subTest(host=host, state=state):
                rc, output, events = self.run_case({host: [state]}, stale='running')
                self.assertNotEqual(rc, 0, output)
                self.assertIn('RKE2 service verification failed', output)
                self.assertNotIn('API_READY_KUBECONFIG_GATE', output)
                self.assertLessEqual(sum(e['host'] == host for e in events), 3)

    def test_inspection_error_fails_closed(self):
        rc, output, _ = self.run_case(rc=1)
        self.assertNotEqual(rc, 0, output)
        self.assertNotIn('API_READY_KUBECONFIG_GATE', output)

    def test_check_mode_observes_once_without_enforcement(self):
        rc, output, events = self.run_case({'worker': [['not-found', 'inactive', 'disabled']]}, check=True)
        self.assertEqual(rc, 0, output)
        self.assertEqual(len(events), 2)
        self.assertIn('WOULD PRESERVE', output)
        self.assertIn('service=rke2-agent.service=inactive | enabled=disabled', output)
