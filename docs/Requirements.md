# Requirements

## Purpose and scope

Provide repeatable Ansible workflows for checking Linux hosts, preparing Carekube nodes, installing/preserving RKE2, and removing a complete cluster for rebuilds. Semaphore is an execution environment; this repository does not implement its web application. Requirements below describe observable repository behavior, not an independently approved product specification.

## Functional requirements

Stable identifiers are shared with [architecture decisions](Adr.md) and [test cases](Testcases.md). Implemented means code exists; it does not claim live-environment certification.

| ID | Requirement | Status | Evidence | Verification |
|----|-------------|--------|----------|--------------|
| <a id="req-001"></a>REQ-001 | Verify SSH/Ansible connectivity and report basic host facts without escalation. | Implemented | [connectivity](../playbooks/connectivity.yml) | [TC-001](Testcases.md#tc-001) |
| <a id="req-002"></a>REQ-002 | Validate exclusive roles and role-specific infrastructure requirements; report confirmed blockers separately from unavailable evidence and deferred installation settings. | Implemented | [prerequisites](../playbooks/prerequisites.yml) | [TC-002](Testcases.md#tc-002) |
| <a id="req-003"></a>REQ-003 | Prepare supported OS packages, swap, modules, sysctls, NetworkManager exclusions, and worker iSCSI. | Implemented | [preparation](../playbooks/prepare-nodes.yml) | [TC-003](Testcases.md#tc-003), [TC-019](Testcases.md#tc-019) |
| <a id="req-004"></a>REQ-004 | Prepare dedicated worker storage only after safety/identity checks and preserve valid existing mounts. | Implemented | Preparation and shared storage tasks | [TC-003](Testcases.md#tc-003), [TC-019](Testcases.md#tc-019) |
| <a id="req-005"></a>REQ-005 | Bootstrap an explicitly selected RKE2 server and join additional servers/workers using distinct API/registration settings. | Implemented | [installation](../playbooks/install-rke2.yml) | [TC-004](Testcases.md#tc-004), [TC-011](Testcases.md#tc-011), [TC-020](Testcases.md#tc-020) |
| <a id="req-006"></a>REQ-006 | Preserve matching installs, refuse managed drift/uncertain state, and block mutation when any selected preflight dependency fails. | Implemented | Classification and cluster barriers | [TC-005](Testcases.md#tc-005), [TC-006](Testcases.md#tc-006), [TC-007](Testcases.md#tc-007), [TC-011](Testcases.md#tc-011), [TC-020](Testcases.md#tc-020) |
| <a id="req-007"></a>REQ-007 | Acquire the existing cluster token without rotation, back it up securely, and run controller tasks as the process user. | Implemented | Token/controller tasks | [TC-008](Testcases.md#tc-008), [TC-009](Testcases.md#tc-009) |
| <a id="req-008"></a>REQ-008 | Verify every inventory Kubernetes node is Ready at the configured version and save a protected external-endpoint kubeconfig. | Implemented | Verification tasks | [TC-009](Testcases.md#tc-009), [TC-010](Testcases.md#tc-010), [TC-020](Testcases.md#tc-020) |
| <a id="req-009"></a>REQ-009 | Remove only a fully selected, explicitly authorized cluster in worker/server/bootstrap order with independent absence verification. | Implemented | [removal](../playbooks/remove-rke2.yml) | [TC-012](Testcases.md#tc-012), [TC-013](Testcases.md#tc-013), [TC-016](Testcases.md#tc-016), [TC-020](Testcases.md#tc-020) |
| <a id="req-010"></a>REQ-010 | Preserve Longhorn storage and OS preparation during removal; refuse unsafe ownership, paths, environments, and mounted cleanup state. | Implemented | Removal inspector and guards | [TC-014](Testcases.md#tc-014), [TC-015](Testcases.md#tc-015), [TC-016](Testcases.md#tc-016), [TC-017](Testcases.md#tc-017), [TC-020](Testcases.md#tc-020) |
| <a id="req-011"></a>REQ-011 | Offer inspection/reporting check mode for RKE2 install/removal without install or cleanup execution. | Implemented | Explicit check-mode guards; still contacts targets | [TC-018](Testcases.md#tc-018) |
| <a id="req-012"></a>REQ-012 | Validate platform readiness including Cilium/Longhorn dependencies and configured endpoints. | Partially implemented | Local evidence and optional DNS/TCP/TLS probes; runtime/network/application health is incomplete | [TC-021](Testcases.md#tc-021) |

## Non-functional requirements and technical constraints

Safety is fail-closed at installation/removal barriers, with bounded runtime cleanup and sanitized diagnostics. Operations are not transactional: earlier preparation changes or removed nodes persist after failure. Rerun preservation applies to matching managed settings; it is not general upgrade reconciliation. Secret files use restrictive permissions, not encryption at rest. See [Security](Security.md).

There are no documented availability/latency SLOs, performance benchmarks, or measured coverage targets. None are introduced here. Proposed capabilities belong in [Roadmap](Roadmap.md), not approved requirements.

## Dependencies and environments

- Controller: Ansible, Python, `ansible.posix`, SSH access and writable scratch/persistent credential paths. Python tests need Ansible and PyYAML in the same interpreter environment. Versions are not pinned by a dependency manifest.
- Targets: Python, SSH, Linux utilities and systemd. Preparation uses apt and explicitly accepts Ubuntu 24.04 or Debian 13; prerequisite validation warns on other distributions. Installation artifacts are Linux AMD64 only.
- Fresh installation: target access to installer/release artifacts and package sources. Networking, DNS/time, resources, disks, endpoint/VIP provisioning and access permissions are infrastructure responsibilities.
- Inventory: exactly one role among `control_plane`, `worker`, `backup` for validation/preparation. RKE2 operations concern control planes/workers. The supplied lab inventory contains one server and one worker.

Production resource thresholds and lab overrides are documented in [Configuration](Configuration.md). A validation profile labels the report; the override mapping actually changes resource thresholds.

## Known limitations

No VM provisioning, Semaphore deployment, Longhorn deployment, backup-service deployment, automated cluster restore/upgrade, ingress implementation, CI pipeline, or live end-to-end suite exists here. Removal supports standard paths/layout only. Endpoint probes do not prove authorization or TLS peer trust. See [Roadmap](Roadmap.md) for gaps and [Testcases](Testcases.md) for verification limits.
