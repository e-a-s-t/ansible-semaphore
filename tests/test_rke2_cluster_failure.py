"""Run real multi-play Ansible host-failure handling with production barriers."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ClusterFailureTests(unittest.TestCase):
    def test_all_hosts_record_readiness(self):
        env = dict(os.environ, ANSIBLE_STDOUT_CALLBACK='default', ANSIBLE_LOCAL_TEMP='/private/tmp/ansible-local')
        run = subprocess.run(['ansible-playbook', '-i', 'tests/rke2_fixture_inventory.yml',
                              'tests/rke2_cluster_failure.yml', '-e', 'failed_host=none'],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('UNSAFE_MUTATION_EXECUTED', run.stdout)

    def test_failed_host_blocks_survivor_in_later_play(self):
        for host in ('cp', 'worker'):
            with self.subTest(host=host):
                env = dict(os.environ, ANSIBLE_STDOUT_CALLBACK='default', ANSIBLE_LOCAL_TEMP='/private/tmp/ansible-local')
                run = subprocess.run(['ansible-playbook', '-i', 'tests/rke2_fixture_inventory.yml',
                                      'tests/rke2_cluster_failure.yml', '-e', 'failed_host=' + host],
                                     cwd=ROOT, env=env, text=True, capture_output=True)
                output = run.stdout + run.stderr
                self.assertEqual(run.returncode, 2, output)
                self.assertIn('Cluster readiness failed', output)
                self.assertNotIn('UNSAFE_MUTATION_EXECUTED', output)


if __name__ == '__main__':
    unittest.main()
