# Ansible Semaphore Connectivity and RKE2 Validation

Read-only Ansible content for verifying Semaphore connectivity and validating whether Linux VMs are suitable for a future RKE2 installation.

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
│   └── prerequisites.yml
├── vars/
│   └── prerequisites.yml
└── .gitignore
```

## Prerequisites

- Ansible installed locally, or Ansible Semaphore configured to run Ansible.
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

The validation supports Ubuntu 24.04 and Debian 13. Other Linux distributions receive a warning. It checks operating-system facts, x86_64 architecture, CPU, memory, root storage, networking, time synchronization, swap, kernel modules and parameters, firewall utilities, existing Kubernetes/RKE2 processes, Longhorn-related worker dependencies, and explicitly configured endpoints.

Requirements are configured in `vars/prerequisites.yml`. Disk requirements use decimal `GB`; Linux memory is displayed in binary `GiB`. Memory uses a configurable tolerance because Linux-visible memory can be slightly below provisioned VM memory due to kernel and firmware reservations. The playbook does not claim that provisioned memory was verified unless an independent source provides it.

Dedicated worker or backup disks must be explicitly identified, for example with a host or group variable:

```yaml
prerequisites_data_disk_device: /dev/sdb
```

The playbook never assumes an unmounted disk is safe, and never partitions, formats, mounts, installs, configures, or restarts anything. Disk discovery reports block devices, filesystems, mount points, provisioned parent-disk capacity, root-device capacity, root-filesystem capacity, and available filesystem capacity. The OS-disk requirement is evaluated only against a confidently identified underlying disk. A confirmed missing or undersized required disk is FAIL; an ambiguous disk identity is WARN.

Network endpoint checks are disabled by default. Add only explicitly approved endpoints to `prerequisites_network_endpoints` in inventory or variables. Checks distinguish DNS, TCP, and optional TLS connectivity. Successful TCP or TLS connectivity does not prove application authorization or API-level access. No public service is tested implicitly.

Status meanings:

- PASS — requirement satisfied.
- WARN — non-blocking issue, uncertainty, or setting that a future RKE2 installation can configure.
- FAIL — mandatory infrastructure requirement is not satisfied, including missing/conflicting role assignment.
- SKIP — not applicable or not configured.

The overall result is `READY`, `READY WITH WARNINGS`, or `NOT READY`. The complete report is printed before the playbook returns nonzero for mandatory failures.

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
