# Ansible Semaphore Connectivity, RKE2 Validation, and Installation

Ansible content for verifying Semaphore connectivity, validating Linux VMs, preparing nodes, and installing an idempotent RKE2 cluster.

## Repository structure

```text
ansible-semaphore/
├── README.md
├── ansible.cfg
├── inventories/
│   └── lab/
│       └── hosts.yml
├── playbooks/
│   ├── connectivity.yml
│   ├── prerequisites.yml
│   ├── prepare-nodes.yml
│   └── install-rke2.yml
├── vars/
│   ├── prerequisites.yml
│   └── rke2.yml
└── .gitignore
```

## Prerequisites

- Ansible installed locally, or Ansible Semaphore configured to run Ansible.
- The `ansible.posix` collection available in the execution environment; its debug stdout callback is configured to preserve multiline report formatting.
- A Linux target VM in Proxmox2.
- An SSH user on the target VM. The user does not need sudo or root privileges.
- A separate SSH key for GitHub repository access and target VM access.

## Inventory and node roles

`proxmox2_targets` remains the parent group used by the connectivity playbook. Put each host in exactly one role group:

- `control_plane` — RKE2 control-plane nodes.
- `worker` — RKE2 worker nodes and Longhorn storage nodes.
- `backup` — standalone backup/S3 infrastructure; Kubernetes checks are skipped.

Role membership is authoritative. A host in no role group or multiple role groups receives a mandatory FAIL.

Edit `inventories/lab/hosts.yml` to configure addresses and users:

- Set `ansible_host` to the target IP address or DNS name.
- Set `ansible_user` to the SSH username on the target VM.

Do not add passwords or private keys to the inventory or any other tracked file.

## Prerequisites validation

The validation supports Ubuntu 24.04 and Debian 13. Other Linux distributions receive a warning. It checks operating-system facts, x86_64 architecture, CPU, memory, root storage, networking, time synchronization, RKE2 kernel modules and parameters, Cilium eBPF prerequisites, Longhorn worker dependencies, and explicitly configured endpoints. Reports use six categories: `SYSTEM`, `STORAGE`, `NETWORK`, `RKE2`, `CILIUM`, and `LONGHORN`.

Validation runs in `fresh_install` mode by default. In this mode, RKE2, Cilium, Longhorn, and Carekube-managed installation dependencies are not required to be present. Set `rke2_validation_mode: existing_install` when validating an already installed cluster.

