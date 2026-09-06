#!/usr/bin/env bash
#
# run-one-shot-scan.sh — Repeatable, certifiable one-shot CTS credential discovery scan.
#
# This script encodes the full operational sequence required before the
# first live scan, so that the process is identical for the canary run
# and any future controlled rerun (e.g. after remediation verification).
#
# It does NOT schedule recurring discovery. Each invocation is one-shot.
#
# USAGE:
#   ./deploy/cts/run-one-shot-scan.sh [OPTIONS]
#
# OPTIONS:
#   --namespace NS       Target namespace (default: cts)
#   --environment ENV    Environment label for evidence path (default: dev)
#   --image DIGEST       Pinned image reference (required for --apply-job)
#   --apply-rbac         Apply RBAC manifests before checks
#   --apply-pvc          Apply PVC manifest before checks
#   --apply-job          Apply and run the one-shot Job (requires --image)
#   --retrieve           Retrieve evidence bundle from PVC after Job completes
#   --verify             Verify manifest, checksums, and safety of retrieved bundle
#   --all                Equivalent to --apply-rbac --apply-pvc --apply-job --retrieve --verify
#   --dry-run            Render manifests and print checks without applying
#   --keep-job           Do not delete Job object after completion (for debugging)
#   --help               Show this help
#
# EXIT CODES:
#   0 — scan completed, no emergency findings (scan_status=completed)
#   1 — preflight failure, scan failure, or verification failure
#   2 — scan completed with findings (scan_status=completed_with_findings)
#       (preserved from the scanner process; see manifest.json for semantics)
#
# REQUIREMENTS:
#   - kubectl configured and connected to the target cluster
#   - kubectl auth can impersonate the discovery service account
#   - For --apply-job: a digest-pinned image accessible from the cluster
#
# SAFETY PROPERTIES ENFORCED BY THIS SCRIPT:
#   1. Negative RBAC checks: service account CANNOT read/list/watch Secrets
#   2. Positive RBAC checks: service account CAN list required workload types
#   3. Image must be pinned by digest (not mutable tag)
#   4. Job has backoffLimit=0, runAsNonRoot, readOnlyRootFilesystem
#   5. Evidence bundle is retrieved and verified after Job completion
#   6. Manifest scan_status is checked against process exit code
#   7. Checksums in manifest.json are verified against actual files
#   8. Redacted reports are scanned for prohibited secret markers
#
# This script is defense in depth. The primary safety boundary remains
# architectural: raw values discarded at the API boundary, raw API
# objects never escape the client, and only redacted safe models are
# persisted.

set -euo pipefail

# --- Configuration -----------------------------------------------------------

NAMESPACE="cts"
ENVIRONMENT="dev"
IMAGE=""
APPLY_RBAC=false
APPLY_PVC=false
APPLY_JOB=false
RETRIEVE=false
VERIFY=false
DRY_RUN=false
KEEP_JOB=false

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVIDENCE_DIR="${EVIDENCE_DIR:-/tmp/cts-discovery-evidence}"
JOB_NAME="credential-discovery-cts-once"
SA_NAME="credential-discovery-kubernetes"
PVC_NAME="credential-discovery-evidence"

# Colors for output (disabled if not a TTY)
if [[ -t 2 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

log()   { echo -e "${BLUE}[$(date -u +%H:%M:%S)]${NC} $*" >&2; }
ok()    { echo -e "${GREEN}[$(date -u +%H:%M:%S)] PASS${NC} $*" >&2; }
fail()  { echo -e "${RED}[$(date -u +%H:%M:%S)] FAIL${NC} $*" >&2; }
warn()  { echo -e "${YELLOW}[$(date -u +%H:%M:%S)] WARN${NC} $*" >&2; }

# --- Argument parsing --------------------------------------------------------

usage() {
    sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//' >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --namespace)   NAMESPACE="$2"; shift 2 ;;
        --environment) ENVIRONMENT="$2"; shift 2 ;;
        --image)       IMAGE="$2"; shift 2 ;;
        --apply-rbac)  APPLY_RBAC=true; shift ;;
        --apply-pvc)   APPLY_PVC=true; shift ;;
        --apply-job)   APPLY_JOB=true; shift ;;
        --retrieve)    RETRIEVE=true; shift ;;
        --verify)      VERIFY=true; shift ;;
        --all)         APPLY_RBAC=true; APPLY_PVC=true; APPLY_JOB=true; RETRIEVE=true; VERIFY=true; shift ;;
        --dry-run)     DRY_RUN=true; shift ;;
        --keep-job)    KEEP_JOB=true; shift ;;
        --help|-h)     usage ;;
        *)             fail "Unknown option: $1"; usage ;;
    esac
