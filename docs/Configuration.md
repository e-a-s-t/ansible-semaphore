# Configuration

## Configuration precedence

Run commands from the repository root so `ansible.cfg` and relative plugin paths are selected. Ansible uses its own configuration discovery; `ANSIBLE_CONFIG` can explicitly select this file. There is no repository-specific configuration loader.

For overlapping variables in these playbooks, inventory/group/host variables are lower priority than play variables and `vars_files`. Extra variables (`-e`, including `-e @file.yml`) override those values. Runtime facts and task-local variables also participate in Ansible precedence; internal facts should not be overridden.

Consequently, putting `rke2_version`, endpoints, or `prerequisites_data_disk_device` only in inventory does **not** override values loaded from `vars/`. Use protected Semaphore extra variables or an extra-vars file. Inventory works for inputs not shadowed there, including `rke2_node_name`, `prerequisites_validation_profile`, and `prerequisites_requirement_overrides`. The latter is recursively combined with production resource defaults; profile names alone do not select thresholds.

All tables describe repository defaults, not a claim that every listed value is independently configurable. No secrets are shown. See [Usage](Usage.md) and [Operations](Operations.md) for workflows.

## RKE2 defaults

Source: [vars/rke2.yml](../vars/rke2.yml). All entries have defaults, but environment-specific node/endpoints must be valid for the selected inventory. Authorization is required per removal execution.

| Variable | Default | Meaning and constraints |
|----------|---------|-------------------------|
| `rke2_version` | `v1.37.1+rke2r1` | Pinned release; validated version shape. Existing version mismatch is drift. |
| `rke2_bootstrap_node` | `basel-rke2-1` | Must name an inventory control plane; not inferred from order. |
| `rke2_token_source_node` | `""` | Empty selects bootstrap; alternate must be a selected matching control plane. |
| `rke2_join_token` | `""` | Optional fresh-bootstrap token. Use protected extra vars/Vault; existing tokens are read, not rotated. |
| `rke2_api_endpoint` | `192.168.50.165` | Required nonempty API address; also included in effective SANs. |
| `rke2_api_port` | `6443` | Positive integer conversion checked; used when rewriting kubeconfig. |
| `rke2_registration_endpoint` | `192.168.50.165` | Required nonempty joining endpoint. |
| `rke2_registration_port` | `9345` | Positive integer conversion checked; used by joining nodes. |
| `rke2_tls_sans` | `[]` | Additional SAN strings; API endpoint is added and deduplicated. |
| `rke2_cni` | `cilium` | Installation asserts cilium; other CNIs are unsupported. |
| `rke2_ingress_controller` | `none` | Server setting. Changing an existing managed value is drift; migration is manual. |
| `rke2_disabled_components` | `[rke2-ingress-nginx]` | RKE2 disable list; no separate ingress implementation is deployed. |
| `rke2_config_path` | `/etc/rancher/rke2/config.yaml` | Config file location; removal requires this exact default. |
| `rke2_data_dir` | `/var/lib/rancher/rke2` | Inspection/token path; not rendered as a custom data-dir setting. Removal requires default. |
| `rke2_managed_marker` | `/etc/rancher/rke2/.carekube-managed-config` | JSON managed-field marker; removal requires default. |
| `rke2_kubeconfig_path` | `{{ lookup('env', 'HOME') }}/.kube/carekube-rke2.yaml` | Controller persistent admin kubeconfig, file 0600 and parent 0700. |
| `rke2_token_backup_path` | `{{ lookup('env', 'HOME') }}/.config/carekube/rke2/server-token` | Controller persistent token recovery copy, file 0600 and parent 0700. |
| `rke2_install_url` | `https://get.rke2.io` | Target-side installer script fetched with curl and executed. |
| `rke2_artifact_base_url` | `https://github.com/rancher/rke2/releases/download` | Base for preflight artifact HEAD probes; does not redirect the installer download source. |
| `rke2_artifact_timeout` | `20` | Seconds per preflight HEAD request. |
| `rke2_installer_diagnostic_limit` | `4000` | Maximum displayed installer stdout/stderr length after redaction. |
| `rke2_api_wait_retries` | `60` | Final per-target systemd service and Kubernetes node verification retry setting; bootstrap token wait is separately fixed at 60 retries. |
| `rke2_api_wait_delay` | `5` | Final service and Kubernetes verification retry delay in seconds; bootstrap token wait uses a fixed 5 seconds. |
| `rke2_controller_remote_tmp` | `/tmp/ansible-semaphore-{{ lookup('pipe', 'id -u') }}/remote` | Controller-only staging directory, mode 0700; evaluated with controller uid. |
| `rke2_remove_confirm` | `false` | Only native true or case-insensitive string true authorizes; no whitespace trimming. |
| `rke2_remove_cleanup_attempts` | `3` | Positive integer, excluding booleans; official cleanup attempts only. |
| `rke2_remove_cleanup_delay` | `3` | Nonnegative integer, excluding booleans; seconds between attempts. |

