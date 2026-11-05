# Semaphore Ansible automation

Ansible playbooks for Carekube Linux node connectivity, prerequisite validation,
OS preparation, RKE2 installation, and guarded cluster removal. Run locally or
through Ansible Semaphore; this repository does not contain the Semaphore service.

## Key capabilities

- Read-only connectivity and role-specific infrastructure validation.
- OS preparation and safe selection of dedicated worker storage for Longhorn.
- Explicit RKE2 bootstrap, controlled expansion, and preservation of matching nodes.
- Protected token backups, Kubernetes node verification, and kubeconfig extraction.
- Explicitly authorized full-cluster removal with runtime and storage safeguards.

## Quick start

Use an Ansible environment with `ansible.posix` installed. Configure addresses,
SSH users and independent repository/target keys as described in
[Usage](docs/Usage.md). From the repository root, check the inventory and connectivity:

```bash
ansible-inventory -i inventories/lab/hosts.yml --list
ansible-playbook -i inventories/lab/hosts.yml playbooks/connectivity.yml
```

A successful run reports Ansible ping and basic host facts without escalation.
Follow [Usage](docs/Usage.md#installation-workflow) for validation and installation;
review [Configuration](docs/Configuration.md) before overriding defaults.
Preparation can format verified unused worker disks. Installation and removal
require target privileges; removal requires explicit per-execution authorization.

## Documentation

| Document | Description |
|----------|-------------|
| [Requirements](docs/Requirements.md) | Functional and technical requirements |
| [Architecture](docs/Architecture.md) | System design and components |
| [Decisions](docs/Adr.md) | Architecture decision records |
| [Usage](docs/Usage.md) | Installation and usage |
| [Configuration](docs/Configuration.md) | Configuration reference |
| [Development](docs/Development.md) | Development workflows |
| [API](docs/Api.md) | Public interfaces |
| [Test cases](docs/Testcases.md) | Testing strategy and scenarios |
| [Security](docs/Security.md) | Security architecture |
| [Operations](docs/Operations.md) | Deployment and operations |
| [Roadmap](docs/Roadmap.md) | Known gaps and proposed improvements |

## License

No license file is included in this repository. License terms are not specified.