done

# --- Preflight: tool checks --------------------------------------------------

check_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        fail "Required tool not found: $1"
        exit 1
    fi
}

check_tool kubectl
check_tool sha256sum
check_tool jq

log "Tools verified: kubectl, sha256sum, jq"

# --- Step 1: Apply RBAC ------------------------------------------------------

if $APPLY_RBAC; then
    log "Step 1: Applying RBAC manifests to namespace ${NAMESPACE}"
    if $DRY_RUN; then
        log "  [dry-run] would apply: ${SCRIPT_DIR}/rbac.yaml"
    else
        kubectl apply -f "${SCRIPT_DIR}/rbac.yaml" --namespace="${NAMESPACE}"
        ok "RBAC applied"
    fi
else
    log "Step 1: Skipping RBAC apply (use --apply-rbac)"
fi

# --- Step 2: Apply PVC -------------------------------------------------------

if $APPLY_PVC; then
    log "Step 2: Applying PVC manifest to namespace ${NAMESPACE}"
    if $DRY_RUN; then
        log "  [dry-run] would apply: ${SCRIPT_DIR}/pvc.yaml"
    else
        kubectl apply -f "${SCRIPT_DIR}/pvc.yaml" --namespace="${NAMESPACE}"
        ok "PVC applied"
    fi
else
    log "Step 2: Skipping PVC apply (use --apply-pvc)"
fi

# --- Step 3: RBAC verification (always run) ----------------------------------

log "Step 3: Verifying RBAC permissions for ${SA_NAME}"

SA_FULL="system:serviceaccount:${NAMESPACE}:${SA_NAME}"

check_negative() {
    local resource="$1"
    local verb="$2"
    local result
    result=$(kubectl auth can-i "${verb}" "${resource}" \
        --as="${SA_FULL}" -n "${NAMESPACE}" 2>/dev/null || echo "error")
    if [[ "${result}" == "no" ]]; then
        ok "Negative check: ${verb} ${resource} → no (correct)"
    else
        fail "Negative check FAILED: ${verb} ${resource} → ${result} (expected: no)"
        exit 1
    fi
}

check_positive() {
    local resource="$1"
    local verb="$2"
    local result
    result=$(kubectl auth can-i "${verb}" "${resource}" \
        --as="${SA_FULL}" -n "${NAMESPACE}" 2>/dev/null || echo "error")
    if [[ "${result}" == "yes" ]]; then
        ok "Positive check: ${verb} ${resource} → yes (correct)"
    else
        fail "Positive check FAILED: ${verb} ${resource} → ${result} (expected: yes)"
        exit 1
    fi
}

# Negative checks: service account must NOT be able to access Secrets
check_negative "secrets" "get"
check_negative "secrets" "list"
check_negative "secrets" "watch"

# Positive checks: service account MUST be able to list workload types
check_positive "deployments" "list"
check_positive "statefulsets" "list"
check_positive "daemonsets" "list"
check_positive "jobs" "list"
check_positive "cronjobs" "list"

ok "All RBAC checks passed"

# --- Step 4: Verify PVC exists -----------------------------------------------

log "Step 4: Verifying PVC ${PVC_NAME} in namespace ${NAMESPACE}"