## Prerequisite defaults

Source: [vars/prerequisites.yml](../vars/prerequisites.yml).

| Role | vCPU | Memory GiB | OS disk GB | Dedicated data GB |
|------|------|------------|------------|-------------------|
| control_plane | 4 | 8 | 100 | 0 |
| worker | 8 | 32 | 100 | 500 |
| backup | 4 | 8 | 100 | 2000 |

`prerequisites_production_requirements` contains the above mappings with keys `vcpu`, `memory_gib`, `os_disk_gb`, and `data_disk_gb`. Optional `prerequisites_requirement_overrides` defaults to `{}` at use and merges recursively by role. The lab inventory sets control-plane OS disk 50 GB and worker 4 vCPU/8 GiB/32 GB OS/20 GB data. Backup retains production thresholds. Disk units are decimal GB, memory binary GiB.

| Variable | Default | Meaning and constraints |
|----------|---------|-------------------------|
| `rke2_validation_mode` | `fresh_install` | fresh_install or existing_install; controls runtime check applicability. |
| `rke2_allowed_validation_modes` | `[fresh_install, existing_install]` | Allowed-mode list; implementation default, not a way to implement new modes. |
| `rke2_clean_install_policy` | `false` | Opt-in clean-install runtime policy. |
| `prerequisites_memory_tolerance` | `0.05` | Fraction allowed below nominal Linux-visible memory, not hypervisor verification. |
| `prerequisites_data_disk_device` | `""` | Empty enables worker discovery; explicit device remains subject to safety checks. Backup disk inspection needs an explicit device. |
| `prerequisites_longhorn_disk_discovery_command` | Shared shell program; see source | Shared read-only shell discovery program. Treat as trusted executable configuration, not user input. |
| `prerequisites_network_endpoints` | `[]` | Optional trusted probe list; see item schema below. |
| `prerequisites_cilium_routing_mode` | `""` | Unset skips mode-specific checks; recognized context includes vxlan/native/direct/wireguard. |
| `prerequisites_cilium_pod_cidr` | `""` | Optional pod CIDR; paired with service CIDR for static overlap validation. |
| `prerequisites_cilium_service_cidr` | `""` | Optional service CIDR; paired with pod CIDR for static overlap validation. |
| `prerequisites_cilium_min_kernel` | `5.10` | Minimum version used by Cilium validation. |
| `prerequisites_longhorn_engine` | `v1` | v1 default; v2 enables additional validation, not deployment. |
| `prerequisites_longhorn_data_path` | `/var/lib/longhorn` | Validation/preparation mount path. Removal protection is fixed to /var/lib/longhorn; do not assume custom-path compatibility. |
| `prerequisites_longhorn_filesystems` | `[ext4, xfs]` | Accepted validation filesystems; preparation creates ext4 for unused disks. |
| `prerequisites_longhorn_required_utilities` | `[fstrim, blkid]` | Declared utility list; current diagnostic probes hard-code fstrim and blkid rather than consuming this list. |
| `prerequisites_mandatory_infrastructure_checks` | `[Node role assignment, Operating system, Architecture, CPU, Memory, OS disk, Dedicated role data disk, IPv4 address, Default route, Hostname resolution, DNS resolvers, Time synchronization]` | Names used to classify mandatory infrastructure evidence; see source list. |
| `prerequisites_installation_deferred_settings` | `[br_netfilter module loaded, net.bridge.bridge-nf-call-iptables enabled, iscsiadm available on workers]` | Declared context list; not consumed elsewhere in current playbooks. |

