# Development

## Environment and repository layout

Use an execution environment with Ansible, Python, PyYAML, the `ansible.posix` collection, and SSH tooling. No dependency lockfile, package manifest, devbox/container definition, or Makefile is checked in; no minimum Ansible/Python version is specified. Use the Python interpreter belonging to the Ansible environment for Python tests: a system `python3` may not have Ansible installed.

The existing workflow uses direct commands from the repository root. If dependencies are absent, install them in the chosen Ansible environment, including the collection:

```bash
ansible-galaxy collection install ansible.posix
ansible-playbook --version
ansible-galaxy collection list ansible.posix
```

This supplies the configured debug callback and mount module; it is not a pinned dependency installation. Python tests import both `ansible` and `yaml`.

| Directory/file | Contents |
|----------------|----------|
| `playbooks/` | Six operational entry points. |
| `tasks/` | Shared production task sequences. |
| `filter_plugins/` | Python state classification and node verification. |
| `library/` | Custom read-only removal inspector. |
| `inventories/lab/` | Example lab roles, connections, resource overrides, and node aliases. |
| `vars/` | Prerequisite and RKE2 values loaded by operational plays. |
| `tests/` | Local YAML fixtures and Python regression suites. |
| `ansible.cfg` | Inventory, callback, module/filter paths, SSH and scratch defaults. |
| `docs/` | Requirements, implementation, workflows and verification references. |

## Build and local execution

There is no compilation/build stage or local application server. Ansible loads YAML, filters, and modules at execution time. [Usage](Usage.md) explains remote execution. Prefer the offline tests below during development; operational `--check` still contacts nodes and is not an offline test.

For a controller requiring another scratch location:

```bash
export ANSIBLE_LOCAL_TEMP=/tmp/ansible-semaphore-local
```

Run syntax checks without contacting lab nodes:

```bash
for playbook in playbooks/*.yml playbooks/*.yaml; do
  ansible-playbook -i inventories/lab/hosts.yml "$playbook" --syntax-check
done
```

## Offline regression checks

Run Python in the environment that contains Ansible and PyYAML:

```bash
python3 -m unittest discover -s tests -p 'test_rke2_*.py'
ansible-playbook tests/prerequisites_numeric.yml
ansible-playbook tests/prepare_nodes.yml
ansible-playbook tests/install_rke2.yml
ansible-playbook tests/rke2_barriers.yml
ansible-playbook tests/rke2_credentials.yml
ansible-playbook tests/rke2_check_mode.yml --check
```

These tests use local fixtures and do not contact lab nodes. Python orchestration tests create temporary inventories and action plugins that simulate target-side actions; they do not perform real host cleanup. Several tests invoke `ansible-playbook` as a subprocess. Negative scenarios intentionally trigger failed assertions and rescue them, or expect a failed subprocess. Use the overall suite exit status and assertions rather than interpreting each displayed `FAILED` line as a suite failure.

`rke2_barrier_case.yml` and `rke2_token_case.yml` are included fixtures, not standalone playbooks. Cluster-failure fixtures are driven by Python. See [Testcases](Testcases.md) for coverage boundaries and missing live tests. No measured coverage percentage or coverage tooling is checked in.

## Formatting, dependencies, and releases

No formatter, linter configuration, CI/CD workflow, automated release process, or project versioning policy is present. Review YAML/Python changes and run syntax/offline checks; do not claim an existing lint/build command. RKE2's pinned release in `vars/rke2.yml` is the installed dependency version, not this repository's release number. Dependency upgrades require explicit review and validation; installation is not an in-place upgrade tool.

When changing behavior, update the configuration reference and relevant requirement/test/decision links. Keep source evidence in documentation and avoid copying secrets or controller artifacts. The repository has no contribution template or declared license; establish these only through a separate project decision.
