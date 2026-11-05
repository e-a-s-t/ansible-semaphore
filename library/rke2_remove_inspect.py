#!/usr/bin/python
"""Read-only, deliberately fixed-path inspection for the Carekube RKE2 remover.

No configuration values, command output, or credentials leave this module.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess

ROOTS = ('/usr/local', '/usr', '/opt/rke2')
BINS = tuple(root + '/bin/' + name for root in ROOTS
             for name in ('rke2', 'rke2-uninstall.sh', 'rke2-killall.sh'))
UNITS = tuple(root + '/' + unit + suffix
              for root in ('/etc/systemd/system', '/usr/local/lib/systemd/system', '/usr/lib/systemd/system', '/lib/systemd/system')
              for unit in ('rke2-server', 'rke2-agent')
              for suffix in ('.service', '.env', '.service.d'))
OWNED = ('/etc/rancher/rke2', '/var/lib/rancher/rke2', '/run/rke2', '/run/k3s',
         '/etc/rancher/node', '/var/lib/kubelet', '/var/lib/cni', '/etc/cni',
         '/opt/cni/bin', '/var/log/pods', '/var/log/containers', '/var/log/calico',
         '/run/flannel', '/run/cilium', '/var/lib/cilium')
SHARED = OWNED[4:]
UNITS += tuple('/etc/systemd/system/multi-user.target.wants/rke2-' + role + '.service' for role in ('server', 'agent'))
# The upstream tarball units reference all three locations, optionally. Keep
# reference validation, content checks and cleanup on this same explicit list.
ENVS = tuple(root + '/rke2-' + role + suffix
             for root, suffix in (('/etc/default', ''), ('/etc/sysconfig', ''),
                                  ('/usr/local/lib/systemd/system', '.env'))
             for role in ('server', 'agent'))
RUNTIME_OVERRIDE = re.compile(
    r'--(data-dir|root-dir|container-runtime-endpoint|config)([= \t]|$)|'
    r'RKE2_(DATA_DIR|CONFIG_FILE|KUBELET_ARG)\s*=')
ARTIFACTS = tuple(dict.fromkeys(BINS + UNITS + ENVS + OWNED + tuple(root + '/share/rke2' for root in ROOTS)))
FOREIGN = ('/etc/kubernetes', '/var/lib/etcd', '/var/lib/rancher/k3s',
           '/etc/rancher/k3s', '/var/snap/microk8s', '/var/lib/k0s')


def probe(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    return result.returncode, result.stdout


def diagnostic_path(value):
    """Escape controls, bound output and discard URL-like credential suffixes."""
    value = re.split(r'[?#]', value, maxsplit=1)[0]
    return json.dumps(value[:256], ensure_ascii=True)[1:-1][:256]


def environment_references(value):
    """Parse systemctl show's path (ignore_errors=yes/no) records, fail closed.

    No shell expansion or path normalization: only exact allowlisted paths can
    pass validation, including when systemd escapes a nonstandard path.
    """
    records = []
    remaining = value.strip()
    while remaining:
        match = re.match(r'(/[^\s()]+)\s+\(ignore_errors=(yes|no)\)(?:\s+|$)', remaining)
        if not match:
            candidate = re.match(r'/[^\s()]+', remaining)
            return records, candidate.group() if candidate else '<unparsed>'
        records.append((match.group(1), match.group(2) == 'yes'))
        remaining = remaining[match.end():]
    return records, None


def environment_content_reason(content):
    """Inspect assignments as data; never source files or return their values."""
    if RUNTIME_OVERRIDE.search(content):
        return 'runtime_path_override'
    try:
        lexer = shlex.shlex(content, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = '#;'
        for assignment in lexer:
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', assignment):
                return 'malformed_contents'
            key = assignment.split('=', 1)[0]
            if key in ('RKE2_DATA_DIR', 'RKE2_CONFIG_FILE', 'RKE2_KUBELET_ARG',
                       'RKE2_CONTAINER_RUNTIME_ENDPOINT', 'LD_PRELOAD', 'LD_LIBRARY_PATH'):
                return 'runtime_path_override'
    except ValueError:
        return 'malformed_contents'
    return None


def classify_mounts(mounts, owned_runtime, owned_cilium=False):
    """Classify mounts without exempting any mounted deletion path from guards.

    Pod volume bind mounts remain runtime blockers even when backed by the same
    filesystem as protected storage. Only the Longhorn target tree is protected.
    No sources or options are included in displayable diagnostics.
    """
    result = {key: [] for key in ('cleanup_mounts', 'runtime_mounts',
                                 'blocking_storage_mounts', 'protected_mounts', 'mount_diagnostics')}
    for mount in mounts:
        target, fstype = mount['target'], mount['fstype']
        protected = target == '/var/lib/longhorn' or target.startswith('/var/lib/longhorn/')
        namespace = bool(re.fullmatch(r'/run/netns/cni-[^/]+', target))
        in_cleanup = any(target == p or target.startswith(p + '/') for p in ARTIFACTS)
        in_cleanup = in_cleanup or target.startswith('/run/netns/cni-') or target.startswith('/sys/fs/bpf/tc/globals/cilium')
        if not protected and not in_cleanup:
            continue
        pod = target.startswith('/var/lib/kubelet/pods/')
        runtime_tree = any(target == p or target.startswith(p + '/') for p in (
            '/run/k3s', '/run/rke2', '/var/lib/rancher/rke2/agent/containerd'))
        # cgroup2 is never accepted through the generic pod/runtime rules.
        # The exact Cilium target needs independent, trusted CNI evidence.
        cilium_cgroup = owned_cilium and target == '/run/cilium/cgroupv2' and fstype == 'cgroup2'
        runtime = owned_runtime and (cilium_cgroup or (fstype != 'cgroup2' and (
            pod or (namespace and fstype == 'nsfs') or
            (runtime_tree and fstype in ('tmpfs', 'overlay', 'nsfs')))))
        category = ('protected_longhorn' if protected else 'runtime' if runtime else
                    'persistent_storage' if fstype in ('ext4', 'xfs', 'btrfs', 'nfs', 'nfs4', 'ceph')
                    else 'unknown_mount')
        diagnostic = {'target': diagnostic_path(target), 'fstype': diagnostic_path(fstype),
                      'classification': category}
        result['mount_diagnostics'].append(diagnostic)
        if protected:
            result['protected_mounts'].append(diagnostic)
        else:
            result['cleanup_mounts'].append(target)
            result['runtime_mounts' if runtime else 'blocking_storage_mounts'].append(diagnostic)
    return result


def inspect(root='/', runner=probe):
    def path(p):
        return Path(root) / p.lstrip('/')

    def exists(p):
        return os.path.lexists(path(p))

    def nonempty(p):
        return exists(p) and (not path(p).is_dir() or any(path(p).iterdir()))

    def unsafe(p):
        target = path(p)
        return any(v.is_symlink() for v in [target] + list(target.parents))

    def command(*args):
        return runner(list(args))

    # Fail closed: missing diagnostics and unexpected formats raise to main().
    services = {}
    for name in ('rke2-server', 'rke2-agent', 'kubelet', 'k3s', 'k3s-agent', 'containerd', 'k0scontroller', 'k0sworker'):
        rc, value = command('systemctl', 'show', name + '.service',
                            '--property=LoadState,ActiveState,ExecStart,DropInPaths,Environment,EnvironmentFiles', '--no-pager')
        props = dict(line.split('=', 1) for line in value.splitlines() if '=' in line)
        if not {'LoadState', 'ActiveState'} <= props.keys():
            raise ValueError('service inspection unavailable')
        services[name] = props
    present = [p for p in ARTIFACTS if (nonempty(p) if p in SHARED else exists(p))]
    foreign = any(nonempty(p) for p in FOREIGN) or any(
        services[n]['LoadState'] != 'not-found'
        for n in services if not n.startswith('rke2-') and n != 'containerd')
    foreign = foreign or services['containerd']['ActiveState'] == 'active'
    rc, processes = command('ps', '-eo', 'args=')
    if rc:
        raise ValueError('process inspection unavailable')
    # Exclude only this inspector's own interpreter invocation, never arbitrary workloads.
    runtime = any(re.search(r'(^|/)(rke2|cilium-agent|cilium-envoy|containerd-shim[^ /]*)( |$)', line)
                  for line in processes.splitlines())
    runtime = runtime or any('/var/lib/rancher/rke2/' in line for line in processes.splitlines())
    foreign = foreign or any(re.search(r'(^|/)(k3s|k0s|microk8s)( |$)', line)
                            for line in processes.splitlines())
    for line in processes.splitlines():
        if re.search(r'(^|/)(kubelet|containerd)( |$)', line) and '/var/lib/rancher/rke2/' not in line:
            foreign = True
    rc, mount_text = command('findmnt', '--json', '--list', '--output', 'TARGET,SOURCE,FSTYPE,UUID')
    if rc:
        raise ValueError('mount inspection unavailable')
    mounts = json.loads(mount_text)['filesystems']
    protected = sorted((m for m in mounts if m['target'] == '/var/lib/longhorn'
                        or m['target'].startswith('/var/lib/longhorn/')), key=lambda m: m['target'])
    # Capture filesystem signatures and topology, excluding changing usage counters.
    rc, disks = command('lsblk', '--json', '--output', 'NAME,PATH,TYPE,SIZE,FSTYPE,UUID,PKNAME')
    if rc:
        raise ValueError('disk inspection unavailable')
    storage = {'mounts': protected, 'disks': json.loads(disks),
               'fstab': hashlib.sha256(path('/etc/fstab').read_bytes()).hexdigest()}
    reasons = []
    environment_diagnostics = []

    def reject_environment(service, env_path, reason):
        reasons.append('unsupported_environment_file')
        if reason == 'runtime_path_override':
            reasons.append('unsupported_runtime_paths')
        environment_diagnostics.append({'service': service + '.service',
                                        'path': diagnostic_path(env_path), 'reason': reason})

    references = {}
    if foreign:
        reasons.append('foreign_kubernetes')
    for name in ('rke2-server', 'rke2-agent'):
        props = services[name]
        if props.get('DropInPaths', ''):
            reasons.append('unsupported_service_overrides')
        effective = props.get('ExecStart', '') + ' ' + props.get('Environment', '')
        if RUNTIME_OVERRIDE.search(effective):
            reasons.append('unsupported_runtime_paths')
        executable = re.search(r'path=([^ ;]+)', props.get('ExecStart', ''))
        if executable and executable.group(1) != '/usr/local/bin/rke2':
            reasons.append('unsupported_service_executable')
        records, malformed = environment_references(props.get('EnvironmentFiles', ''))
        if malformed is not None:
            reject_environment(name, malformed, 'malformed_reference')
        for env_path, optional in records:
            if env_path not in ENVS:
                reject_environment(name, env_path, 'unexpected_path')
                continue
            references.setdefault(env_path, []).append((name, optional))

    # Inspect supported files even if a partial installation has no loaded unit.
    # Missing optional references remain valid and are not cleanup artifacts.
    for env_path in ENVS:
        consumers = references.get(env_path, [(Path(env_path).name.split('.')[0], True)])
        reason = None
        if unsafe(env_path):
            reason = 'symlink_path'
        elif not exists(env_path):
            if any(not optional for _, optional in consumers):
                reason = 'missing_required_file'
        else:
            try:
                metadata = path(env_path).lstat()
                if not stat.S_ISREG(metadata.st_mode):
                    reason = 'not_regular_file'
                elif metadata.st_uid != 0 or metadata.st_mode & 0o022:
                    reason = 'unsafe_ownership_or_permissions'
                elif not metadata.st_mode & 0o444:
                    reason = 'unreadable_file'
                else:
                    reason = environment_content_reason(path(env_path).read_text())
            except (OSError, UnicodeError):
                reason = 'unreadable_file'
        if reason:
            for service, _ in consumers:
                reject_environment(service, env_path, reason)
    if any(unsafe(p) for p in OWNED + BINS):
        reasons.append('unsafe_cleanup_path')
    server = services['rke2-server']['LoadState'] != 'not-found'
    agent = services['rke2-agent']['LoadState'] != 'not-found'
    binary = exists('/usr/local/bin/rke2')
    recognized = False
    if binary and not unsafe('/usr/local/bin/rke2'):
        rc, version = command('/usr/local/bin/rke2', '--version')
        recognized = rc == 0 and bool(re.search(r'rke2 version v\S+\+rke2r\d+', version))
    marker = path('/etc/rancher/rke2/.carekube-managed-config')
    managed = False
    if marker.is_file():
        try:
            value = json.loads(marker.read_text())
            managed = isinstance(value, dict) and ('server' in value or 'cluster-init' in value)
        except (ValueError, UnicodeError):
            pass
    data = exists('/var/lib/rancher/rke2/agent') or exists('/var/lib/rancher/rke2/server')
    evidence = recognized or managed or (data and (server or agent))
    shared = any(nonempty(p) for p in SHARED)
    exclusive = evidence and data
    if shared and not exclusive:
        reasons.append('unowned_shared_state')
    # v1 intentionally supports only the repository's default tarball layout.
    if any(exists(p) for p in BINS if not p.startswith('/usr/local/')):
        reasons.append('unsupported_install_layout')
    if exists('/etc/rancher/rke2/config.yaml'):
        config = path('/etc/rancher/rke2/config.yaml').read_text()
        if re.search(r"(?m)(?:^|[,{])\s*['\"]?(data-dir|kubelet-arg|container-runtime-endpoint)['\"]?\s*:|^\s*[?%!]", config):
            reasons.append('unsupported_runtime_paths')
    if nonempty('/etc/rancher/rke2/config.yaml.d'):
        reasons.append('unsupported_config_fragments')
    for unit in UNITS:
        if unit not in ENVS and exists(unit) and path(unit).is_file():
            content = path(unit).read_text()
            if RUNTIME_OVERRIDE.search(content):
                reasons.append('unsupported_runtime_paths')
    cilium_evidence = False
    cilium_configs = ('05-cilium.conflist', '05-cilium.conf')
    for conf in path('/etc/cni/net.d').glob('*'):
        if conf.name in cilium_configs:
            # Only exact, trusted on-node CNI files can associate the cgroup
            # mount with this RKE2 runtime. Never follow symlink evidence.
            metadata = conf.lstat()
            if (unsafe('/etc/cni/net.d/' + conf.name) or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != 0 or metadata.st_mode & 0o022
                    or not metadata.st_mode & 0o444):
                reasons.append('untrusted_cilium_cni')
                continue
        if conf.is_file():
            if conf.name not in cilium_configs + ('10-canal.conflist', '10-flannel.conflist', '10-calico.conflist'):
                reasons.append('unrecognized_cni')
            try:
                cni = json.loads(conf.read_text())
                plugins = cni.get('plugins', [cni]) if isinstance(cni, dict) else None
                known = {'cilium-cni', 'calico', 'portmap', 'bandwidth', 'loopback', 'flannel', 'bridge', 'tuning'}
                valid = (isinstance(plugins, list) and bool(plugins)
                         and all(isinstance(p, dict) and p.get('type') in known for p in plugins))
                if not valid:
                    reasons.append('unrecognized_cni')
                elif conf.name in cilium_configs and any(p['type'] == 'cilium-cni' for p in plugins):
                    cilium_evidence = True
            except (ValueError, OSError, UnicodeError):
                reasons.append('unrecognized_cni')
    scripts = {}
    for name in ('uninstall', 'killall'):
        p = '/usr/local/bin/rke2-' + name + '.sh'
        if exists(p):
            st = path(p).stat()
            content = path(p).read_text()
            if unsafe(p) or st.st_uid != 0 or st.st_mode & 0o022 or 'rke2' not in content:
                reasons.append('untrusted_script')
            else:
                scripts[name] = p
    if (runtime or shared) and 'killall' not in scripts:
        reasons.append('missing_runtime_cleanup_script')
    evidence = evidence or bool(scripts)
    if present and not evidence:
        reasons.append('unrecognized_installation')
    if runtime and not evidence:
        reasons.append('unrecognized_runtime')
    mount_state = classify_mounts(mounts, evidence and data, owned_cilium=cilium_evidence)
    cleanup_mounts = mount_state['cleanup_mounts']
    for mount in mount_state['blocking_storage_mounts']:
        reasons.append('persistent_mount_in_cleanup_path' if mount['classification'] == 'persistent_storage'
                       else 'unrecognized_mount_in_cleanup_path')
    if mount_state['runtime_mounts'] and 'killall' not in scripts:
        reasons.append('missing_runtime_cleanup_script')
    rc, interfaces = command('ip', '-j', 'link', 'show')
    if rc:
        raise ValueError('network inspection unavailable')
    network = [v['ifname'] for v in json.loads(interfaces)
               if re.match(r'^(cilium|cni0$|flannel|cali|vxlan.calico|lxc|kube-ipvs0$)', v['ifname'])]
    for tool in ('iptables-save', 'ip6tables-save'):
        rc, rules = command(tool)
        if rc:
            raise ValueError('firewall inspection unavailable')
        if re.search(r'KUBE-|CNI-|CILIUM_|cali-|cali:|flannel', rules):
            network.append(tool)
    if network and not exclusive:
        reasons.append('unowned_network_state')
    if network and 'killall' not in scripts:
        reasons.append('missing_runtime_cleanup_script')
    pins = [str(p)[len(str(Path(root))):] if root != '/' else str(p)
            for p in path('/sys/fs/bpf/tc/globals').glob('cilium*')]
    if pins and not exclusive:
        reasons.append('unowned_bpf_state')
    # Helpers created by the installer are removable only when their link target is RKE2.
    helpers = []
    for name in ('kubectl', 'crictl', 'ctr'):
        p = '/usr/local/bin/' + name
        if path(p).is_symlink() and str(path(p).resolve()).startswith(str(path('/var/lib/rancher/rke2')) + '/'):
            helpers.append(p)
    return {'safe': not reasons, 'reasons': sorted(set(reasons)),
            'present': bool(present or server or agent or runtime or network or pins or helpers or cleanup_mounts),
            'remaining': present + [n + '.service' for n, yes in (('rke2-server', server), ('rke2-agent', agent)) if yes]
                         + (['runtime_processes'] if runtime else []) + network + pins + helpers + cleanup_mounts,
            'role': 'server' if server or exists('/var/lib/rancher/rke2/server') else 'agent' if agent else 'unknown',
            'scripts': scripts, 'cleanup_paths': present + helpers + pins,
            'storage': storage, 'cleanup_mounts': cleanup_mounts, 'runtime_active': runtime,
            'services_stopped': all(services[n]['ActiveState'] in ('inactive', 'failed')
                                    for n in ('rke2-server', 'rke2-agent')),
            'environment_diagnostics': environment_diagnostics,
            **mount_state}


def main():
    from ansible.module_utils.basic import AnsibleModule
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    try:
        module.exit_json(changed=False, inspection=inspect())
    except Exception:
        module.fail_json(msg='RKE2 removal inspection failed; no diagnostic inputs are logged.')


if __name__ == '__main__':
    main()
