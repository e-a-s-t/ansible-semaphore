"""RKE2 state inspection. Exceptions deliberately contain no input values."""
import base64
import json
import re
import yaml


def classify_rke2(paths, version_result, config_result, marker_result, expected, version, bootstrap, control_plane):
    def decode(result):
        if not isinstance(result, dict) or 'content' not in result:
            raise ValueError('unreadable configuration or marker')
        return base64.b64decode(result['content'], validate=True).decode('utf-8')

    stage = 'read_or_parse'
    try:
        binary, config_exists, data, marker_exists = [x['stat']['exists'] for x in paths['results']]
        current = yaml.safe_load(decode(config_result)) if config_exists else {}
        marker = json.loads(decode(marker_result)) if marker_exists else None
        stage = 'invalid_shape'
        if not isinstance(current, dict) or (marker_exists and not isinstance(marker, dict)):
            raise ValueError('invalid configuration shape')
        for obj in [current] + ([marker] if marker_exists else []):
            for key in ('disable', 'tls-san'):
                if key in obj and (not isinstance(obj[key], list) or any(not isinstance(v, str) for v in obj[key])):
                    raise ValueError('invalid managed list')
        stage = 'version_inspection'
        installed = ''
        if binary:
            installed_match = re.search(r'v[0-9]+\.[0-9]+\.[0-9]+[^\s]*', version_result.get('stdout', ''))
            if version_result.get('rc', 0) != 0 or not installed_match:
                raise ValueError('unreadable installed version')
            installed = installed_match.group()
        stage = 'comparison_error'
        differences = []
        if binary and installed != version:
            differences.append('version')
        if marker_exists:
            # Existing markers also carry server-only defaults for workers.
            if set(marker) != set(expected):
                differences.append('marker')
            for key in expected:
                a, b = marker.get(key), expected[key]
                if key in ('disable', 'tls-san') and isinstance(a, list):
                    a, b = sorted(a), sorted(b)
                if a != b:
                    differences.append('marker.' + key)
        if config_exists:
            keys = ['cluster-init'] if bootstrap else ['server']
            if control_plane:
                keys += ['cni', 'disable', 'tls-san']
            for key in keys:
                a, b = current.get(key), expected[key]
                if key in ('disable', 'tls-san') and isinstance(a, list):
                    a, b = sorted(a), sorted(b)
                if a != b:
                    differences.append(key)
            if not bootstrap and current.get('cluster-init', False) is not False:
                differences.append('cluster-init')
            if bootstrap and 'server' in current:
                differences.append('server')
        state = ('drifted' if differences else
                 'unknown' if (data or marker_exists or config_exists) and (not config_exists or not binary) else
                 'matching' if config_exists else 'incomplete_install' if binary else 'new')
        return dict(state=state, drift=bool(differences), differences=sorted(set(differences)), inspection_error=False, error_category='none')
    except Exception:
        return dict(state='inspection_error', drift=False, differences=[], inspection_error=True, error_category=stage)


class FilterModule:
    def filters(self):
        return {'classify_rke2': classify_rke2}
