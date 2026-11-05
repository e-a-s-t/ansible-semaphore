# Roadmap and known gaps

This is an evidence-based gap register, not an approved delivery schedule. No committed roadmap, milestones, or owners are recorded in the repository. Existing behavior is described in [Requirements](Requirements.md); proposals below do not add approved requirements.

## Functionality and operational gaps

| Gap | Current implementation | Proposed enhancement |
|-----|------------------------|----------------------|
| Version upgrades and managed-setting changes | Installation refuses drift and preserves matching nodes. | Design a separately reviewed maintenance/upgrade workflow with recovery criteria. |
| Platform deployment | Cilium is selected through RKE2; Longhorn prerequisites/storage are prepared, but Longhorn, backup services and ingress are not deployed. | Define ownership and interfaces before adding platform automation. |
| Cluster disaster recovery | Controller credentials are copied; etcd backup/restore is operator-managed. | Establish a verified snapshot/restore runbook and isolated recovery tests. |
| Custom runtime/storage layouts | Some paths are configurable, but installation assumptions and removal/protection paths remain fixed. | Either constrain configuration explicitly in code or design consistent layout support with safety tests. |
| Monitoring | Ansible reports and node verification only. | Define operational health requirements before adding alerts or monitoring integrations. |

## Technical debt and inconsistencies

- `vars_files` override inventory defaults. Earlier README guidance implied generic inventory overrides worked; [Configuration](Configuration.md) now documents actual precedence. A future defaults-loading change would require compatibility review.
- Dependency versions are unpinned; there is no dependency manifest, formatting/lint configuration, CI/CD, or repository release/versioning workflow. Choose those conventions separately rather than claiming they already exist.
- `prerequisites_longhorn_required_utilities` and `prerequisites_installation_deferred_settings` are declared but not consumed as general policy controls; utility probes currently hard-code two tools.
- Validation/preparation accept a configurable Longhorn path while removal protects `/var/lib/longhorn` explicitly. Nondefault layouts need review and must not be assumed safe.
- `rke2_node_name` maps verification expectations but is not rendered into RKE2 configuration. A custom value must match the actual registered node identity.
- Endpoint checks use trusted shell inputs and TLS handshake success without strict peer verification. Hardening input validation or certificate policy would be a behavior change requiring separate approval.
- Managed-field comparison does not inspect every RKE2 setting or independently establish cluster identity. Installer error redaction is pattern-based; prerequisite process diagnostics may contain sensitive command-line data.

## Verification and documentation gaps

[TC-019](Testcases.md#tc-019), [TC-020](Testcases.md#tc-020), and [TC-021](Testcases.md#tc-021) identify missing live OS/storage, lifecycle, and endpoint/platform tests. Connectivity also lacks a dedicated automated case ([TC-001](Testcases.md#tc-001)). Existing modeled tests cannot prove real formatting safety, upstream uninstaller side effects, or production availability. There is no measured coverage baseline.

Historical decision dates/rationale, supported minimum tool versions, tested production topologies, release ownership, license terms, vulnerability reporting process, and recovery-time objectives are not established by repository evidence. Document them when the project establishes them. New documentation should stay linked to source rather than accumulating duplicated commands or inferred guarantees.