Requirements are mapped to the [RKE2 requirements](https://docs.rke2.io/install/requirements), [Cilium system requirements](https://docs.cilium.io/en/stable/operations/system_requirements/), and [Longhorn installation requirements](https://longhorn.io/docs/1.13.0/deploy/install/) documentation. Infrastructure provisioning is owned by Infrastructure; installation-managed modules, sysctls, packages, services, and CNI/storage setup are owned by Carekube.

Requirements are configured in `vars/prerequisites.yml` with production defaults. Inventories may select a validation profile and provide role-specific nested overrides; the lab inventory selects `lab` and uses smaller control-plane and worker requirements without changing production defaults. The active profile and effective role requirements are printed in each report. Disk requirements use decimal `GB`; Linux memory is displayed in binary `GiB`. Memory uses a configurable tolerance because Linux-visible memory can be slightly below provisioned VM memory due to kernel and firmware reservations. The playbook does not claim that provisioned memory was verified unless an independent source provides it.

Worker Longhorn storage is discovered automatically from block-device and mount diagnostics. A disk is formatted only when it is conclusively verified to have no partitions, signatures, mounts, swap, LVM, RAID, holders, or other storage consumers. An explicit device may still be supplied with a host or group variable when discovery finds multiple suitable disks:

```yaml
prerequisites_data_disk_device: /dev/vdc
```

The preparation playbook first validates an existing `/var/lib/longhorn` mount, including its underlying storage, filesystem, capacity, available space, UUID, and persistent UUID-based configuration. If the path is not mounted, it excludes the OS disk, partitions, mounted devices, swap, LVM, RAID, and devices with existing filesystems or partitions before evaluating unused disks. Exactly one suitable disk is formatted and mounted automatically; multiple suitable disks require an explicit override, which is subject to the same safety checks. The selected disk is revalidated immediately before formatting, and any identity or ownership ambiguity fails without modifying storage. The OS-disk requirement is evaluated only against a confidently identified underlying disk.

Network endpoint checks are disabled by default. Add only explicitly approved endpoints to `prerequisites_network_endpoints` in inventory or variables. Checks distinguish DNS, TCP, and optional TLS connectivity. Successful TCP or TLS connectivity does not prove application authorization or API-level access. No public service is tested implicitly.

Status meanings:

- PASS — requirement satisfied.
- WARN — non-blocking issue, uncertainty, or setting that Carekube can configure during installation.
- FAIL — confirmed mandatory blocker, including missing/conflicting role assignment.
- SKIP — not applicable, runtime-only before installation, or not configured.

The overall result is `READY`, `INCOMPLETE`, or `NOT READY`. `INCOMPLETE` is used only for mandatory, applicable, Infrastructure-owned requirements whose evidence is unavailable or ambiguous. Carekube-managed installation tasks cannot produce `INCOMPLETE`. `NOT READY` is reserved for confirmed blockers, and the complete report is printed before the playbook returns nonzero.

Runtime evidence includes exact service state, process ID, executable, and command line. A running `containerd` process alone is compatible with RKE2 and is not a conflict. Active but ambiguous runtime evidence is reported as a warning; only verified incompatible installations or an enabled clean-install policy can produce a runtime failure.

Run locally with:

```bash
ansible-playbook \
  -i inventories/lab/hosts.yml \
  playbooks/prerequisites.yml
```

## Local connectivity execution

From the repository root:

```bash
ansible-inventory -i inventories/lab/hosts.yml --list
ansible-playbook -i inventories/lab/hosts.yml playbooks/connectivity.yml
```

The playbook does not gather facts during the initial connection step. It first runs `ansible.builtin.ping`, then explicitly runs `ansible.builtin.setup` and displays basic system information. It does not use sudo, root privileges, or modifying modules.

## Semaphore configuration

## Installation workflow

Run the stages in this order:

```text
connectivity.yml -> prerequisites.yml -> prepare-nodes.yml -> install-rke2.yml
```

`install-rke2.yml` is intentionally separate from operating-system preparation and later platform components. It targets only `control_plane` and `worker` and requires root privileges.

Configure `vars/rke2.yml` through inventory/group variables or Semaphore extra variables. Set `rke2_bootstrap_node` explicitly; inventory order is not used. Configure the Kubernetes API and RKE2 registration endpoints independently:

```yaml
rke2_bootstrap_node: basel-rke2-1
rke2_api_endpoint: 192.168.50.165       # lab direct node IP or production F5 VIP
rke2_api_port: 6443
rke2_registration_endpoint: 192.168.50.165
rke2_registration_port: 9345
rke2_tls_sans: [192.168.50.165]
```

The first fresh server uses `cluster-init: true`. Joining control-plane nodes never use `cluster-init`; they join through the registration endpoint. An existing bootstrap node is detected and preserved, never reinitialized. Existing matching nodes are not rewritten or restarted during expansion. Drift or uncertain existing state fails safely for review.

RKE2 generates the server token during a fresh bootstrap unless `rke2_join_token` is explicitly supplied. Existing-cluster expansion reads the existing token from `rke2_token_source_node`, or the bootstrap node by default. The playbook never rotates or regenerates an existing token. It stores a protected `0600` recovery copy on the Ansible controller; include that file in encrypted disaster-recovery backups and do not commit it.

The playbook configures RKE2-managed Cilium and disables bundled `rke2-ingress-nginx`. It extracts the admin kubeconfig to `rke2_kubeconfig_path`, replaces the localhost API address with the configured API endpoint, and writes it with mode `0600`. Token and kubeconfig operations use hidden task logging.

Run the installation template with:

```bash
ansible-playbook -i inventories/lab/hosts.yml playbooks/install-rke2.yml
```

For production, override the endpoint, SAN, bootstrap, and token-source variables in the Semaphore environment. Supply `rke2_join_token` only through Ansible Vault or a protected Semaphore extra variable when controlled bootstrap or recovery requires it.

Local checks that do not contact target VMs:

```bash
ANSIBLE_LOCAL_TEMP=/private/tmp/ansible-local ansible-playbook -i inventories/lab/hosts.yml playbooks/install-rke2.yml --syntax-check
ANSIBLE_LOCAL_TEMP=/private/tmp/ansible-local ansible-playbook tests/install_rke2.yml
```

Configure the two SSH authentication contexts independently in Semaphore's Key Store.

### 1. GitHub repository access

1. Add the SSH private key authorized to read `git@github.com:e-a-s-t/ansible-semaphore.git` to the Semaphore Key Store.
2. Select that key in the repository configuration used to clone or update the private GitHub repository.
3. Ensure its corresponding public key is authorized on GitHub.

This key is used only for Git operations. It is not the key Ansible should use for the Proxmox2 target.

### 2. Proxmox2 target access

1. Add a different SSH private key to the Semaphore Key Store.
2. Select or associate that key with the project, environment, or task template used for this Ansible job, according to the Semaphore deployment configuration.
3. Install the corresponding public key in the target user's `~/.ssh/authorized_keys` on Proxmox2.
4. Confirm the inventory address and username are correct.

This key is used only by Ansible when connecting to the target VM. Semaphore supplies it to the task execution environment; it is not stored in Git or referenced by a private-key path committed to the repository.

Configure the task template to use this repository and inventory, then execute:

```bash
ansible-playbook -i inventories/lab/hosts.yml playbooks/connectivity.yml
```

For validation, configure the Semaphore task template with the same repository and target SSH key, then run:

```bash
ansible-playbook -i inventories/lab/hosts.yml playbooks/prerequisites.yml
```

The validation defaults to no privilege escalation. Some diagnostics may therefore be unavailable and will be reported as WARN rather than causing an incomplete report.

The repository key is used before task execution to clone the repository. The target key is used during task execution for SSH connections from Semaphore to Proxmox2. Keep these keys independent and rotate them independently.

## Expected output

A successful run reports a successful Ansible ping and displays:

- Hostname
- Operating system and version
- Kernel version
- CPU architecture
- Available memory
- Number of CPU cores

## Troubleshooting SSH connectivity

- Confirm the target address and SSH username in `inventories/lab/hosts.yml`.
- Confirm the Proxmox2 public key is in the target user's `~/.ssh/authorized_keys`.
- Confirm the target SSH key is selected for the Semaphore task, not only for repository checkout.
- Confirm the GitHub repository key has read access to the private repository.
- Test the target connection from the same execution environment with `ssh USER@TARGET` when permitted.
- Check Semaphore task logs for host-key, username, key selection, or network errors.

Never commit either private key, passwords, or other credentials.

### RKE2 rerun safety and offline regression checks

Every targeted RKE2 host must pass classification and drift validation before
any node can be installed, configured, or started. A failed or unreachable host
continues to block the cluster-wide barrier even after Ansible removes it from
active execution. Inspection errors are reported separately from drift, without
configuration values. Matching existing nodes are preserved.

Include the selected token source in Semaphore's host limit. To add workers
while the original bootstrap is unavailable, explicitly select another existing
control-plane node with `rke2_token_source_node` and target that source together
with the workers; exclude the unavailable bootstrap. Token retrieval, validation,
and the protected controller backup must succeed before joining nodes mutate.
A binary-only partial worker installation resumes without reinstalling its binary.
Data-bearing ambiguous states require operator review; no data is deleted.

Additional offline checks (use a Python environment containing Ansible and PyYAML):

```bash
python -m unittest discover -s tests -p 'test_rke2_*.py'
ansible-playbook tests/rke2_barriers.yml
ansible-playbook tests/rke2_credentials.yml
ansible-playbook tests/rke2_check_mode.yml --check
```

Negative cases deliberately exercise failed assertions and rescue them. The
multi-host Python test expects Ansible to reject its deliberately failed hosts.
These checks use local fixtures and do not connect to lab nodes.