### Additional inventory and preparation inputs

- `prerequisites_validation_profile`: optional report label, default `production`; lab sets `lab`.
- `rke2_node_name`: optional Kubernetes identity per host, default remote hostname lowercased when discovered. Must be unique and match the verification pattern `^[a-z0-9][a-z0-9.-]*$`. It is used for verification; the generated RKE2 configuration does not set `node-name`. With a host limit, explicitly map inventory nodes outside the selection as well: final verification covers all inventory nodes, while hostname discovery runs only on selected nodes.
- `ansible_host`, `ansible_user`, and standard Ansible SSH/become variables select remote access. Use Key Store/Vault for credentials. Root operations require working escalation.
- Preparation play variables: `prepare_nodes_common_packages` defaults to conntrack, curl, ebtables, e2fsprogs, ethtool, iproute2, iptables, socat, util-linux, xfsprogs; `prepare_nodes_worker_packages` adds nfs-common/open-iscsi; `prepare_nodes_kernel_modules` defaults to overlay/br_netfilter (workers also get iscsi_tcp). `prepare_nodes_network_manager_conf` defaults to `/etc/NetworkManager/conf.d/99-carekube-rke2-cni.conf`; `prepare_nodes_longhorn_mount` derives from `prerequisites_longhorn_data_path`. These are play-level settings, not a general supported-layout abstraction.

Endpoint items require `host` and `port`, and accept optional `name` (report label; defaults to host), `tls` (false), and `timeout` (5 seconds). Values are trusted shell inputs: use only administrator-approved hosts, numeric ports/timeouts, and no shell metacharacters. TLS checks test handshake completion without strict certificate validation; they do not establish peer identity or application access.

## Ansible configuration and environment

| Setting in ansible.cfg | Default | Purpose |
|------------------------|---------|---------|
| local_tmp | `/tmp/ansible-semaphore-local` | Private per-process controller scratch directories. |
| filter_plugins | `./filter_plugins` | Custom state filters. |
| library | `./library` | Read-only removal module. |
| inventory | `inventories/lab/hosts.yml` | Default inventory. |
| host_key_checking | `True` | Verify SSH host keys. |
| retry_files_enabled | `False` | Disable retry file creation. |
| interpreter_python | `auto_silent` | Target Python discovery. |
| stdout_callback | `ansible.posix.debug` | Multiline reports; requires collection. |

`ANSIBLE_LOCAL_TEMP` overrides controller scratch space. `HOME` on the controller supplies default persistent credential destinations. Controller staging evaluates `id -u`. Standard Ansible environment settings remain available; this repository defines no custom environment-variable parser. `INSTALL_RKE2_VERSION` and `INSTALL_RKE2_TYPE` are set internally for the installer; removal sets `RKE2_DATA_DIR` and `INSTALL_RKE2_ROOT` internally. They are not alternate repository configuration inputs.

## Controller execution

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

## Example extra variables

Save non-secret environment settings outside tracked inventory defaults and pass the file with `-e @/path/to/environment.yml`:

```yaml
rke2_bootstrap_node: cp-1
rke2_api_endpoint: 192.0.2.10
rke2_registration_endpoint: 192.0.2.20
rke2_tls_sans:
  - api.example.invalid
```

`cp-1` must be in the selected inventory control-plane group. These are illustrative addresses, not working lab settings. Keep tokens in Vault or protected Semaphore variables. Never persist removal authorization in inventory or a shared environment file.

CLI flags and input/output contracts are in [Api](Api.md). Runtime `set_fact` names such as readiness flags, selected source, expected configuration, and parsed diagnostic records are implementation state, not supported configuration options.
