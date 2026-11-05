# Architecture decision records

These records reconstruct decisions visible in the current implementation. Status describes implemented behavior, not evidence of a historical approval meeting. Dates and original rationale are unknown unless explicitly established; context below explains the observed design constraint. See [Requirements](Requirements.md), [Architecture](Architecture.md), and [Operations](Operations.md).

## ADR-001: Separate lifecycle playbooks

- Date: Unknown.
- Status: Implemented; reconstructed from repository evidence.
- Requirements: [REQ-001](Requirements.md#req-001), [REQ-002](Requirements.md#req-002), [REQ-003](Requirements.md#req-003), [REQ-005](Requirements.md#req-005).
- Context: Connectivity/validation need different privileges and effects from node preparation and installation.
- Decision: Keep the five lifecycle entry points independently runnable.
- Consequences: Operators must sequence stages; there is no transactional orchestration of the full lifecycle.
- Evidence: [implementation](../playbooks/connectivity.yml).

## ADR-002: Explicit bootstrap and distinct endpoints

- Date: Unknown.
- Status: Implemented; reconstructed from repository evidence.
- Requirements: [REQ-005](Requirements.md#req-005).
- Context: Inventory order must not determine cluster initialization; client and join traffic may use different endpoints.
- Decision: Select bootstrap by name; only it receives cluster-init. Joining nodes use the registration endpoint while kubeconfig uses the API endpoint.
- Consequences: Infrastructure supplies addresses/VIPs and correct SANs; existing state is preserved.
- Evidence: [implementation](../playbooks/install-rke2.yml).

## ADR-003: Fail closed on drift and cluster readiness

- Date: Unknown.
- Status: Implemented; reconstructed from repository evidence.
- Requirements: [REQ-006](Requirements.md#req-006).
- Context: A failed host can disappear from later Ansible plays, and existing data must not be silently reconciled.
- Decision: Freeze selected targets, require readiness facts, classify managed fields/version, and refuse ambiguous/drifted installs.
- Consequences: Expansion includes the selected token source; version/configuration changes require separate operator procedures.
- Evidence: [implementation](../tasks/rke2-barrier.yml).

## ADR-004: Protect controller credential handling

- Date: Unknown.
- Status: Implemented; reconstructed from repository evidence.
- Requirements: [REQ-007](Requirements.md#req-007), [REQ-008](Requirements.md#req-008).
- Context: Token reuse and kubeconfig extraction cross the target/controller privilege boundary.
- Decision: Read existing tokens with hidden logging, back up before joining, and write credentials locally without controller become.
- Consequences: Controller needs writable persistent storage and externally secured backups; credentials are not encrypted by these tasks.
- Evidence: [implementation](../tasks/rke2-token.yml).

## ADR-005: Guard full-cluster removal and preserve storage

- Date: Unknown.
- Status: Implemented; reconstructed from repository evidence.
- Requirements: [REQ-009](Requirements.md#req-009), [REQ-010](Requirements.md#req-010), [REQ-011](Requirements.md#req-011).
- Context: Cleanup can destroy etcd, credentials, shared runtime state, or mounted data.
- Decision: Require explicit execution authorization and complete scope; inspect ownership, run workers first/bootstrap last, and independently guard cleanup mounts/storage.
- Consequences: Only supported standard layouts are removed; failure leaves partial teardown for operator recovery.
- Evidence: [implementation](../playbooks/remove-rke2.yml).

## ADR-006: Deploy no bundled ingress implementation

- Date: Unknown.
- Status: Implemented; reconstructed from repository evidence.
- Requirements: [REQ-005](Requirements.md#req-005), [REQ-006](Requirements.md#req-006).
- Context: The pinned release defaults require an explicit server ingress setting; existing configurations must not be migrated implicitly.
- Decision: Render ingress-controller none for new managed servers and treat existing differences as drift.
- Consequences: Ingress is an external platform concern; existing Traefik installations require the manual migration procedure.
- Evidence: [implementation](../vars/rke2.yml).
