"""Offline execution of production controller, token and final barrier tasks."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_tasks(name):
    tasks = yaml.safe_load((ROOT / 'tasks' / name).read_text())
    def resolve(items):
        for task in items:
            include = task.get('ansible.builtin.include_tasks')
            if isinstance(include, str):
                task['ansible.builtin.include_tasks'] = str(ROOT / 'tasks' / include)
            for key in ('block', 'rescue', 'always'):
                resolve(task.get(key, []))
    resolve(tasks)
    return tasks


class ControllerTests(unittest.TestCase):
    def run_case(self, failure=None, explicit_localhost=True):
        with tempfile.TemporaryDirectory(prefix='rke2-controller-') as directory:
            base = Path(directory)
            token = 'K10controller-fixture::server:private-fixture-value'
            source = base / 'source-token'
            source.write_text(token + '\n' if failure != 'invalid_token' else '\n')
            source.chmod(0o600)
            backup = base / 'credentials' / 'token'
            if failure == 'backup':
                backup.parent.write_text('not a directory')
            inventory = {'all': {'children': {
                'control_plane': {'hosts': {'cp': {'ansible_connection': 'local', 'ansible_remote_tmp': str(base / 'source-staging'), 'rke2_state': 'matching'}}},
                'worker': {'hosts': {'agent': {'ansible_connection': 'local'}}}}}}
            if explicit_localhost:
                inventory['all']['hosts'] = {'localhost': {
                    'ansible_connection': 'ssh', 'ansible_become': True,
                    'ansible_remote_tmp': '/dev/null/unwritable'}}
            inv = base / 'inventory.yml'
            inv.write_text(yaml.safe_dump(inventory))
            variables = {
                'rke2_controller_remote_tmp': str(base / 'staging'),
                'rke2_token_backup_path': str(backup),
                'rke2_bootstrap_node': 'cp',
            }
            token_tasks = load_tasks('rke2-token.yml')
            token_tasks[0]['when'] = [token_tasks[0]['when'], "inventory_hostname == 'cp'"]
            # Only remote source I/O is substituted; validation, local storage and
            # readiness publication are the production tasks.
            for task in token_tasks[0]['block']:
                if 'ansible.builtin.service_facts' in task:
                    del task['ansible.builtin.service_facts']
                    task.pop('register')
                    task['ansible.builtin.set_fact'] = {'rke2_source_services': {
                        'ansible_facts': {'services': {'rke2-server.service': {'state': 'running'}}}}}
                if 'ansible.builtin.shell' in task:
                    del task['ansible.builtin.shell']
                    task.pop('args')
                    task['become'] = False
                    task['ansible.builtin.command'] = {
                        'argv': ['cat', str(base / 'missing' if failure == 'read' else source)]}
            setup = load_tasks('rke2-controller.yml') + [
                {'ansible.builtin.set_fact': {
                    'rke2_target_hosts': ['cp', 'agent'], 'rke2_selected_source': 'cp',
                    'rke2_bootstrap_complete': failure != 'bootstrap',
                    # Deliberately stale readiness must be invalidated on failure.
                    'rke2_token_ready': True, 'rke2_source_ready': True,
                    'rke2_cluster_token': 'stale'},
                 'delegate_to': 'localhost', 'delegate_facts': True, 'no_log': True},
                {'ansible.builtin.set_fact': {
                    'rke2_preflight_ready': True,
                    'rke2_installation_complete': "{{ item != 'agent' or " + str(failure != 'worker') + " }}"},
                 'delegate_to': '{{ item }}', 'delegate_facts': True,
                 'loop': ['cp', 'agent']},
                {'ansible.builtin.command': 'id -u', 'delegate_to': 'localhost',
                 'become': False, 'register': 'controller_uid', 'changed_when': False},
                {'ansible.builtin.assert': {'that': [
                    "hostvars['localhost'].ansible_connection == 'local'",
                    "not (hostvars['localhost'].ansible_become | bool)",
                    "controller_uid.stdout | int == " + str(os.getuid())]}}]
            final = load_tasks('rke2-verification-barrier.yml') + [
                {'name': 'API and kubeconfig sentinel',
                 'ansible.builtin.file': {'path': str(base / 'verification-executed'), 'state': 'touch'}}]
            join = [{'block': [
                {'ansible.builtin.include_tasks': str(ROOT / 'tasks/rke2-barrier.yml'),
                 'vars': {'rke2_require_token': True}},
                {'ansible.builtin.debug': {'msg': 'JOIN_ALLOWED'}}],
                'rescue': [{'ansible.builtin.debug': {'msg': 'Expansion blocked by readiness barrier'}}]}]
            plays = [
                {'name': 'Acquire credentials from local fixture', 'hosts': 'cp:agent',
                 'gather_facts': False, 'become': True, 'vars': variables,
                 'tasks': [dict(task, run_once=True) for task in setup] + token_tasks},
                {'name': 'Gate expansion on surviving host', 'hosts': 'agent',
                 'gather_facts': False, 'vars': variables, 'tasks': join},
                {'name': 'Verify after previous play failures', 'hosts': 'localhost',
                 'gather_facts': False, 'become': False, 'vars': variables, 'tasks': final}]
            playbook = base / 'case.yml'
            playbook.write_text(yaml.safe_dump(plays, sort_keys=False))
            env = dict(os.environ, ANSIBLE_STDOUT_CALLBACK='default',
                       ANSIBLE_LOCAL_TEMP=str(base / 'local-tmp'),
                       ANSIBLE_REMOTE_TEMP='/dev/null/unwritable')
            run = subprocess.run(['ansible-playbook', '-i', str(inv), str(playbook)],
                                 cwd=ROOT, env=env, text=True, capture_output=True)
            output = run.stdout + run.stderr
            self.assertNotIn(token, output)
            self.assertNotIn('ESTABLISH SSH', output)
            self.assertEqual(run.returncode, 2 if failure else 0, output)
            self.assertEqual((base / 'verification-executed').exists(), not bool(failure), output)
            self.assertEqual((base / 'staging').stat().st_mode & 0o777, 0o700)
            if not failure:
                self.assertEqual(backup.read_text(), token + '\n')
                self.assertEqual(backup.stat().st_uid, os.getuid())
                self.assertEqual(source.read_text(), token + '\n')
                self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
                self.assertEqual(backup.parent.stat().st_mode & 0o777, 0o700)
            self.assertIn('Verify after previous play failures', output)
            if failure in ('read', 'invalid_token', 'backup'):
                self.assertIn('Cluster token readiness failed', output)
                self.assertNotIn('JOIN_ALLOWED', output)

    def test_controller_connection_and_protected_storage(self):
        for explicit in (False, True):
            with self.subTest(explicit_localhost=explicit):
                self.run_case(explicit_localhost=explicit)

    def test_failed_token_acquisition_blocks_final_operations(self):
        for failure in ('read', 'invalid_token', 'backup'):
            with self.subTest(failure=failure):
                self.run_case(failure)

    def test_failed_installation_blocks_final_operations(self):
        for failure in ('bootstrap', 'worker'):
            with self.subTest(failure=failure):
                self.run_case(failure)

    def test_production_wiring(self):
        import configparser
        config = configparser.ConfigParser()
        config.read(ROOT / 'ansible.cfg')
        self.assertTrue(config['defaults']['local_tmp'].startswith('/tmp/'))
        defaults = yaml.safe_load((ROOT / 'vars/rke2.yml').read_text())
        self.assertTrue(defaults['rke2_controller_remote_tmp'].startswith('/tmp/'))
        plays = yaml.safe_load((ROOT / 'playbooks/install-rke2.yml').read_text())
        self.assertEqual(plays[0]['pre_tasks'][0]['ansible.builtin.include_tasks'],
                         '../tasks/rke2-controller.yml')
        final = next(p for p in plays if p['name'] == 'Verify API and extract kubeconfig')
        self.assertEqual(final['tasks'][0]['ansible.builtin.include_tasks'],
                         '../tasks/rke2-verification-barrier.yml')
        for task in final['tasks']:
            if task.get('delegate_to'):
                self.assertTrue(task['become'])
        for name in ('Join additional control-plane nodes', 'Join worker nodes'):
            play = next(p for p in plays if p['name'] == name)
            self.assertTrue(play['tasks'][-1]['ansible.builtin.set_fact']['rke2_installation_complete'])


if __name__ == '__main__':
    unittest.main()
