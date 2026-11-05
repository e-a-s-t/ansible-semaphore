# Ansible Semaphore Connectivity, RKE2 Validation, and Installation

Ansible content for verifying Semaphore connectivity, validating Linux VMs, preparing nodes, installing RKE2, and safely removing it for rebuilds.

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
1. Connectivity
       |
2. Prerequisites
       |
3. Prepare Nodes
       |
4. Install RKE2
       |
5. Remove RKE2
       |
       +----> 4. Install RKE2
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

The playbook configures RKE2-managed Cilium and selects `ingress-controller: none` to disable bundled ingress. It extracts the admin kubeconfig to `rke2_kubeconfig_path`, replaces the localhost API address with the configured API endpoint, and writes it with mode `0600`. Token and kubeconfig operations use hidden task logging.

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

RKE2 targets are captured once, before controller setup or delegation, from the
`control_plane` and `worker` inventory groups intersected with the initial host
selection (including Semaphore's host limit). Localhost aliases and controller-only
hosts are excluded. Later inventory additions and failed hosts never change this
snapshot: every originally targeted node must complete preflight. Bootstrap and
token-source dependencies are validated separately without expanding the targets.

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

### Semaphore controller execution

RKE2 controller tasks explicitly use the local connection and run as the Semaphore
process user. Root access remains enabled only for operations on cluster nodes.
The playbook establishes localhost settings before delegation, including when
Semaphore supplies its own inventory.

Ansible controller scratch space defaults to `/tmp/ansible-semaphore-local`;
Ansible creates private per-process directories there. Set `ANSIBLE_LOCAL_TEMP`
in the Semaphore environment to override this base. Controller module staging
uses `rke2_controller_remote_tmp`, defaulting to
`/tmp/ansible-semaphore-<uid>/remote`, with mode `0700`. Set that variable through
Semaphore extra vars if a different writable location is needed. Remote-node
SSH connections and their temporary-directory settings remain independent.

Token backups retain their configured persistent destination, directory mode
`0700`, and file mode `0600`; temporary storage does not replace token backups.
API verification and kubeconfig extraction require current-run bootstrap and token
readiness plus successful completion of every targeted node. Failures block those
operations even if Ansible continues into later plays.

### RKE2 final verification and ingress migration

Fresh v1.37 installations retain Cilium, CoreDNS, metrics-server, the snapshot
components and the standalone `rke2-gateway-api-crd` chart. All managed servers
use `ingress-controller: none`; no ingress or gateway implementation is installed
by this playbook. Disabling only `rke2-ingress-nginx` does not disable the v1.37
Traefik default. See the [RKE2 networking documentation](https://docs.rke2.io/networking/networking_services)
and [server configuration reference](https://docs.rke2.io/reference/server_config).

Final verification runs directly as root on the selected inventory control-plane
host, retaining that host's SSH settings. `rke2_token_source_node` selects an
alternative healthy control plane (include it in the host limit). The API JSON
must contain every inventory node, Ready, at exactly `rke2_version`; extra nodes
do not substitute for missing nodes. Set `rke2_node_name` for aliases or custom
node names. Otherwise the remote hostname is used. The lab mappings are
`basel-rke2-1` → `basel-rke2-01` and `basel-rke2-2` → `basel-rke2-02`.
Retries allow registration to converge. Failure diagnostics report only expected
node identities and failure categories, never raw command output or credentials.
Check mode skips final verification and extraction.

Inspect nodes on a control plane with:

```bash
sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get nodes -o json
```

The admin kubeconfig is read there with hidden logging and saved on the Semaphore
controller as the Semaphore process user at `rke2_kubeconfig_path` (default
`$HOME/.kube/carekube-rke2.yaml`), mode `0600`, parent directory `0700`.
Its loopback server address is replaced by the configured API endpoint. Repeated
extraction of unchanged content makes no change.

Existing installations are never migrated automatically. The new ingress setting
is drift: the playbook stops before mutation. To finish verification of the
existing Traefik installation first, explicitly use the temporary extra variable
`rke2_ingress_controller: traefik`. Legacy configuration and markers without an
explicit ingress setting are interpreted as the v1.37 Traefik default. This
preserves their contents, token, binary and healthy services.

For a controlled migration, schedule a maintenance window (the lab has only one
control plane), back up etcd and securely back up configuration, token, kubeconfig,
and Gateway API resources. Inspect installed HelmCharts and Gateway API CRD
ownership first; ensure `rke2-gateway-api-crd` owns the required CRDs before removing
Traefik. v1.37 separates these CRDs from Traefik; do not delete Gateway API CRDs
or the standalone chart. Review any workloads depending on Traefik.

Manually add `ingress-controller: none` to each server's existing
`/etc/rancher/rke2/config.yaml`, preserving every other setting, especially tokens,
Cilium, SANs and cluster identity. Restart `rke2-server` on one server at a time,
waiting for healthy API/etcd and Ready nodes between servers. Confirm the bundled
Traefik charts and workloads are removed and Gateway API CRDs remain. Do not
restart workers or delete cluster data. If validation fails, restore the prior
server configuration and restart that server during the window.

After successful migration, securely update only the `ingress-controller` field
to `none` in each existing `.carekube-managed-config` JSON marker. Remove the
temporary extra variable and rerun the playbook. All other differences still
require review; do not bypass drift checks or recreate markers blindly.


## Remove RKE2 and rebuild

Create a Semaphore task template named **5. Remove RKE2**, using playbook
`playbooks/remove-rke2.yml` and inventory `inventories/lab/hosts.yml`.
Supply confirmation explicitly in the execution's extra variables:

```json
{"rke2_remove_confirm": true}
```

Configure a Semaphore survey variable named `rke2_remove_confirm` as an **Enum**
with choices `false` and `true`, defaulting to `false`. Semaphore passes survey
values as strings; explicitly select `true` to authorize removal for that execution.
The playbook accepts native YAML boolean `true` or the string `"true"`
(case-insensitive). Missing, false, empty, whitespace-padded, and arbitrary values
are rejected; values such as `yes` and `1` do not authorize removal.

The default is false. Never put destructive authorization in inventory. Running
this template alone does not authorize removal. The command-line equivalent is:

```bash
ansible-playbook -i inventories/lab/hosts.yml playbooks/remove-rke2.yml \
  -e '{"rke2_remove_confirm": true}'
```

For inspection without changes, append `--check`; confirmation is still required.
Check mode contacts the selected nodes for read-only inspection, reports `WOULD REMOVE`
or `ABSENT`, and does not stop services, run cleanup scripts, or delete files.
Implementation tests and syntax checks below do not contact lab nodes.

Removal supports the standard Linux tarball layout used by this repository.
Every inventory `worker` and `control_plane` node must be included and reachable;
partial-cluster removal is rejected. `rke2_bootstrap_node` explicitly selects the
last node removed. Workers are removed first, then additional control-plane nodes,
then bootstrap, one node at a time. All nodes must pass preflight before removal
starts. A failure halts later phases; previously removed nodes stay removed.

The remover accepts recognized RKE2 installations, including installations without
a Carekube marker, drifted configuration, and safely identifiable partial installs.
It refuses foreign Kubernetes, ambiguous shared CNI/runtime state, unsupported
custom runtime paths, and unsafe cleanup mounts or symlinks. Refused states require
operator investigation; changing the confirmation does not bypass these checks.
It uses installed official uninstall/runtime cleanup scripts when available and
an inspected allowlist for remaining files. Missing scripts with runtime or CNI
state require operator recovery rather than generic network deletion.

Removal deletes RKE2 services, installation artifacts, configuration, certificates,
credentials, embedded etcd, and owned runtime/CNI state. It preserves OS preparation,
prerequisite packages, iSCSI, modules, sysctls, swap settings, SSH, dedicated disks,
and `/var/lib/longhorn` with its persistent mount configuration. Disk identity,
Longhorn mounts, and `/etc/fstab` are compared before and after cleanup. No disks
are formatted or partitioned. Preserving Longhorn storage does not automatically
restore its Kubernetes resources or recover volumes into a rebuilt cluster.

A node reports `REMOVED` only after independent verification. An already removed
node reports `ABSENT`; uninstall errors or remaining artifacts/storage changes
produce `INCOMPLETE` and fail the run. After successful removal, run **4. Install
RKE2** again on the prepared machines without recreating VMs or reinstalling the OS.

Controller-side token backups (`rke2_token_backup_path`) and kubeconfigs
(`rke2_kubeconfig_path`) are preserved for audit and recovery. These credentials
may no longer work after rebuilding. Archive them securely before reinstalling,
since installation writes the current cluster credentials to those paths.

Offline removal checks (the fixtures never execute host cleanup):

```bash
ansible-playbook -i inventories/lab/hosts.yml playbooks/remove-rke2.yml --syntax-check
python3 -m unittest discover -s tests -p 'test_rke2_*.py'
```
