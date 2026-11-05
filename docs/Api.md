# Public interfaces

## Interface boundary

This repository exposes Ansible playbooks, not a REST/HTTP API, standalone CLI executable, web UI, or SDK. Semaphore's own API/authentication and the deployed Kubernetes API are external interfaces; they are not implemented here.

## Ansible entry points

Commands run from the repository root:

```bash
ansible-inventory -i inventories/lab/hosts.yml --list
ansible-playbook -i inventories/lab/hosts.yml playbooks/connectivity.yml
```

| Playbook | Target | Input/action | Output |
|----------|--------|--------------|--------|
| `playbooks/connectivity.yml` | proxmox2_targets | SSH/Ansible ping and facts; no become | Host OS, kernel, architecture, memory, CPU |
| `playbooks/prerequisites.yml` | proxmox2_targets | Roles, resource overrides, read-only diagnostics | Six category reports and overall readiness |
| `playbooks/prepare-nodes.yml` | proxmox2_targets | OS preparation; worker storage safety rules | Changes and storage readiness report |
| `playbooks/install-rke2.yml` | selected control_plane/worker | Classify, preserve/bootstrap/join, verify | Sanitized node states; token backup and kubeconfig |
| `playbooks/remove-rke2.yml` | complete control_plane/worker | Explicit confirmation plus safety preflight | WOULD REMOVE/ABSENT in check mode; REMOVED/ABSENT/INCOMPLETE otherwise |

### Common CLI options

These are Ansible options, not custom parser flags. `ansible-playbook --help` is the complete installed-version reference.

| Option | Use here |
|--------|----------|
| `-i PATH` | Select inventory; repository config defaults to lab. |
| `-e KEY=VALUE`, `-e '{"key": value}'`, `-e @file.yml` | Highest-priority extra variables; JSON/YAML preserves types. |
| `--limit PATTERN` | Select hosts; install must include the token source, removal rejects partial cluster scope. |
| `--check` | Installation/removal inspection with mutation guards; still contacts nodes. Not a guarantee of general OS preparation dry-run completeness. |
| `--syntax-check` | Parse playbook without executing target tasks. |
| `--ask-become-pass` | Prompt locally when escalation needs a password; configure the runner appropriately in Semaphore. |

Examples and sensitive operation instructions are in [Usage](Usage.md) and [Operations](Operations.md). Settings and precedence are in [Configuration](Configuration.md).

## Formats and authentication

Inventory and variable files use YAML; extra variables can be JSON or YAML. Node configuration is YAML and the managed comparison marker is JSON. Final verification consumes `kubectl get nodes -o json`. Token output is a single trimmed non-whitespace token; kubeconfig is YAML. Neither is a public machine-readable automation response.

Authentication is SSH to targets and separate SSH repository access in Semaphore. Privileged target operations use Ansible become. The repository provides no user accounts or RBAC; controller/Semaphore access controls are external. The extracted kubeconfig carries cluster-admin credentials. See [Security](Security.md).

## Reports and errors

Prerequisites report `PASS`, `WARN`, `FAIL`, or `SKIP` and overall `READY`, `INCOMPLETE`, or `NOT READY`. Any FAIL finding or incomplete mandatory infrastructure evidence causes a nonzero result after reporting. These readiness names are specific to prerequisites; removal's `INCOMPLETE` means cleanup/storage verification failed.

Installation reports classification and differing managed keys without values. Inspection errors are separate from drift. API verification failures expose allowlisted missing/not-ready/version-mismatch categories, not raw Kubernetes command output. Removal refusals expose bounded escaped environment paths and mount classifications rather than credential values.

Ansible recap and process exit status indicate execution outcome; failures return nonzero under Ansible's exit conventions. Reports are human-readable, not a versioned JSON schema. No repository-defined numeric error-code contract or HTTP status-code contract exists.

## Internal extension interfaces

The filter plugin exports `classify_rke2` and `verify_rke2_nodes`. The custom module `rke2_remove_inspect` accepts no module arguments, supports check mode, and returns `changed: false` with an `inspection` object. These support playbook internals and tests; they are not a separately versioned public API. See [Architecture](Architecture.md).
