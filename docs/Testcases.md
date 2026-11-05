# Test cases

## Strategy and execution

Run the exact commands in [Development](Development.md#offline-regression-checks). Python `unittest` covers filters, removal inspection, and local orchestration. YAML tests exercise production task includes and modeled decision expressions. Security-related tests cover secrets in diagnostics, foreign state, unsafe files/mounts, confirmation and readiness barriers. No live end-to-end suite, benchmark, coverage report, or CI runner is checked in.

Implemented means an automated test exists, not that the feature has live coverage. Preconditions below refer to local fixtures unless explicitly marked missing. Missing scenarios are proposed verification work and must not be run against shared infrastructure without separate authorization. Each case maps to [Requirements](Requirements.md); architectural rationale is in [Adr](Adr.md).

## Cases

### TC-001

ID: TC-001\
Title: Connectivity and host facts\
Requirement: [REQ-001](Requirements.md#req-001)\
Preconditions: A reachable test Linux node and independent SSH key.\
Steps: Run connectivity playbook against the test node.\
Expected result: Ping succeeds before facts and basic host information are printed without escalation.\
Status: Missing

Evidence / coverage boundary: No dedicated automated connectivity test exists.

### TC-002

ID: TC-002\
Title: Numeric prerequisite evidence and profile thresholds\
Requirement: [REQ-002](Requirements.md#req-002)\
Preconditions: Local fixture execution environment.\
Steps: Run tests/prerequisites_numeric.yml.\
Expected result: Fixture assertions distinguish valid/invalid numeric evidence, resource profiles, readiness and report categories.\
Status: Implemented

Evidence / coverage boundary: [numeric fixtures](../tests/prerequisites_numeric.yml); largely modeled expressions rather than full remote validation.

### TC-003

ID: TC-003\
Title: Preparation decisions and storage selection\
Requirement: [REQ-003](Requirements.md#req-003), [REQ-004](Requirements.md#req-004)\
Preconditions: Local Ansible environment; no real disks.\
Steps: Run tests/prepare_nodes.yml.\
Expected result: Role/package decisions, existing mounts, rejected/ambiguous disks, shared storage selection, and report expressions satisfy fixture assertions.\
Status: Implemented

Evidence / coverage boundary: [preparation fixtures](../tests/prepare_nodes.yml); modeled preparation plus shared production storage tasks, not live formatting.

### TC-004

ID: TC-004\
Title: Bootstrap and endpoint decision models\
Requirement: [REQ-005](Requirements.md#req-005)\
Preconditions: Local Ansible environment.\
Steps: Run tests/install_rke2.yml.\
Expected result: Explicit bootstrap, separate endpoints, bootstrap-only initialization, pinned artifact URLs, token reuse and diagnostic redaction match modeled expectations.\
Status: Implemented

Evidence / coverage boundary: [installation fixtures](../tests/install_rke2.yml); modeled decisions do not prove a real cluster installs.

### TC-005

ID: TC-005\
Title: Matching rerun and managed drift\
Requirement: [REQ-006](Requirements.md#req-006)\
Preconditions: Python with Ansible and PyYAML.\
Steps: Run ClassificationTests using unittest discovery.\
Expected result: Matching bootstrap reruns remain matching, unordered managed lists compare consistently, and version/configuration drift is detected.\
Status: Implemented

Evidence / coverage boundary: [ClassificationTests](../tests/test_rke2_state.py): test_successful_bootstrap_and_rerun, test_production_bootstrap_template_rerun, test_actual_drift.

### TC-006

ID: TC-006\
Title: Malformed and ambiguous existing state\
Requirement: [REQ-006](Requirements.md#req-006)\
Preconditions: Classification fixtures.\
Steps: Run ClassificationTests.\
Expected result: Unreadable/malformed inputs yield sanitized inspection errors; binary-only partial installs differ from ambiguous data-bearing states.\
Status: Implemented

Evidence / coverage boundary: [state tests](../tests/test_rke2_state.py): test_inspection_errors_are_sanitized, test_unreadable_config_fails_without_values, test_partial_and_ambiguous_state.

### TC-007

ID: TC-007\
Title: Frozen targets and failed host barriers\
Requirement: [REQ-006](Requirements.md#req-006)\
Preconditions: Local multi-host fixture and ansible-playbook executable.\
Steps: Run ClusterFailureTests and tests/rke2_barriers.yml.\
Expected result: Failed hosts remain blocking dependencies; excluded source limits are rejected; an explicitly selected healthy alternate source can be used.\
Status: Implemented

Evidence / coverage boundary: [cluster failure tests](../tests/test_rke2_cluster_failure.py), [production barrier exercises](../tests/rke2_barriers.yml).

### TC-008

ID: TC-008\
Title: Credential validation and rerun classification\
Requirement: [REQ-007](Requirements.md#req-007)\
Preconditions: Local fixture token values only.\
Steps: Run tests/rke2_credentials.yml.\
Expected result: Empty/multiline/failed-read credentials are rejected; valid fixture token passes; repeated production classification remains matching.\
Status: Implemented

Evidence / coverage boundary: [credential fixtures](../tests/rke2_credentials.yml) include production validation tasks.

### TC-009

ID: TC-009\
Title: Controller connection and credential failure gating\
Requirement: [REQ-007](Requirements.md#req-007), [REQ-008](Requirements.md#req-008)\
Preconditions: Temporary local files and simulated target credential reads.\
Steps: Run ControllerTests.\
Expected result: Controller stays local and unprivileged, credential permissions are checked, and failed acquisition/installation blocks final operations.\
Status: Implemented

Evidence / coverage boundary: [ControllerTests](../tests/test_rke2_controller.py): test_controller_connection_and_protected_storage, test_failed_token_acquisition_blocks_final_operations, test_failed_installation_blocks_final_operations.

### TC-010

ID: TC-010\
Title: Expected Kubernetes nodes and kubeconfig rerun\
Requirement: [REQ-008](Requirements.md#req-008)\
Preconditions: Fixture Kubernetes JSON and temporary kubeconfig.\
Steps: Run VerificationTests.\
Expected result: Missing/not-ready/version-mismatched nodes fail; verification uses selected target context and unchanged kubeconfig extraction is idempotent.\
Status: Implemented

Evidence / coverage boundary: [VerificationTests](../tests/test_rke2_verification.py): test_node_validation, test_direct_context_and_kubeconfig_rerun.

### TC-011

ID: TC-011\
Title: Ingress configuration drift\
Requirement: [REQ-005](Requirements.md#req-005), [REQ-006](Requirements.md#req-006)\
Preconditions: Server/worker configuration fixtures.\
Steps: Run VerificationTests.\
Expected result: Fresh servers specify no ingress; legacy Traefik differs from none; workers ignore server-only ingress comparison.\
Status: Implemented

Evidence / coverage boundary: [verification tests](../tests/test_rke2_verification.py): test_ingress_drift_and_fresh_configuration, test_worker_ignores_server_ingress_setting.

### TC-012

ID: TC-012\
Title: Removal authorization and full scope\
Requirement: [REQ-009](Requirements.md#req-009)\
Preconditions: Simulated removal orchestration.\
Steps: Run OrchestrationTests.\
Expected result: Only supported true values authorize; partial scope, invalid bootstrap, overlapping roles, unsafe nodes, and unreachable preflight block mutation.\
Status: Implemented

Evidence / coverage boundary: [removal tests](../tests/test_rke2_removal.py): test_accepted_confirmation_values, test_rejected_confirmation_values, test_partial_scope_and_invalid_bootstrap, test_unreachable_preflight_blocks_mutation.

### TC-013

ID: TC-013\
Title: Removal ordering and independent results\
Requirement: [REQ-009](Requirements.md#req-009)\
Preconditions: Fixture action plugins replace cleanup.\
Steps: Run OrchestrationTests.\
Expected result: Workers precede other servers/bootstrap; absent nodes are no-ops; failed uninstall/verification stops later nodes.\
Status: Implemented

Evidence / coverage boundary: [removal tests](../tests/test_rke2_removal.py): test_full_cluster_order, test_absent_is_noop, test_uninstall_and_verification_failures_stop_later_nodes.

### TC-014

ID: TC-014\
Title: Unsafe environment files and secret diagnostics\
Requirement: [REQ-010](Requirements.md#req-010)\
Preconditions: Temporary file tree and simulated systemctl data.\
Steps: Run InspectionTests and OrchestrationTests.\
Expected result: Optional missing files pass; unexpected paths, symlinks, unsafe permissions/content and runtime overrides are refused without exposing values.\
Status: Implemented

Evidence / coverage boundary: [removal tests](../tests/test_rke2_removal.py): test_standard_server_and_agent_environment_files, test_environment_unsafe_contents_never_leak_values, test_diagnostic_paths_are_bounded_escaped_and_redacted, test_environment_diagnostics_and_failure_barriers.

### TC-015

ID: TC-015\
Title: Foreign state and storage boundaries\
Requirement: [REQ-010](Requirements.md#req-010)\
Preconditions: Fake disk/mount/runtime evidence.\
Steps: Run InspectionTests.\
Expected result: Foreign/shared state and unsupported paths fail; protected Longhorn tree is distinguished from blocking pod bind mounts.\
Status: Implemented

Evidence / coverage boundary: [removal tests](../tests/test_rke2_removal.py): test_foreign_runtime_and_cni_even_with_rke2, test_custom_paths_and_symlinks_rejected, test_longhorn_filesystem_is_protected_but_pod_bind_mount_is_blocking.

### TC-016

ID: TC-016\
Title: Bounded cleanup retries and interrupted removal\
Requirement: [REQ-009](Requirements.md#req-009), [REQ-010](Requirements.md#req-010)\
Preconditions: Simulated official scripts and mount/process transitions.\
Steps: Run OrchestrationTests and InspectionTests.\
Expected result: Transient runtime state can clear; persistent mounts exhaust bounded retries without uninstall; script/safety changes stop retries; recognized stopped installs can resume.\
Status: Implemented

Evidence / coverage boundary: [removal tests](../tests/test_rke2_removal.py): test_transient_mounts_and_processes_clear_on_retry, test_persistent_runtime_mounts_exhaust_bound_without_uninstalling, test_script_failure_and_changed_safety_abort_retries, test_interrupted_removal_with_stopped_services_remains_recognizable.

### TC-017

ID: TC-017\
Title: Exact trusted Cilium cgroup recognition\
Requirement: [REQ-010](Requirements.md#req-010)\
Preconditions: Trusted/untrusted CNI and mount fixtures.\
Steps: Run removal inspection and orchestration tests.\
Expected result: Only exact owned cgroup2 runtime state is recognized; it still must disappear before deletion; persistent failure blocks uninstall.\
Status: Implemented

Evidence / coverage boundary: [removal tests](../tests/test_rke2_removal.py): test_cilium_cgroup_requires_trusted_cni_evidence, test_cgroup_mount_recognition_is_exact_and_requires_rke2_ownership, test_residual_cilium_unmount_and_worker_order, test_absent_cilium_mount_needs_no_unmount, test_cilium_unmount_refusals_and_verification_failures, test_service_shutdown_and_cilium_process_detection.

### TC-018

ID: TC-018\
Title: Check-mode suppression\
Requirement: [REQ-011](Requirements.md#req-011)\
Preconditions: Local fixtures; check flag supplied to token test.\
Steps: Run tests/rke2_check_mode.yml --check and Python removal tests.\
Expected result: Token acquisition/transfer and destructive cleanup are suppressed; removal reports inspection outcome without mutation.\
Status: Implemented

Evidence / coverage boundary: [check-mode fixture](../tests/rke2_check_mode.yml), [removal tests](../tests/test_rke2_removal.py): test_check_mode_no_mutation, test_production_mutation_is_explicitly_check_guarded.

### TC-019

ID: TC-019\
Title: Live preparation and idempotence\
Requirement: [REQ-003](Requirements.md#req-003), [REQ-004](Requirements.md#req-004)\
Preconditions: Disposable supported Linux VMs, isolated dedicated disks and recovery access.\
Steps: In a separately authorized lab, prepare nodes twice and inspect actual packages, services, disk identity, filesystem and fstab.\
Expected result: Second execution preserves data/mount identity; rejected disk cases never format storage.\
Status: Missing

Evidence / coverage boundary: No live disk/OS integration harness exists; local modeled assertions do not cover real utilities or races.

### TC-020

ID: TC-020\
Title: Live install expansion and rebuild\
Requirement: [REQ-005](Requirements.md#req-005), [REQ-006](Requirements.md#req-006), [REQ-008](Requirements.md#req-008), [REQ-009](Requirements.md#req-009), [REQ-010](Requirements.md#req-010)\
Preconditions: Disposable multi-node cluster with backed-up test data and explicit teardown authorization.\
Steps: Install, rerun, expand, inspect health, remove and rebuild in a controlled lab.\
Expected result: Nodes converge and preserved storage survives; failures block later phases and rebuilt credentials are handled correctly.\
Status: Missing

Evidence / coverage boundary: No live end-to-end cluster lifecycle suite exists; offline action plugins cannot prove upstream script behavior.

### TC-021

ID: TC-021\
Title: Endpoint and platform health\
Requirement: [REQ-012](Requirements.md#req-012)\
Preconditions: Controlled DNS/TCP/TLS endpoints and separately deployed platform components.\
Steps: Exercise DNS, TCP, TLS and application authorization failures independently; validate Cilium/Longhorn runtime health.\
Expected result: Probe failures are classified correctly; handshake success is not reported as application authorization or trusted peer proof.\
Status: Missing

Evidence / coverage boundary: No dedicated automated endpoint/live platform integration tests exist.
