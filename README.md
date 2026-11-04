# Ansible Semaphore Connectivity Test

Minimal, read-only Ansible content for verifying that Ansible Semaphore can connect to a Linux VM in Proxmox2.

## Repository structure

```text
ansible-semaphore/
├── README.md
├── ansible.cfg
├── inventories/
│   └── lab/
│       └── hosts.yml
├── playbooks/
│   └── connectivity.yml
└── .gitignore
```

## Prerequisites

- Ansible installed locally, or Ansible Semaphore configured to run Ansible.
- A Linux target VM in Proxmox2.
- An SSH user on the target VM. The user does not need sudo or root privileges.
- A separate SSH key for GitHub repository access and target VM access.

## Inventory configuration

Edit `inventories/lab/hosts.yml` and replace the two placeholders:

- `REPLACE_WITH_PROXMOX2_ADDRESS`: target IP address or DNS name.
- `REPLACE_WITH_SSH_USERNAME`: SSH username on the target VM.

Do not add passwords or private keys to the inventory or any other tracked file.

## Local execution

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
4. Replace the inventory address and username placeholders.

This key is used only by Ansible when connecting to the target VM. Semaphore supplies it to the task execution environment; it is not stored in Git or referenced by a private-key path committed to the repository.

Configure the task template to use this repository and inventory, then execute:

```bash
ansible-playbook -i inventories/lab/hosts.yml playbooks/connectivity.yml
```

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