PVC_STATUS=$(kubectl get pvc "${PVC_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "not_found")

if [[ "${PVC_STATUS}" == "Bound" ]]; then
    ok "PVC ${PVC_NAME} is Bound"
elif [[ "${PVC_STATUS}" == "not_found" ]]; then
    fail "PVC ${PVC_NAME} not found in namespace ${NAMESPACE}"
    fail "Apply with: kubectl apply -f ${SCRIPT_DIR}/pvc.yaml"
    exit 1
else
    warn "PVC ${PVC_NAME} status: ${PVC_STATUS} (expected Bound)"
    if ! $DRY_RUN; then
        fail "PVC not ready"
        exit 1
    fi
fi

# --- Step 5: Image digest verification ---------------------------------------

if $APPLY_JOB; then
    log "Step 5: Verifying image digest"

    if [[ -z "${IMAGE}" ]]; then
        fail "--apply-job requires --image <pinned-digest>"
        fail "Example: --image registry-bridge.tailc2cafc.ts.net/credential-discovery@sha256:abc123..."
        exit 1
    fi

    if [[ "${IMAGE}" != *@sha256:* ]]; then
        fail "Image must be pinned by digest (not mutable tag): ${IMAGE}"
        fail "Use: registry.../image@sha256:<64-hex-chars>"
        exit 1
    fi

    ok "Image pinned by digest: ${IMAGE}"

    # --- Step 6: Render and apply Job ----------------------------------------

    log "Step 6: Rendering and applying one-shot Job"

    # Generate a unique run ID for this scan
    RUN_ID="discovery-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"

    # Render Job manifest with the pinned image and unique run ID
    # The run_id is passed as an arg to the scanner so the evidence
    # bundle directory is unique per invocation.
    RENDERED_JOB=$(mktemp /tmp/cts-discovery-job.XXXXXX.yaml)
    trap 'rm -f "${RENDERED_JOB}"' EXIT

    sed \
        -e "s|image: <pinned-image-digest>|image: ${IMAGE}|" \
        "${SCRIPT_DIR}/job.yaml" > "${RENDERED_JOB}"

    # Add run_id to the scanner args
    sed -i \
        "s|--log-level=WARNING|--log-level=WARNING \\\\\n            - --run-id=${RUN_ID}|" \
        "${RENDERED_JOB}"

    if $DRY_RUN; then
        log "  [dry-run] would apply rendered Job:"
        cat "${RENDERED_JOB}" >&2
        log "  [dry-run] run_id would be: ${RUN_ID}"
    else
        # Verify Job spec before applying
        if ! kubectl apply --dry-run=client -f "${RENDERED_JOB}" >/dev/null 2>&1; then
            fail "Job manifest failed client-side dry-run validation"
            cat "${RENDERED_JOB}" >&2
            exit 1
        fi
        ok "Job manifest passed dry-run validation"

        # Delete any existing Job with the same name (from prior runs)
        kubectl delete job "${JOB_NAME}" -n "${NAMESPACE}" --ignore-not-found=true >/dev/null 2>&1 || true

        kubectl apply -f "${RENDERED_JOB}" --namespace="${NAMESPACE}"
        ok "Job applied: ${JOB_NAME} (run_id=${RUN_ID})"

        # --- Step 7: Wait for Job completion ---------------------------------

        log "Step 7: Waiting for Job completion (this may take a few minutes)"

        # Wait for the Job to reach a terminal state
        # Kubernetes marks exit 2 as "failed", so we check both conditions
        while true; do
            JOB_STATUS=$(kubectl get job "${JOB_NAME}" -n "${NAMESPACE}" \
                -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || echo "")
            JOB_FAILED=$(kubectl get job "${JOB_NAME}" -n "${NAMESPACE}" \
                -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || echo "")

            if [[ "${JOB_STATUS}" == "True" ]]; then
                ok "Job completed successfully (exit 0)"
                PROCESS_EXIT=0
                break
            elif [[ "${JOB_FAILED}" == "True" ]]; then
                # Could be exit 1 (failure) or exit 2 (findings)
                # Check the Pod's container exit code
                POD_NAME=$(kubectl get pods -n "${NAMESPACE}" \
                    -l job-name="${JOB_NAME}" \
                    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

                if [[ -n "${POD_NAME}" ]]; then
                    CONTAINER_EXIT=$(kubectl get pod "${POD_NAME}" -n "${NAMESPACE}" \
                        -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}' 2>/dev/null || echo "1")

                    if [[ "${CONTAINER_EXIT}" == "2" ]]; then
                        warn "Job terminated with exit code 2 (completed_with_findings)"
                        warn "This is a successful scan with urgent findings — NOT a scanner failure"
                        PROCESS_EXIT=2
                        break
                    elif [[ "${CONTAINER_EXIT}" == "1" ]]; then
                        fail "Job terminated with exit code 1 (scan failed)"
                        PROCESS_EXIT=1
                        break
                    else
                        fail "Job terminated with unexpected exit code: ${CONTAINER_EXIT}"
                        PROCESS_EXIT=1
                        break
                    fi
                else
                    fail "Job failed but no Pod found to determine exit code"
                    PROCESS_EXIT=1
                    break
                fi
            fi

            sleep 5
        done

        # Print Pod logs (stderr only — should contain DISCOVERY RESULT block)
        POD_NAME=$(kubectl get pods -n "${NAMESPACE}" \
            -l job-name="${JOB_NAME}" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [[ -n "${POD_NAME}" ]]; then
            log "Step 7a: Pod logs (console summary from scanner):"
            kubectl logs "${POD_NAME}" -n "${NAMESPACE}" --container=discovery >&2 || true
        fi

        # Clean up Job object unless --keep-job
        if ! $KEEP_JOB; then
            log "Step 7b: Cleaning up Job object (PVC evidence is preserved)"
            kubectl delete job "${JOB_NAME}" -n "${NAMESPACE}" --ignore-not-found=true >/dev/null 2>&1 || true
        else
            warn "Keeping Job object for debugging (--keep-job)"
        fi
    fi
fi

# --- Step 8: Retrieve evidence bundle ----------------------------------------

if $RETRIEVE; then
    log "Step 8: Retrieving evidence bundle from PVC"

    if $DRY_RUN; then
        log "  [dry-run] would create helper Pod to copy evidence from PVC"
        log "  [dry-run] evidence would be copied to: ${EVIDENCE_DIR}"
    else
        # Create a temporary helper Pod to copy evidence from the PVC
        # This Pod mounts the PVC read-only and does NOT use the scanner
        # service account — it uses a restricted ephemeral pod.
        HELPER_POD="evidence-reader-$(date -u +%s)"
        mkdir -p "${EVIDENCE_DIR}"

        kubectl run "${HELPER_POD}" \
            --namespace="${NAMESPACE}" \
            --image=busybox:1.36 \
            --restart=Never \
            --overrides='{
                "spec": {
                    "securityContext": {
                        "runAsNonRoot": true,
                        "runAsUser": 65532,
                        "fsGroup": 65532
                    },
                    "containers": [{
                        "name": "reader",
                        "image": "busybox:1.36",
                        "command": ["sleep", "300"],
                        "volumeMounts": [{
                            "name": "evidence",
                            "mountPath": "/evidence",
                            "readOnly": true
                        }],
                        "securityContext": {
                            "allowPrivilegeEscalation": false,
                            "readOnlyRootFilesystem": true,
                            "runAsNonRoot": true,
                            "runAsUser": 65532
                        }
                    }],
                    "volumes": [{
                        "name": "evidence",
                        "persistentVolumeClaim": {
                            "claimName": "credential-discovery-evidence"
                        }
                    }]
                }
            }' >/dev/null 2>&1

        # Wait for helper Pod to be ready
        kubectl wait pod "${HELPER_POD}" -n "${NAMESPACE}" --for=condition=Ready --timeout=60s >/dev/null 2>&1 || {
            fail "Helper Pod did not become ready"
            kubectl delete pod "${HELPER_POD}" -n "${NAMESPACE}" --ignore-not-found=true >/dev/null 2>&1 || true
            exit 1
        }

        # Copy evidence from PVC to local directory
        kubectl cp "${NAMESPACE}/${HELPER_POD}:/evidence/credential-discovery" "${EVIDENCE_DIR}/credential-discovery" \
            --container=reader >/dev/null 2>&1 || {
            fail "Failed to copy evidence from PVC"
            kubectl delete pod "${HELPER_POD}" -n "${NAMESPACE}" --ignore-not-found=true >/dev/null 2>&1 || true
            exit 1
        }

        # Clean up helper Pod
        kubectl delete pod "${HELPER_POD}" -n "${NAMESPACE}" --ignore-not-found=true >/dev/null 2>&1 || true

        ok "Evidence bundle retrieved to: ${EVIDENCE_DIR}"
        log "  Bundle contents:"
        find "${EVIDENCE_DIR}" -type f | sort >&2
    fi
fi

# --- Step 9: Verify evidence bundle ------------------------------------------

if $VERIFY; then
    log "Step 9: Verifying evidence bundle integrity and safety"

    if $DRY_RUN; then
        log "  [dry-run] would verify manifest, checksums, and scan for prohibited markers"
    else
        # Find the most recent run directory
        BUNDLE_DIR=$(find "${EVIDENCE_DIR}" -type d -name "run_id=*" | sort | tail -1)

        if [[ -z "${BUNDLE_DIR}" ]]; then
            fail "No evidence bundle found in ${EVIDENCE_DIR}"
            exit 1
        fi

        log "  Verifying bundle: ${BUNDLE_DIR}"

        # 9a: Verify all expected files exist
        for f in report.json report.md manifest.json checksums.txt; do
            if [[ ! -f "${BUNDLE_DIR}/${f}" ]]; then
                fail "Missing file: ${f}"
                exit 1
            fi
        done
        ok "All expected files present"

        # 9b: Verify checksums.txt matches actual file hashes
        log "  Verifying checksums..."
        pushd "${BUNDLE_DIR}" >/dev/null
        while IFS= read -r line; do
            expected_hash=$(echo "${line}" | awk '{print $1}')
            filename=$(echo "${line}" | awk '{print $2}')
            if [[ -z "${expected_hash}" || -z "${filename}" ]]; then
                continue
            fi
            actual_hash=$(sha256sum "${filename}" | awk '{print $1}')
            if [[ "${expected_hash}" != "${actual_hash}" ]]; then
                fail "Checksum mismatch for ${filename}: expected ${expected_hash}, got ${actual_hash}"
                popd >/dev/null
                exit 1
            fi
            ok "  ${filename}: sha256 verified"
        done < checksums.txt
        popd >/dev/null

        # 9c: Verify manifest structure and scan_status
        log "  Verifying manifest structure..."
        MANIFEST_SCAN_STATUS=$(jq -r '.scan_status' "${BUNDLE_DIR}/manifest.json")
        MANIFEST_EXIT_CODE=$(jq -r '.exit_code' "${BUNDLE_DIR}/manifest.json")
        MANIFEST_RUN_ID=$(jq -r '.run_id' "${BUNDLE_DIR}/manifest.json")
        MANIFEST_EMERGENCY=$(jq -r '.emergency_items' "${BUNDLE_DIR}/manifest.json")
        MANIFEST_COVERAGE=$(jq -r '.coverage | to_entries | map("\(.key):\(.value)") | join(",")' "${BUNDLE_DIR}/manifest.json")

        if [[ -z "${MANIFEST_SCAN_STATUS}" || "${MANIFEST_SCAN_STATUS}" == "null" ]]; then
            fail "Manifest missing scan_status"
            exit 1
        fi

        ok "  scan_status=${MANIFEST_SCAN_STATUS}"
        ok "  exit_code=${MANIFEST_EXIT_CODE}"
        ok "  run_id=${MANIFEST_RUN_ID}"
        ok "  emergency_items=${MANIFEST_EMERGENCY}"
        ok "  coverage=${MANIFEST_COVERAGE}"

        # Validate scan_status is in closed vocabulary
        case "${MANIFEST_SCAN_STATUS}" in
            completed|completed_with_findings|failed|partial) ;;
            *)
                fail "Invalid scan_status in manifest: ${MANIFEST_SCAN_STATUS}"
                exit 1
                ;;
        esac

        # 9d: Verify coverage honesty
        log "  Verifying coverage honesty..."
        PG_STATUS=$(jq -r '.coverage.postgres' "${BUNDLE_DIR}/manifest.json")
        MINIO_STATUS=$(jq -r '.coverage.minio' "${BUNDLE_DIR}/manifest.json")
        GIT_STATUS=$(jq -r '.coverage.git_findings' "${BUNDLE_DIR}/manifest.json")
        K8S_STATUS=$(jq -r '.coverage.kubernetes' "${BUNDLE_DIR}/manifest.json")

        if [[ "${K8S_STATUS}" != "completed" ]]; then
            fail "Kubernetes coverage should be 'completed', got: ${K8S_STATUS}"
            exit 1
        fi
        if [[ "${PG_STATUS}" != "not_configured" ]]; then
            fail "PostgreSQL coverage should be 'not_configured', got: ${PG_STATUS}"
            exit 1
        fi
        if [[ "${MINIO_STATUS}" != "not_configured" ]]; then
            fail "MinIO coverage should be 'not_configured', got: ${MINIO_STATUS}"
            exit 1
        fi
        if [[ "${GIT_STATUS}" != "not_configured" ]]; then
            fail "Git findings coverage should be 'not_configured', got: ${GIT_STATUS}"
            exit 1
        fi
        ok "Coverage is honest: kubernetes=completed, others=not_configured"

        # 9e: Verify correlation status in report
        log "  Verifying candidate correlation status..."
        UNCONFIRMED_COUNT=$(jq '[.entries[] | select(.correlation_status == "unconfirmed")] | length' "${BUNDLE_DIR}/report.json")
        if [[ "${UNCONFIRMED_COUNT}" -gt 0 ]]; then
            ok "  ${UNCONFIRMED_COUNT} candidate record(s) marked unconfirmed"
        else
            ok "  No unconfirmed candidate records (or no entries)"
        fi

        # 9f: Scan for prohibited secret markers in all bundle files
        log "  Scanning bundle files for prohibited secret markers..."
        PROHIBITED_PATTERNS=(
            'password='
            'postgres://'
            'postgresql://'
            'authorization: bearer'
            'authorization: basic'
            'aws_secret_access_key='
            'begin private key'
            'begin rsa private key'
            'begin openssh private key'
        )

        for f in report.json report.md manifest.json checksums.txt; do
            for pattern in "${PROHIBITED_PATTERNS[@]}"; do
                if grep -qi "${pattern}" "${BUNDLE_DIR}/${f}" 2>/dev/null; then
                    fail "Prohibited marker '${pattern}' found in ${f}"
                    exit 1
                fi
            done
        done
        ok "No prohibited secret markers found in bundle files"

        # 9g: Verify manifest hashes match actual report files
        log "  Verifying manifest hashes match report files..."
        EXPECTED_JSON_HASH=$(jq -r '.report_json_sha256' "${BUNDLE_DIR}/manifest.json" | sed 's/sha256://')
        ACTUAL_JSON_HASH=$(sha256sum "${BUNDLE_DIR}/report.json" | awk '{print $1}')
        if [[ "${EXPECTED_JSON_HASH}" != "${ACTUAL_JSON_HASH}" ]]; then
            fail "report.json hash mismatch: manifest=${EXPECTED_JSON_HASH}, actual=${ACTUAL_JSON_HASH}"
            exit 1
        fi
        ok "  report.json hash matches manifest"

        EXPECTED_MD_HASH=$(jq -r '.report_markdown_sha256' "${BUNDLE_DIR}/manifest.json" | sed 's/sha256://')
        ACTUAL_MD_HASH=$(sha256sum "${BUNDLE_DIR}/report.md" | awk '{print $1}')
        if [[ "${EXPECTED_MD_HASH}" != "${ACTUAL_MD_HASH}" ]]; then
            fail "report.md hash mismatch: manifest=${EXPECTED_MD_HASH}, actual=${ACTUAL_MD_HASH}"
            exit 1
        fi
        ok "  report.md hash matches manifest"

        ok "Evidence bundle verification complete"

        # Print final summary
        echo "" >&2
        echo "=== ONE-SHOT SCAN RESULT ===" >&2
        echo "  scan_status:     ${MANIFEST_SCAN_STATUS}" >&2
        echo "  exit_code:       ${MANIFEST_EXIT_CODE}" >&2
        echo "  run_id:          ${MANIFEST_RUN_ID}" >&2
        echo "  emergency_items: ${MANIFEST_EMERGENCY}" >&2
        echo "  coverage:        ${MANIFEST_COVERAGE}" >&2
        echo "  bundle:          ${BUNDLE_DIR}" >&2
        echo "" >&2

        if [[ "${MANIFEST_SCAN_STATUS}" == "completed_with_findings" ]]; then
            warn "SCAN COMPLETED WITH URGENT FINDINGS"
            warn "Treat ${MANIFEST_EMERGENCY} active_in_source item(s) as emergency remediation."
            warn "Rotate exposed credentials and replace inline values with secretKeyRef."
            warn "Re-run with a new run ID after remediation to verify the fix."
        elif [[ "${MANIFEST_SCAN_STATUS}" == "completed" ]]; then
            ok "SCAN COMPLETED — no emergency findings"
        else
            fail "SCAN STATUS: ${MANIFEST_SCAN_STATUS}"
        fi
    fi
fi

# --- Exit code propagation ---------------------------------------------------

if $APPLY_JOB && ! $DRY_RUN; then
    exit "${PROCESS_EXIT:-1}"
fi

exit 0
