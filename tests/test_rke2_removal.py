"""Offline production inspector and orchestration tests. No VM or host cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('removal', ROOT / 'library/rke2_remove_inspect.py')
removal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(removal)


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.environment_uids = {}
        original_lstat = Path.lstat

        def fixture_lstat(path, *args, **kwargs):
            metadata = original_lstat(path, *args, **kwargs)
            if str(path) in self.environment_uids:
                fields = list(metadata)
                fields[4] = self.environment_uids[str(path)]
                return os.stat_result(fields)
            return metadata

        ownership = patch.object(Path, 'lstat', fixture_lstat)
        ownership.start()
        self.addCleanup(ownership.stop)
        self.services = {}
        self.service_properties = {}
        self.processes = ''
        self.interfaces = []
        self.rules = ''
        self.mounts = [{'target': '/var/lib/longhorn', 'source': '/dev/sdb', 'fstype': 'ext4', 'uuid': 'disk-uuid'}]
        self.write('/etc/fstab', 'UUID=disk-uuid /var/lib/longhorn ext4 defaults 0 2\n')

    def write(self, path, content=''):
        target = self.root / path.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def run_command(self, argv):
        if argv[0] == 'systemctl':
            name = argv[2].removesuffix('.service')
            state = self.services.get(name, ('not-found', 'inactive'))
            return 0, ('LoadState=%s\nActiveState=%s\n' % state) + self.service_properties.get(name, '')
        if argv[0] == '/usr/local/bin/rke2':
            return 0, 'rke2 version v1.36.4+rke2r1 (fixture)'
        if argv[0] == 'ps':
            return 0, self.processes
        if argv[0] == 'findmnt':
            return 0, json.dumps({'filesystems': self.mounts})
        if argv[0] == 'lsblk':
            return 0, json.dumps({'blockdevices': [{'name': 'sdb', 'uuid': 'disk-uuid'}]})
        if argv[0] == 'ip':
            return 0, json.dumps([{'ifname': v} for v in self.interfaces])
        if argv[0] in ('iptables-save', 'ip6tables-save'):
            return 0, self.rules
        self.fail('Unexpected probe: ' + str(argv))

    def inspect(self):
        return removal.inspect(str(self.root), self.run_command)

    def install(self, role='server', scripts=True):
        self.write('/usr/local/bin/rke2', 'fixture')
        self.write('/etc/rancher/rke2/config.yaml', 'cni: cilium\ntoken: fixture-secret\n')
        self.write('/etc/rancher/rke2/.carekube-managed-config', '{"cluster-init": true}')
        self.write('/var/lib/rancher/rke2/' + ('server' if role == 'server' else 'agent') + '/state')
        self.services['rke2-' + role] = ('loaded', 'active')
        # Mirror the three optional EnvironmentFile directives in upstream units.
        env_paths = [f'/etc/default/rke2-{role}', f'/etc/sysconfig/rke2-{role}',
                     f'/usr/local/lib/systemd/system/rke2-{role}.env']
        self.service_properties['rke2-' + role] = (
            'ExecStart={ path=/usr/local/bin/rke2 ; argv[]=/usr/local/bin/rke2 ' + role + ' ; }\n'
            'EnvironmentFiles=' + ' '.join(p + ' (ignore_errors=yes)' for p in env_paths))
        self.write('/usr/local/lib/systemd/system/rke2-' + role + '.service',
                   '[Service]\n' + ''.join('EnvironmentFile=-' + p + '\n' for p in env_paths)
                   + 'ExecStart=/usr/local/bin/rke2 ' + role + '\n')
        if scripts:
            for name in ('uninstall', 'killall'):
                self.write('/usr/local/bin/rke2-' + name + '.sh', '#!/bin/sh\n# rke2 fixture\n')

    def write_environment(self, path, content='RKE2_TOKEN="fixture-secret"\nHTTP_PROXY=http://proxy.invalid:3128\n'):
        result = self.write(path, content)
        self.environment_uids[str(result)] = 0
        return result

    def test_standard_server_and_agent_environment_files(self):
        for role in ('server', 'agent'):
            with self.subTest(role=role):
                self.install(role=role, scripts=False)
                # systemctl lists optional files even if none of them exist.
                self.assertTrue(self.inspect()['safe'])
                files = [f'/etc/default/rke2-{role}', f'/etc/sysconfig/rke2-{role}',
                         f'/usr/local/lib/systemd/system/rke2-{role}.env']
                for filename in files:
                    self.write_environment(filename)
                inspected = self.inspect()
                self.assertTrue(inspected['safe'], inspected['environment_diagnostics'])
                self.assertEqual(inspected['environment_diagnostics'], [])
                self.assertTrue(set(files) <= set(inspected['cleanup_paths']))
                self.assertEqual(len(inspected['cleanup_paths']), len(set(inspected['cleanup_paths'])))
                self.assertNotIn('fixture-secret', str(inspected))

    def test_environment_required_missing_and_present(self):
        self.install(scripts=False)
        filename = '/usr/local/lib/systemd/system/rke2-server.env'
        self.service_properties['rke2-server'] = 'EnvironmentFiles=' + filename + ' (ignore_errors=no)'
        self.assertEqual(self.inspect()['environment_diagnostics'], [
            {'service': 'rke2-server.service', 'path': filename, 'reason': 'missing_required_file'}])
        self.write_environment(filename)
        self.assertTrue(self.inspect()['safe'])

    def test_unexpected_and_malformed_environment_references(self):
        self.install(scripts=False)
        for value, filename, reason in (
            ('/custom/environment (ignore_errors=yes)', '/custom/environment', 'unexpected_path'),
            ('/etc/default/../foreign (ignore_errors=yes)', '/etc/default/../foreign', 'unexpected_path'),
            ('/custom/environment (ignore_errors=unknown)', '/custom/environment', 'malformed_reference'),
            ('/custom/environment', '/custom/environment', 'malformed_reference'),
            ('RKE2_TOKEN=fixture-secret', '<unparsed>', 'malformed_reference'),
        ):
            with self.subTest(value=value):
                self.service_properties['rke2-server'] = 'EnvironmentFiles=' + value
                result = self.inspect()
                self.assertFalse(result['safe'])
                self.assertIn('unsupported_environment_file', result['reasons'])
                self.assertEqual(result['environment_diagnostics'][0]['path'], filename)
                self.assertEqual(result['environment_diagnostics'][0]['reason'], reason)
                self.assertNotIn('fixture-secret', str(result))

    def test_environment_symlinks_and_parent_symlinks(self):
        self.install(scripts=False)
        filename = '/etc/default/rke2-server'
        target = self.write('/outside', 'RKE2_TOKEN=fixture-secret')
        link = self.root / filename.lstrip('/')
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        self.assertEqual(self.inspect()['environment_diagnostics'][0]['reason'], 'symlink_path')
        link.unlink()
        link.parent.rmdir()
        directory = self.root / 'other'
        directory.mkdir()
        link.parent.symlink_to(directory, target_is_directory=True)
        self.assertEqual(self.inspect()['environment_diagnostics'][0]['reason'], 'symlink_path')
        self.assertEqual(target.read_text(), 'RKE2_TOKEN=fixture-secret')

    def test_environment_permissions_types_and_unreadable_contents(self):
        self.install(scripts=False)
        filename = '/usr/local/lib/systemd/system/rke2-server.env'
        env = self.write_environment(filename)
        for mode, reason in ((0o666, 'unsafe_ownership_or_permissions'), (0o000, 'unreadable_file')):
            env.chmod(mode)
            self.assertEqual(self.inspect()['environment_diagnostics'][0]['reason'], reason)
        env.chmod(0o600)
        self.environment_uids[str(env)] = 12345
        self.assertEqual(self.inspect()['environment_diagnostics'][0]['reason'], 'unsafe_ownership_or_permissions')
        self.environment_uids[str(env)] = 0
        original_read = Path.read_text

        def unreadable(path, *args, **kwargs):
            if path == env:
                raise PermissionError('fixture-secret')
            return original_read(path, *args, **kwargs)

        with patch.object(Path, 'read_text', unreadable):
            result = self.inspect()
            self.assertEqual(result['environment_diagnostics'][0]['reason'], 'unreadable_file')
            self.assertNotIn('fixture-secret', str(result))
        env.write_bytes(b'\xff')
        self.assertEqual(self.inspect()['environment_diagnostics'][0]['reason'], 'unreadable_file')
        env.unlink()
        env.mkdir()
        self.assertEqual(self.inspect()['environment_diagnostics'][0]['reason'], 'not_regular_file')

    def test_environment_unsafe_contents_never_leak_values(self):
        self.install(scripts=False)
        filename = '/usr/local/lib/systemd/system/rke2-server.env'
        for content, reason in (
            ('RKE2_DATA_DIR=/var/lib/longhorn\nRKE2_TOKEN=fixture-secret', 'runtime_path_override'),
            ('RKE2_CONFIG_FILE = /custom', 'runtime_path_override'),
            ('"RKE2_KUBELET_ARG=--root-dir=/custom"', 'runtime_path_override'),
            ('LD_PRELOAD=/custom/fixture-secret.so', 'runtime_path_override'),
            ('RKE2_TOKEN="fixture-secret', 'malformed_contents'),
            ('touch /tmp/fixture-secret', 'malformed_contents'),
        ):
            with self.subTest(reason=reason):
                self.write_environment(filename, content)
                result = self.inspect()
                self.assertFalse(result['safe'])
                self.assertEqual(result['environment_diagnostics'][0]['reason'], reason)
                self.assertNotIn('fixture-secret', str(result))

    def test_environment_cleanup_remnants_and_repeat_absence(self):
        filename = '/usr/local/lib/systemd/system/rke2-server.env'
        self.write_environment(filename)
        self.assertFalse(self.inspect()['safe'])  # An env file alone is not ownership evidence.
        self.write('/etc/rancher/rke2/.carekube-managed-config', '{"cluster-init":true}')
        result = self.inspect()
        self.assertTrue(result['safe'])
        self.assertIn(filename, result['remaining'])
        # Apply only the production inspector's allowlist to this temporary fixture root.
        for name in result['cleanup_paths']:
            target = self.root / name.lstrip('/')
            if target.is_dir():
                import shutil
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for _ in range(2):
            after = self.inspect()
            self.assertFalse(after['present'])
            self.assertTrue(after['safe'])

    def test_diagnostic_paths_are_bounded_escaped_and_redacted(self):
        self.assertEqual(removal.diagnostic_path('/custom/\n\x1b[31m'), '/custom/\\n\\u001b[31m')
        self.assertNotIn('fixture-secret', removal.diagnostic_path('/custom?token=fixture-secret'))
        self.assertLessEqual(len(removal.diagnostic_path('/' + 'x' * 1000)), 256)

    def test_already_absent_and_storage_snapshot(self):
        result = self.inspect()
        self.assertTrue(result['safe'])
        self.assertFalse(result['present'])
        self.assertEqual(result['storage']['mounts'], self.mounts)
        self.assertNotIn('/var/lib/longhorn', result['cleanup_paths'])
        self.assertNotIn('fixture-secret', str(result))

    def test_fresh_matching_and_drifted_installs(self):
        self.install(scripts=False)
        for config in ('cni: cilium', 'cni: canal\nserver: https://different-endpoint'):
            self.write('/etc/rancher/rke2/config.yaml', config)
            self.assertTrue(self.inspect()['safe'])
        self.assertNotIn('fixture-secret', str(self.inspect()))

    def test_partial_server_and_agent_binary_only(self):
        self.write('/usr/local/bin/rke2', 'fixture')
        self.assertTrue(self.inspect()['safe'])
        for role in ('server', 'agent'):
            self.services = {'rke2-' + role: ('loaded', 'inactive')}
            result = self.inspect()
            self.assertTrue(result['safe'])
            self.assertEqual(result['role'], role)

    def test_managed_marker_without_binary_or_services(self):
        self.write('/etc/rancher/rke2/.carekube-managed-config', '{"server":"old"}')
        self.assertTrue(self.inspect()['safe'])

    def test_complete_install_scripts_and_network(self):
        self.install()
        self.interfaces = ['cilium_net', 'cilium_vxlan']
        self.rules = '-A FORWARD -j CILIUM_FORWARD'
        self.write('/etc/cni/net.d/05-cilium.conflist', '{"plugins":[{"type":"cilium-cni"}]}')
        original_stat = Path.stat

        def root_script_stat(path, *args, **kwargs):
            stat = original_stat(path, *args, **kwargs)
            if path.name in ('rke2-uninstall.sh', 'rke2-killall.sh'):
                fields = list(stat)
                fields[4] = 0
                return os.stat_result(fields)
            return stat

        with patch.object(Path, 'stat', root_script_stat):
            result = self.inspect()
            self.assertTrue(result['safe'], result['reasons'])
            self.assertEqual(set(result['scripts']), {'uninstall', 'killall'})
            self.assertTrue(result['present'])

    def test_foreign_runtime_and_cni_even_with_rke2(self):
        self.install(scripts=False)
        self.processes = '/usr/bin/containerd --config /etc/containerd/config.toml'
        self.assertIn('foreign_kubernetes', self.inspect()['reasons'])
        self.processes = ''
        self.write('/etc/cni/net.d/third-party.conf', '{"type":"foreign-cni"}')
        self.assertIn('unrecognized_cni', self.inspect()['reasons'])

    def test_pod_volume_bind_mount_is_not_a_data_disk_cleanup_root(self):
        self.install(scripts=False)
        self.mounts.append({'target': '/var/lib/kubelet/pods/uid/volumes/data',
                            'source': '/dev/sdb[/volumes/pvc]', 'fstype': 'ext4'})
        self.assertNotIn('persistent_mount_in_cleanup_path', self.inspect()['reasons'])

    def test_foreign_and_unknown_state(self):
        self.write('/etc/kubernetes/kubelet.conf', 'secret')
        self.assertFalse(self.inspect()['safe'])
        self.assertNotIn('secret', str(self.inspect()))

    def test_unrecognized_rke2_data(self):
        self.write('/var/lib/rancher/rke2/server/state')
        self.assertIn('unrecognized_installation', self.inspect()['reasons'])

    def test_unowned_shared_cni(self):
        self.write('/usr/local/bin/rke2')
        self.write('/etc/cni/net.d/foreign.conf')
        self.assertIn('unowned_shared_state', self.inspect()['reasons'])

    def test_missing_script_with_runtime_or_network(self):
        self.install(scripts=False)
        self.processes = '/var/lib/rancher/rke2/data/hash/bin/containerd-shim-runc-v2 -namespace k8s.io'
        self.assertIn('missing_runtime_cleanup_script', self.inspect()['reasons'])
        self.processes = ''
        self.interfaces = ['cilium_net']
        self.assertIn('missing_runtime_cleanup_script', self.inspect()['reasons'])

    def test_custom_paths_and_symlinks_rejected(self):
        self.install(scripts=False)
        self.write('/etc/rancher/rke2/config.yaml', 'data-dir: /var/lib/longhorn')
        self.assertIn('unsupported_runtime_paths', self.inspect()['reasons'])
        self.write('/etc/rancher/rke2/config.yaml', 'cni: cilium')
        (self.root / 'run').mkdir(exist_ok=True)
        (self.root / 'run/k3s').symlink_to('/var/lib/longhorn')
        self.assertIn('unsafe_cleanup_path', self.inspect()['reasons'])

    def test_quoted_config_and_effective_service_overrides(self):
        self.install(scripts=False)
        for config in ('"data-dir": /custom', '{"data-dir":"/custom"}'):
            self.write('/etc/rancher/rke2/config.yaml', config)
            self.assertIn('unsupported_runtime_paths', self.inspect()['reasons'])
        self.write('/etc/rancher/rke2/config.yaml', 'cni: cilium')
        for props, reason in (
            ('DropInPaths=/etc/systemd/system/rke2-server.service.d/custom.conf', 'unsupported_service_overrides'),
            ('Environment=RKE2_DATA_DIR=/custom', 'unsupported_runtime_paths'),
            ('ExecStart={ path=/usr/bin/foreign ; argv[]=foreign ; }', 'unsupported_service_executable'),
            ('EnvironmentFiles=/custom/environment (ignore_errors=yes)', 'unsupported_environment_file'),
        ):
            self.service_properties['rke2-server'] = props
            self.assertIn(reason, self.inspect()['reasons'])

    def test_persistent_mount_beneath_cleanup_rejected(self):
        self.install(scripts=False)
        self.mounts.append({'target': '/var/lib/rancher/rke2/data', 'source': '/dev/sdb', 'fstype': 'ext4'})
        self.assertIn('persistent_mount_in_cleanup_path', self.inspect()['reasons'])


# These action plugins return fixtures, never dispatch remote modules. The production
# playbook, assertions, includes, conditions, rescue and ordering execute in Ansible.
INSPECT_ACTION = '''
from ansible.plugins.action import ActionBase
class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        v = task_vars
        host = v['inventory_hostname']
        if host == v.get('fixture_unreachable_host', ''):
            return {'unreachable': True, 'msg': 'fixture unreachable'}
        after = self._task.name.startswith('Inspect after')
        phase = 'after' if after else ('current' if self._task.name.startswith('Reinspect') else 'before')
        unsafe = host == v.get('fixture_unsafe_host', '') or phase == v.get('fixture_unsafe_phase', '')
        present = v.get('fixture_present', True) and (not after or v.get('fixture_residual', False))
        storage = {'uuid': 'protected-disk', 'fstab': 'original'}
        if after and v.get('fixture_storage_change', False):
            storage['fstab'] = 'changed'
        role = 'server' if 'control_plane' in v['group_names'] else 'agent'
        return {'changed': False, 'inspection': {
            'safe': not unsafe, 'reasons': ['fixture'],
            'environment_diagnostics': v.get('fixture_environment_diagnostics', []) if unsafe else [],
            'present': present, 'remaining': ['rke2-' + role + '.service'] if present else [],
            'storage': storage, 'cleanup_paths': ['/fixture/rke2'],
            'runtime_active': False, 'cleanup_mounts': ['/fixture/mounted-volume'] if v.get('fixture_mount_residual', False) else [],
            'scripts': v.get('fixture_scripts', {'uninstall': '/fixture/rke2-uninstall.sh'})}}
'''
MUTATE_ACTION = '''
import json
from ansible.plugins.action import ActionBase
class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        args = self._task.args
        with open(task_vars['fixture_events'], 'a') as stream:
            stream.write(json.dumps({'host': task_vars['inventory_hostname'], 'operation': args['operation'], 'arguments': args['arguments']}) + '\\n')
        fail = task_vars.get('fixture_uninstall_failure', False) and args['operation'] == 'ansible.builtin.command'
        return {'changed': True, 'failed': fail, 'msg': 'non-zero return code' if fail else 'fixture', 'stdout': 'fixture-secret' if fail else ''}
'''


class OrchestrationTests(unittest.TestCase):
    def run_case(self, variables=None, limit=None, check=False, roles=None):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            base = Path(directory)
            actions = base / 'actions'
            actions.mkdir()
            (actions / 'rke2_remove_inspect.py').write_text(INSPECT_ACTION)
            (actions / 'rke2_remove_fixture.py').write_text(MUTATE_ACTION)
            destructive = {'ansible.builtin.command', 'ansible.builtin.file', 'ansible.builtin.systemd_service'}

            def transform(tasks):
                for task in tasks:
                    for block in ('block', 'rescue', 'always'):
                        if block in task:
                            transform(task[block])
                    for key in list(task):
                        if key in destructive:
                            value = task.pop(key)
                            task['rke2_remove_fixture'] = {'operation': key, 'arguments': value}
                    if 'ansible.builtin.include_tasks' in task:
                        task['ansible.builtin.include_tasks'] = str(base / Path(task['ansible.builtin.include_tasks']).name)

            for name in ('rke2-remove-node.yml', 'rke2-remove-barrier.yml'):
                data = yaml.safe_load((ROOT / 'tasks' / name).read_text())
                transform(data)
                (base / name).write_text(yaml.safe_dump(data))
            plays = yaml.safe_load((ROOT / 'playbooks/remove-rke2.yml').read_text())
            for play in plays:
                play['vars_files'] = [str(ROOT / 'vars/rke2.yml')]
                transform(play['tasks'])
            playbook = base / 'remove.yml'
            playbook.write_text(yaml.safe_dump(plays))
            inventory = {'all': {'children': roles or {
                'control_plane': {'hosts': {'cp': {}, 'extra': {}}},
                'worker': {'hosts': {'worker': {}}}}}}
            inv = base / 'inventory.yml'
            inv.write_text(yaml.safe_dump(inventory))
            events = base / 'events'
            extra = {'rke2_bootstrap_node': 'cp', 'rke2_remove_confirm': True, 'fixture_events': str(events)}
            extra.update(variables or {})
            if extra.get('rke2_remove_confirm') == 'omit':
                del extra['rke2_remove_confirm']
            command = ['ansible-playbook', '-i', str(inv), str(playbook), '-e', json.dumps(extra)]
            if limit:
                command += ['--limit', limit]
            if check:
                command += ['--check']
            env = dict(os.environ, ANSIBLE_ACTION_PLUGINS=str(actions), ANSIBLE_STDOUT_CALLBACK='default',
                       ANSIBLE_LOCAL_TEMP=str(base / 'local'))
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
            recorded = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
            return result.returncode, result.stdout + result.stderr, recorded

    def test_full_cluster_order(self):
        rc, output, events = self.run_case()
        self.assertEqual(rc, 0, output)
        ordered = list(dict.fromkeys(event['host'] for event in events))
        self.assertEqual(ordered, ['worker', 'extra', 'cp'])
        self.assertEqual(output.count('| REMOVED'), 3)

    def test_partial_install_fallback(self):
        for scripts in ({}, {'killall': '/fixture/rke2-killall.sh'}):
            rc, output, events = self.run_case({'fixture_scripts': scripts})
            self.assertEqual(rc, 0, output)
            commands = [v for v in events if v['operation'] == 'ansible.builtin.command']
            self.assertEqual(len(commands), 3 if scripts else 0)
            for event in commands:
                self.assertEqual(event['arguments']['argv'], ['/fixture/rke2-killall.sh'])

    def test_killall_precedes_uninstaller(self):
        scripts = {'killall': '/fixture/rke2-killall.sh', 'uninstall': '/fixture/rke2-uninstall.sh'}
        rc, output, events = self.run_case({'fixture_scripts': scripts})
        self.assertEqual(rc, 0, output)
        for host in ('worker', 'extra', 'cp'):
            commands = [v['arguments']['argv'][0] for v in events
                        if v['host'] == host and v['operation'] == 'ansible.builtin.command']
            self.assertEqual(commands, ['/fixture/rke2-killall.sh', '/fixture/rke2-uninstall.sh'])

    def test_absent_is_noop(self):
        rc, output, events = self.run_case({'fixture_present': False})
        self.assertEqual(rc, 0, output)
        self.assertEqual(events, [])
        self.assertEqual(output.count('| ABSENT'), 3)

    def test_accepted_confirmation_values(self):
        for value in (True, 'true', 'TRUE', 'True'):
            with self.subTest(value=value):
                rc, output, events = self.run_case({'rke2_remove_confirm': value})
                self.assertEqual(rc, 0, output)
                self.assertTrue(events)
                self.assertEqual(output.count('| REMOVED'), 3)

    def test_rejected_confirmation_values(self):
        for value in ('omit', False, 'false', 'FALSE', None, '', 'yes', '1', 1,
                      0, ' true ', [], {}, ['true'], {'confirm': True}):
            with self.subTest(value=value):
                rc, output, events = self.run_case({'rke2_remove_confirm': value})
                self.assertEqual(rc, 2, output)
                self.assertEqual(events, [])

    def test_partial_scope_and_invalid_bootstrap(self):
        for variables, limit in (({}, 'worker'), ({'rke2_remove_confirm': 'true'}, 'worker'),
                                 ({'rke2_bootstrap_node': 'worker'}, None)):
            rc, output, events = self.run_case(variables, limit=limit)
            self.assertEqual(rc, 2, output)
            self.assertEqual(events, [])

    def test_unsafe_node_blocks_entire_cluster(self):
        rc, output, events = self.run_case({'fixture_unsafe_host': 'cp'})
        self.assertNotEqual(rc, 0, output)
        self.assertEqual(events, [])

    def test_environment_diagnostics_and_failure_barriers(self):
        filename = '/usr/local/lib/systemd/system/rke2-server.env'
        diagnostic = [{'service': 'rke2-server.service', 'path': filename,
                       'reason': 'runtime_path_override'}]
        for phase in ('before', 'current', 'after'):
            with self.subTest(phase=phase):
                rc, output, events = self.run_case({'fixture_unsafe_phase': phase,
                                                  'fixture_environment_diagnostics': diagnostic})
                self.assertEqual(rc, 2, output)
                self.assertIn(filename, output)
                self.assertIn('runtime_path_override', output)
                if phase in ('before', 'current'):
                    self.assertEqual(events, [])
                else:
                    self.assertEqual({e['host'] for e in events}, {'worker'})
                    self.assertIn('INCOMPLETE', output)

    def test_unreachable_preflight_blocks_mutation(self):
        rc, output, events = self.run_case({'fixture_unreachable_host': 'worker'})
        self.assertNotEqual(rc, 0, output)
        self.assertEqual(events, [])
        self.assertIn('unreachable', output)

    def test_overlapping_roles_rejected(self):
        roles = {'control_plane': {'hosts': {'cp': {}}}, 'worker': {'hosts': {'cp': {}}}}
        rc, output, events = self.run_case(roles=roles)
        self.assertEqual(rc, 2, output)
        self.assertEqual(events, [])

    def test_check_mode_no_mutation(self):
        for value in (True, 'true', 'TRUE'):
            with self.subTest(value=value):
                rc, output, events = self.run_case({'rke2_remove_confirm': value}, check=True)
                self.assertEqual(rc, 0, output)
                self.assertEqual(events, [])
                self.assertEqual(output.count('WOULD REMOVE'), 3)
        rc, _, events = self.run_case({'rke2_remove_confirm': False}, check=True)
        self.assertNotEqual(rc, 0)
        self.assertEqual(events, [])

    def test_uninstall_and_verification_failures_stop_later_nodes(self):
        for flag in ('fixture_uninstall_failure', 'fixture_residual', 'fixture_storage_change', 'fixture_mount_residual'):
            rc, output, events = self.run_case({flag: True})
            self.assertNotEqual(rc, 0, output)
            self.assertIn('worker | worker | INCOMPLETE', output)
            self.assertEqual({event['host'] for event in events}, {'worker'})
            self.assertNotIn('fixture-secret', output)
            if flag == 'fixture_mount_residual':
                self.assertFalse(any(e['operation'] == 'ansible.builtin.file' for e in events))

    def test_production_mutation_is_explicitly_check_guarded(self):
        tasks = yaml.safe_load((ROOT / 'tasks/rke2-remove-node.yml').read_text())
        block = next(t for t in tasks if 'block' in t)
        self.assertEqual(block['when'], 'not ansible_check_mode')
        module = (ROOT / 'library/rke2_remove_inspect.py').read_text()
        for forbidden in ('mkfs', 'wipefs', 'parted'):
            self.assertNotIn(forbidden, module)


if __name__ == '__main__':
    unittest.main()
