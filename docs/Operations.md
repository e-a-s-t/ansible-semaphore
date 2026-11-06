# Operations

## Deployment and dependencies

Semaphore itself and target VMs are provisioned outside this repository. Configure controller dependencies and independent repository/target SSH keys using [Usage](Usage.md). The provided lab has one control plane and one worker; it provides no control-plane redundancy. Backup infrastructure has an inventory role but no backup-service deployment playbook.

Run the four setup stages described in Usage. Targets need SSH, Python, apt repositories, systemd, and access to the upstream RKE2 installer and artifacts for fresh installs. The API endpoint and registration endpoint can differ; an external VIP/load balancer is supplied by infrastructure, not created here. Reachability probes are not application health or authorization checks.

## Monitoring and health

Use Ansible/Semaphore task logs and recaps for per-host failures and readiness reports. There is no repository-managed monitoring stack, dashboard, alerting, or HTTP health endpoint. Installation checks registered Kubernetes node readiness/version and reads kubeconfig on the selected control plane. It does not establish full Cilium, storage, workload, or disaster-recovery health.

On a server, inspect `sudo systemctl status rke2-server` and `sudo journalctl -u rke2-server`; on a worker use `rke2-agent`. Treat service logs as potentially sensitive. A matching configuration is preserved even when its service is stopped. Final verification directly queries the expected systemd unit on every targeted node and requires `LoadState=loaded`, `ActiveState=active`, and `UnitFileState=enabled`, using the bounded final-verification retry settings. Failure blocks Kubernetes verification and kubeconfig extraction; investigate service health rather than expecting a rerun to restart or enable a preserved service. Reports use these independently observed properties, not cached service facts or a fallback to the other role's unit. Check mode observes once without enforcing readiness.

## Backups and upgrades

The playbook writes a token recovery copy and admin kubeconfig on the controller with protected permissions. Store these in encrypted backups together with securely captured server configuration and appropriate etcd snapshots. Backup scheduling, offsite storage, snapshot restore, and recovery validation are operator responsibilities; no automated backup/restore workflow exists here. A token copy alone is not a cluster backup.

There is no automated version upgrade or downgrade workflow. Changing the version or managed settings on existing nodes triggers drift refusal. Plan changes separately, preserve recovery artifacts, and validate compatibility before maintenance. Do not use removal as an in-place upgrade.

## Reruns and expansion

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

## Final verification and ingress migration

