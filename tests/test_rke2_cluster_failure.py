"""Exercise production target capture and barriers across real Ansible plays."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ClusterFailureTests(unittest.TestCase):
    def run_case(self, failed_host='none', explicit_controller=True, limit=None,
                 alternate=False, expected_targets=None):
        with tempfile.TemporaryDirectory(prefix='rke2-targets-') as directory:
            inventory = yaml.safe_load((ROOT / 'tests/rke2_fixture_inventory.yml').read_text())
            inventory['all']['hosts'] = {'controller': {'ansible_connection': 'local'}}
            if explicit_controller:
                inventory['all']['hosts']['localhost'] = {'ansible_connection': 'local'}
            if alternate:
                inventory['all']['children']['control_plane']['hosts']['alternate'] = {
                    'ansible_connection': 'local', 'rke2_state': 'matching'}
            inv = Path(directory) / 'inventory.yml'
            inv.write_text(yaml.safe_dump(inventory))
            variables = {'failed_host': failed_host, 'fixture_tmp': directory,
                         'expected_targets': expected_targets or ['cp', 'worker']}
            if alternate:
                variables['rke2_token_source_node'] = 'alternate'
            command = ['ansible-playbook', '-i', str(inv), 'tests/rke2_cluster_failure.yml',
                       '-e', json.dumps(variables)]
            if limit:
                command += ['--limit', limit]
            env = dict(os.environ, ANSIBLE_STDOUT_CALLBACK='default',
                       ANSIBLE_LOCAL_TEMP=str(Path(directory) / 'local'))
            return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)

    def test_all_hosts_record_readiness(self):
        for explicit in (True, False):
            with self.subTest(explicit_controller=explicit):
                run = self.run_case(explicit_controller=explicit)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertIn('UNSAFE_MUTATION_EXECUTED', run.stdout)
                self.assertNotIn('ok: [late-worker]', run.stdout)

    def test_failed_host_blocks_survivor_in_later_play(self):
        for host in ('cp', 'worker'):
            with self.subTest(host=host):
                run = self.run_case(failed_host=host)
                output = run.stdout + run.stderr
                self.assertEqual(run.returncode, 2, output)
                self.assertIn('Cluster readiness failed', output)
                self.assertNotIn('UNSAFE_MUTATION_EXECUTED', output)

    def test_explicit_limit_with_controller(self):
        run = self.run_case(limit='cp,worker,localhost,controller')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('UNSAFE_MUTATION_EXECUTED', run.stdout)

    def test_limit_excluding_required_source_is_rejected(self):
        run = self.run_case(limit='worker,localhost,controller', expected_targets=['worker'])
        output = run.stdout + run.stderr
        self.assertEqual(run.returncode, 2, output)
        self.assertIn('selected control-plane token source must be included', output)
        self.assertNotIn('UNSAFE_MUTATION_EXECUTED', output)

    def test_alternate_source_limit_excludes_bootstrap(self):
        run = self.run_case(limit='alternate,worker,localhost', alternate=True,
                            expected_targets=['alternate', 'worker'])
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('UNSAFE_MUTATION_EXECUTED', run.stdout)

    def test_production_uses_frozen_targets_for_node_plays(self):
        production = yaml.safe_load((ROOT / 'playbooks/install-rke2.yml').read_text())
        fixture = yaml.safe_load((ROOT / 'tests/rke2_cluster_failure.yml').read_text())
        self.assertEqual(production[0]['hosts'], fixture[0]['hosts'])
        self.assertEqual(production[0]['pre_tasks'][0]['ansible.builtin.include_tasks'],
                         '../tasks/rke2-initialize.yml')
        for play in production[1:]:
            if play['hosts'] != 'localhost':
                self.assertIn("hostvars['localhost'].rke2_target_hosts", play['hosts'])


if __name__ == '__main__':
    unittest.main()
