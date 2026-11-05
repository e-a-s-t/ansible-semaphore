# Security

## Implemented boundaries

SSH authenticates remote Ansible operations. `ansible.cfg` enables host-key checking. Connectivity and prerequisites default to no escalation; preparation, installation, and removal enable become on nodes. Controller tasks force a local connection and disable become so they run as the Semaphore process user. The repository does not implement Semaphore login, project permissions, audit retention, or Kubernetes RBAC policy.

Separate repository and target SSH keys are the documented Semaphore setup. Key provisioning and rotation are operator responsibilities. No passwords/private keys are intentionally tracked. `.gitignore` excludes common key and environment files but is not a secret scanner.

## Credentials and logs

Token/config reads and credential writes use `no_log`. Target configuration/markers and controller token/kubeconfig files use `0600`; protected controller parent directories use `0700`. Existing tokens are read and preserved rather than automatically rotated. Removal preserves controller credentials, which can become stale after rebuilding.

Installer error diagnostics apply pattern-based redaction and length limits. Node verification returns only allowlisted failure categories and expected node identities. Removal diagnostics bound and escape paths, omit environment contents and mount sources/options, and expose fixed refusal reasons. These controls do not promise arbitrary secret removal from every possible tool output. In particular, prerequisite runtime evidence includes executable/command-line information; review log access and avoid putting secrets in process arguments.

Permissions do not encrypt credentials. Encrypted controller backups, secure Semaphore variable storage or Ansible Vault, restricted task/log access, and independent key rotation are operational recommendations. They are not implemented encryption or rotation services. Never commit tokens, kubeconfigs, private keys, or destructive authorization.

## Network and supply chain

Targets obtain the upstream installer over HTTPS and execute it; artifacts are pinned to a configured RKE2 version. Preflight checks artifact HTTP availability, not an independent repository-implemented signature verification system. The installer/release hosts, OS package sources, trusted administrators, and controller environment are trust dependencies.

Prerequisite endpoints are opt-in. DNS/TCP/TLS probes do not prove application authorization. The TLS probe uses `openssl s_client` without strict certificate-verification enforcement; success does not prove trusted peer identity. The repository provisions no firewall, network policy, load balancer, or ingress/gateway implementation. RKE2-managed Cilium is configured but its security policy is not defined here.

## Input validation and destructive actions

Role exclusivity, bootstrap membership, selected-source readiness, positive ports, version shape, and Cilium choice are checked. Parsing uses safe YAML loading and JSON parsing; malformed state is refused with sanitized errors. Comparison validates selected managed fields, not all possible RKE2 configuration or independent cluster provenance.

Preparation rejects used/ambiguous disks and rechecks device identity before formatting. Removal requires native true or exact case-insensitive string true, full-cluster scope, remote targets, supported paths and verified ownership. It rejects foreign Kubernetes/shared CNI, unsafe symlinks, custom runtime layouts, unsupported service overrides, and unsafe environment files. Files are inspected as data rather than sourced.

Official cleanup scripts require trusted root ownership and permissions. Runtime cleanup is bounded; independent process/mount/storage checks block recursive deletion until runtime shutdown is verified. Unknown/persistent mounts are refused; the Longhorn target tree is protected. Confirmation cannot bypass safety checks. These are software safeguards, not a sandbox around a compromised root host or upstream script.

## Threat scenarios and assumptions

| Scenario | Implemented response | Remaining assumption/limitation |
|----------|----------------------|--------------------------------|
| Wrong task key or untrusted SSH host | Independent key setup and host-key checking | Execution environment must have correct trusted keys. |
| Failed preflight host omitted from later Ansible plays | Frozen target/readiness barriers | Controller inventory/configuration is trusted. |
| Credential retrieval or backup fails | Readiness invalidated; joins/final operations blocked | Host/controller secrets remain accessible to privileged administrators. |
| Shared runtime or persistent volume beneath cleanup paths | Ownership and mount guards; refuse unsafe deletion | Host diagnostics and root are trusted; external scripts can have side effects. |
| Disk changes between inspection and formatting | Immediate identity/safety revalidation | No atomic lock against concurrent external storage changes. |
| Malicious extra variables/endpoints | Some fields quoted/validated; diagnostics hidden | Variables are trusted executable configuration, not safe untrusted input. |

There is no dedicated vulnerability reporting policy, automated security scan, live isolation test suite, or security certification in this repository. [Testcases](Testcases.md) identifies implemented security regressions; [Roadmap](Roadmap.md) separates proposed improvements from current protections.
