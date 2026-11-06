"""Execute restart selection guards offline; never call real systemd or SSH."""
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
        with Path(task_vars['fixture_events']).open('a') as stream:
            stream.write(json.dumps({'host': task_vars['inventory_hostname'],
                'args': self._task.args, 'become': self._task.become,
                'check': self._task.check_mode}) + '\\n')
        return {'changed': True, 'failed': task_vars.get('fixture_fail', False)}
'''


class RestartTests(unittest.TestCase):
    def run_case(self, variables=None, limit=None, check=False, overlap=False):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            base = Path(directory)
            actions = base / 'actions'
            actions.mkdir()
            (actions / 'restart_fixture.py').write_text(ACTION)
            plays = yaml.safe_load((ROOT / 'playbooks/restart-rke2-agent.yaml').read_text())
            self.assertFalse(plays[0]['gather_facts'])
            self.assertTrue(plays[0]['any_errors_fatal'])
            restart = plays[0]['tasks'][-1]
            restart['restart_fixture'] = restart.pop('ansible.builtin.systemd_service')
            play = base / 'play.yml'
            play.write_text(yaml.safe_dump(plays))
            inventory = {'all': {'vars': {'ansible_connection': 'local'}, 'children': {
                'worker': {'hosts': {'worker1': {}, 'worker2': {}}},
                'control_plane': {'hosts': {'cp': {}, **({'worker1': {}} if overlap else {})}},
                'backup': {'hosts': {'backup1': {}}}}}}
            inv = base / 'inventory.yml'
            inv.write_text(yaml.safe_dump(inventory))
            events = base / 'events'
            extra = dict(variables or {}, fixture_events=str(events))
            command = ['ansible-playbook', '-i', str(inv), str(play), '-e', json.dumps(extra)]
            if limit:
                command += ['--limit', limit]
            if check:
                command += ['--check']
            env = dict(os.environ, ANSIBLE_ACTION_PLUGINS=str(actions),
                       ANSIBLE_STDOUT_CALLBACK='default', ANSIBLE_LOCAL_TEMP=str(base / 'local'))
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            recorded = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
            return run.returncode, run.stdout + run.stderr, recorded

    def test_exact_worker_only(self):
        for limit in (None, 'worker1', 'worker'):
            with self.subTest(limit=limit):
                rc, output, events = self.run_case({'target_host': 'worker1'}, limit=limit)
                self.assertEqual(rc, 0, output)
                self.assertEqual(events, [{'host': 'worker1', 'args': {
                    'name': 'rke2-agent', 'state': 'restarted'}, 'become': True, 'check': False}])

    def test_invalid_selection_never_restarts(self):
        cases = [{}, *({'target_host': value} for value in
                 ['', None, True, 123, ['worker1'], {}, 'missing', 'worker', 'all',
                  'worker*', 'worker1,worker2', 'cp', 'backup1'])]
        for variables in cases:
            with self.subTest(variables=variables):
                rc, output, events = self.run_case(variables)
                self.assertNotEqual(rc, 0, output)
                self.assertEqual(events, [])
                self.assertIn('target_host must name exactly one inventory worker', output)

    def test_limit_excluding_target_never_restarts(self):
        rc, output, events = self.run_case({'target_host': 'worker1'}, limit='cp')
        self.assertNotEqual(rc, 0, output)
        self.assertEqual(events, [])

    def test_overlapping_control_plane_never_restarts(self):
        rc, output, events = self.run_case({'target_host': 'worker1'}, overlap=True)
        self.assertNotEqual(rc, 0, output)
        self.assertEqual(events, [])

    def test_systemd_failure_propagates(self):
        rc, output, events = self.run_case({'target_host': 'worker1', 'fixture_fail': True})
        self.assertNotEqual(rc, 0, output)
        self.assertEqual(len(events), 1)

    def test_check_mode_is_forwarded(self):
        rc, output, events = self.run_case({'target_host': 'worker1'}, check=True)
        self.assertEqual(rc, 0, output)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['check'])
        # The fixture only proves forwarding; the real systemd module owns dry-run behavior.