Fresh v1.37 installations retain Cilium, CoreDNS, metrics-server, the snapshot
components and the standalone `rke2-gateway-api-crd` chart. All managed servers
use `ingress-controller: none`; no ingress or gateway implementation is installed
by this playbook. Disabling only `rke2-ingress-nginx` does not disable the v1.37
Traefik default. These component expectations follow the pinned release configuration; inspect the actual installed charts before migration. Retained upstream references: [RKE2 networking](https://docs.rke2.io/networking/networking_services) and [server configuration](https://docs.rke2.io/reference/server_config).

Final verification runs directly as root on the selected inventory control-plane
host, retaining that host's SSH settings. `rke2_token_source_node` selects an
alternative healthy control plane (include it in the host limit). The API JSON
must contain every inventory node, Ready, at exactly `rke2_version`; extra nodes
do not substitute for missing nodes. Set `rke2_node_name` for aliases or custom
node names. Otherwise the remote hostname is used. The lab mappings are
`basel-rke2-1` → `basel-rke2-01` and `basel-rke2-2` → `basel-rke2-02`.
When limiting expansion, supply `rke2_node_name` for inventory nodes outside the selection too; their hostnames are not discovered during that run. Retries allow registration to converge. Failure diagnostics report only expected
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

The standard RKE2 server and agent service units reference three optional
environment files per service: `/etc/default/rke2-server` (or `rke2-agent`),
`/etc/sysconfig/rke2-server` (or `rke2-agent`), and
`/usr/local/lib/systemd/system/rke2-server.env` (or `rke2-agent.env`). These
references come from the upstream tarball units installed by `install-rke2.yml`;
our playbook does not create the files itself. A reference in `systemctl show`
does not mean the optional file exists. Missing optional files are accepted.
Existing files must be regular, root-owned, not group/world-writable, and have
no symlink in their path. They are inspected as data, never sourced or executed.
Unexpected paths, missing required files, malformed contents, and runtime-path
overrides remain blocked. Recognized files are included in cleanup and absence
verification. Environment refusals report the service, a bounded escaped file
path, and a fixed reason such as `unexpected_path`, `symlink_path`, or
`runtime_path_override`; environment values and credentials are never logged.

Removal deletes RKE2 services, installation artifacts, configuration, certificates,
credentials, embedded etcd, and owned runtime/CNI state. It preserves OS preparation,
prerequisite packages, iSCSI, modules, sysctls, swap settings, SSH, dedicated disks,
and `/var/lib/longhorn` with its persistent mount configuration. Disk identity,
Longhorn mounts, and `/etc/fstab` are compared before and after cleanup. No disks
are formatted or partitioned. Preserving Longhorn storage does not automatically
restore its Kubernetes resources or recover volumes into a rebuilt cluster.

Runtime cleanup is independently verified rather than inferred from the official
script's exit code. The remover retries the installed official cleanup script up
to `rke2_remove_cleanup_attempts` times (default **3**), with
`rke2_remove_cleanup_delay` seconds between attempts (default **3**). Attempts must
be a positive integer and delay a nonnegative integer. Each attempt revalidates
ownership and compares protected storage against the original snapshot. A script
failure, changed storage, or changed safety conditions stops retries immediately.
Check mode performs no retries or script execution.

Mount diagnostics contain only bounded, escaped targets, filesystem types, and
classifications: `runtime`, `protected_longhorn`, `persistent_storage`, or
`unknown_mount`. They omit mount sources, options, and credential values. The
filesystem at `/var/lib/longhorn` and its descendants are explicitly protected;
these targets are never automatically unmounted or deleted. A pod volume bind
mount beneath a cleanup directory still blocks deletion even when backed by
Longhorn. Unknown or persistent mounts in deletion paths are refused, not treated
as removable runtime state. Unrelated mounts outside deletion paths are untouched.

The exact `/run/cilium/cgroupv2` mount with filesystem type `cgroup2` is recognized
as expected runtime state during preflight only when RKE2 runtime ownership and
trusted Cilium CNI evidence are present. Evidence must be a supported
`05-cilium.conf` or `05-cilium.conflist` containing a valid `cilium-cni` plugin,
with a regular root-owned file, no group/world write permissions, and no symlink
in its path. Other mounts under `/run/cilium` and unrelated `cgroup2` mounts do
not gain runtime classification. Recognition does not exempt the Cilium mount
from cleanup guards. After official cleanup, a sole residual recognized Cilium
mount is released with normal `umount /run/cilium/cgroupv2`, only after fresh
inspection confirms safe ownership, stopped RKE2 services, no relevant runtime
processes, and unchanged protected storage. No additional official cleanup
attempt is made for this residual mount. An absent mount needs no unmount.
A failed or busy unmount stops safely with sanitized diagnostics. Independent
inspection must confirm the mount is gone and protected storage is unchanged
before uninstall or recursive cleanup. Command success alone is insufficient.

Remaining runtime processes or mounts after bounded cleanup produce `INCOMPLETE`.
No uninstall or fallback recursive deletion proceeds while any mounted cleanup
path remains, and a worker failure prevents control-plane teardown. Mount safety
is checked afresh immediately before uninstall and before fallback file cleanup.
There is no generic, forced, or lazy unmount fallback. If the failure persists,
review the reported targets and types before operator recovery; do not bypass the
guard. A previous attempt that stopped services and ran runtime cleanup can be
rerun with the same full inventory and explicit authorization. Recognized stopped
installations resume cleanup without restarting services; removed nodes report
`ABSENT`. Installation and node preparation do not need to be rerun for recovery.

A node reports `REMOVED` only after independent verification. An already removed
node reports `ABSENT`; uninstall errors or remaining artifacts/storage changes
produce `INCOMPLETE` and fail the run. After successful removal, run **4. Install
RKE2** again on the prepared machines without recreating VMs or reinstalling the OS.

Controller-side token backups (`rke2_token_backup_path`) and kubeconfigs
(`rke2_kubeconfig_path`) are preserved for audit and recovery. These credentials
may no longer work after rebuilding. Archive them securely before reinstalling,
since installation writes the current cluster credentials to those paths.

## Failure triage

| Symptom | Action |
|---------|--------|
| SSH checkout/connection failure | Check the independent keys, inventory username/address, trusted host keys, and network from the execution environment. |
| Prerequisites `INCOMPLETE` | Resolve missing or ambiguous mandatory infrastructure evidence; inspect the complete report. |
| Artifact probe failure | Check the pinned release and target access to checksum/tarball URLs; probes do not install anything. |
| Drift or inspection error | Review sanitized differing keys and protected source files; do not delete data or recreate markers to bypass validation. |
| Token backup/controller staging failure | Check process-user permissions, persistent paths, and configured scratch directories. |
| Missing/not-Ready/version-mismatched node | Check node name mappings, services, network, version, and registration; extra nodes do not replace missing ones. |
| Removal `INCOMPLETE` | Inspect sanitized mount/storage/environment diagnostics and resolve the cause before a full-scope authorized retry. Previously removed nodes remain removed. |

See [Configuration](Configuration.md), [Security](Security.md), and [test coverage](Testcases.md).

## Agent restart troubleshooting

Use [the single-worker restart workflow](Usage.md#restart-one-rke2-agent) when an explicit agent restart is needed. Selection failures require correcting `target_host`, inventory role membership, or the CLI/Semaphore host limit. A systemd or SSH/become failure is reported as a failed run; investigate target access and `sudo systemctl status rke2-agent` / `sudo journalctl -u rke2-agent` before retrying. Each retry requests another restart.

After a successful restart, independently check Kubernetes node readiness and affected workload/storage health using your cluster credentials. This playbook does not perform those checks, drain/uncordon nodes, or promise recovery. No live restart validation is included in the offline suite.
