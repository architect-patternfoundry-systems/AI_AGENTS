#!/usr/bin/env bash
#
# compare-discovery-runs.sh — Compare two discovery evidence bundles.
#
# Produces a concise redacted delta report comparing posture attributes
# between a "before" and "after" discovery run. Does NOT compare raw
# report content, secret values, or provider references — only
# aggregate counts and classification distributions.
#
# USAGE:
#   ./deploy/cts/compare-discovery-runs.sh --before <dir> --after <dir>
#
# OPTIONS:
#   --before DIR    Path to the "before" evidence bundle (run_id=... directory)
#   --after  DIR    Path to the "after" evidence bundle (run_id=... directory)
#   --json           Output delta as JSON instead of human-readable text
#   --help           Show this help
#
# EXIT CODES:
#   0 — comparison completed
#   1 — missing files or invalid bundles
#
# The comparison covers:
#   - active_in_source count (emergency inline credentials)
#   - scan_status (completed vs completed_with_findings)
#   - emergency_items count
#   - total_credentials count
#   - exposure class distribution (inline, secret_delivered, etc.)
#   - coverage status changes
#   - candidate/unconfirmed count
#   - unowned/orphaned count
#   - entries_sha256 (provenance, not content comparison)
#   - manifest provenance (run_id, package_version, policy_version)
#
# All output is redacted. No provider references, secret names, or
# report content appears in the delta report.

set -Eeuo pipefail
IFS=$'\n\t'

CURRENT_STEP="initialization"

on_error() {
    local exit_code=$?
    printf 'ERROR: comparison failed at step=%s line=%s exit_code=%s\n' \
        "$CURRENT_STEP" "$LINENO" "$exit_code" >&2
    exit "$exit_code"
}

trap on_error ERR

# --- Configuration -----------------------------------------------------------

BEFORE_DIR=""
AFTER_DIR=""
JSON_OUTPUT=false

# --- Argument parsing --------------------------------------------------------

usage() {
    sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//' >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --before)  BEFORE_DIR="$2"; shift 2 ;;
        --after)   AFTER_DIR="$2"; shift 2 ;;
        --json)    JSON_OUTPUT=true; shift ;;
        --help|-h) usage ;;
        *)         fail "Unknown option: $1"; usage ;;
    esac
done

# --- Validation --------------------------------------------------------------

CURRENT_STEP="validation"

if [[ -z "${BEFORE_DIR}" ]]; then
    echo "FAIL: --before is required" >&2
    exit 1
fi
if [[ -z "${AFTER_DIR}" ]]; then
    echo "FAIL: --after is required" >&2
    exit 1
fi
if [[ ! -d "${BEFORE_DIR}" ]]; then
    echo "FAIL: before directory not found: ${BEFORE_DIR}" >&2
    exit 1
fi
if [[ ! -d "${AFTER_DIR}" ]]; then
    echo "FAIL: after directory not found: ${AFTER_DIR}" >&2
    exit 1
fi
if [[ ! -f "${BEFORE_DIR}/report.json" ]]; then
    echo "FAIL: before/report.json not found" >&2
    exit 1
fi
if [[ ! -f "${AFTER_DIR}/report.json" ]]; then
    echo "FAIL: after/report.json not found" >&2
    exit 1
fi
if [[ ! -f "${BEFORE_DIR}/manifest.json" ]]; then
    echo "FAIL: before/manifest.json not found" >&2
    exit 1
fi
if [[ ! -f "${AFTER_DIR}/manifest.json" ]]; then
    echo "FAIL: after/manifest.json not found" >&2
    exit 1
fi

# --- Helper functions --------------------------------------------------------

# Extract a count from report.json using jq
get_count() {
    local dir="$1"
    local filter="$2"
    jq "${filter}" "${dir}/report.json"
}

# Extract a field from manifest.json
get_manifest_field() {
    local dir="$1"
    local field="$2"
    jq -r ".${field}" "${dir}/manifest.json"
}

# Extract coverage from manifest
get_coverage() {
    local dir="$1"
    jq -r '.coverage | to_entries | map("\(.key):\(.value)") | sort | join(",")' "${dir}/manifest.json"
}

# Format a delta line: "label: before → after"
format_delta() {
    local label="$1"
    local before_val="$2"
    local after_val="$3"
    if [[ "${before_val}" == "${after_val}" ]]; then
        echo "  ${label}: ${before_val} (unchanged)"
    else
        echo "  ${label}: ${before_val} → ${after_val}"
    fi
}

# --- Extract metrics ---------------------------------------------------------

CURRENT_STEP="extract-metrics"

# Before metrics
BEFORE_SCAN_STATUS=$(get_manifest_field "${BEFORE_DIR}" "scan_status")
BEFORE_EXIT_CODE=$(get_manifest_field "${BEFORE_DIR}" "exit_code")
BEFORE_RUN_ID=$(get_manifest_field "${BEFORE_DIR}" "run_id")
BEFORE_EMERGENCY=$(get_manifest_field "${BEFORE_DIR}" "emergency_items")
BEFORE_TOTAL=$(get_manifest_field "${BEFORE_DIR}" "total_credentials")
BEFORE_COVERAGE=$(get_coverage "${BEFORE_DIR}")
BEFORE_ENTRIES_HASH=$(get_manifest_field "${BEFORE_DIR}" "entries_sha256")
BEFORE_PKG_VERSION=$(get_manifest_field "${BEFORE_DIR}" "package_version")
BEFORE_POLICY_VERSION=$(get_manifest_field "${BEFORE_DIR}" "policy_version")

BEFORE_ACTIVE_INLINE=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.exposure_status == "active_in_source")] | length')
BEFORE_SECRET_DELIVERED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.exposure_status == "secret_delivered")] | length')
BEFORE_SECRET_SHARED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.exposure_status == "secret_delivered_shared")] | length')
BEFORE_CERT_DELIVERED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.exposure_status == "certificate_delivered")] | length')
BEFORE_EXT_SECRET=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.exposure_status == "external_secret_delivered")] | length')
BEFORE_UNKNOWN_EXP=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.exposure_status == "unknown")] | length')

BEFORE_UNCONFIRMED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.correlation_status == "unconfirmed")] | length')
BEFORE_UNOWNED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.owner == null)] | length')
BEFORE_ORPHANED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.consumer_count == 0 and .lifecycle_state != "discovered")] | length')
BEFORE_ELIGIBLE=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.eligible == true)] | length')
BEFORE_BLOCKED=$(get_count "${BEFORE_DIR}" '[.entries[] | select(.eligible == false)] | length')

# After metrics
AFTER_SCAN_STATUS=$(get_manifest_field "${AFTER_DIR}" "scan_status")
AFTER_EXIT_CODE=$(get_manifest_field "${AFTER_DIR}" "exit_code")
AFTER_RUN_ID=$(get_manifest_field "${AFTER_DIR}" "run_id")
AFTER_EMERGENCY=$(get_manifest_field "${AFTER_DIR}" "emergency_items")
AFTER_TOTAL=$(get_manifest_field "${AFTER_DIR}" "total_credentials")
AFTER_COVERAGE=$(get_coverage "${AFTER_DIR}")
AFTER_ENTRIES_HASH=$(get_manifest_field "${AFTER_DIR}" "entries_sha256")
AFTER_PKG_VERSION=$(get_manifest_field "${AFTER_DIR}" "package_version")
AFTER_POLICY_VERSION=$(get_manifest_field "${AFTER_DIR}" "policy_version")

AFTER_ACTIVE_INLINE=$(get_count "${AFTER_DIR}" '[.entries[] | select(.exposure_status == "active_in_source")] | length')
AFTER_SECRET_DELIVERED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.exposure_status == "secret_delivered")] | length')
AFTER_SECRET_SHARED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.exposure_status == "secret_delivered_shared")] | length')
AFTER_CERT_DELIVERED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.exposure_status == "certificate_delivered")] | length')
AFTER_EXT_SECRET=$(get_count "${AFTER_DIR}" '[.entries[] | select(.exposure_status == "external_secret_delivered")] | length')
AFTER_UNKNOWN_EXP=$(get_count "${AFTER_DIR}" '[.entries[] | select(.exposure_status == "unknown")] | length')

AFTER_UNCONFIRMED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.correlation_status == "unconfirmed")] | length')
AFTER_UNOWNED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.owner == null)] | length')
AFTER_ORPHANED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.consumer_count == 0 and .lifecycle_state != "discovered")] | length')
AFTER_ELIGIBLE=$(get_count "${AFTER_DIR}" '[.entries[] | select(.eligible == true)] | length')
AFTER_BLOCKED=$(get_count "${AFTER_DIR}" '[.entries[] | select(.eligible == false)] | length')

# --- Output ------------------------------------------------------------------

CURRENT_STEP="output"

if $JSON_OUTPUT; then
    # JSON output
    jq -n \
        --arg before_run_id "${BEFORE_RUN_ID}" \
        --arg after_run_id "${AFTER_RUN_ID}" \
        --arg before_scan_status "${BEFORE_SCAN_STATUS}" \
        --arg after_scan_status "${AFTER_SCAN_STATUS}" \
        --argjson before_exit_code "${BEFORE_EXIT_CODE}" \
        --argjson after_exit_code "${AFTER_EXIT_CODE}" \
        --argjson before_emergency "${BEFORE_EMERGENCY}" \
        --argjson after_emergency "${AFTER_EMERGENCY}" \
        --argjson before_total "${BEFORE_TOTAL}" \
        --argjson after_total "${AFTER_TOTAL}" \
        --argjson before_active_inline "${BEFORE_ACTIVE_INLINE}" \
        --argjson after_active_inline "${AFTER_ACTIVE_INLINE}" \
        --argjson before_secret_delivered "${BEFORE_SECRET_DELIVERED}" \
        --argjson after_secret_delivered "${AFTER_SECRET_DELIVERED}" \
        --argjson before_unconfirmed "${BEFORE_UNCONFIRMED}" \
        --argjson after_unconfirmed "${AFTER_UNCONFIRMED}" \
        --argjson before_unowned "${BEFORE_UNOWNED}" \
        --argjson after_unowned "${AFTER_UNOWNED}" \
        --argjson before_orphaned "${BEFORE_ORPHANED}" \
        --argjson after_orphaned "${AFTER_ORPHANED}" \
        --arg before_coverage "${BEFORE_COVERAGE}" \
        --arg after_coverage "${AFTER_COVERAGE}" \
        --arg before_entries_sha256 "${BEFORE_ENTRIES_HASH}" \
        --arg after_entries_sha256 "${AFTER_ENTRIES_HASH}" \
        --arg before_pkg_version "${BEFORE_PKG_VERSION}" \
        --arg after_pkg_version "${AFTER_PKG_VERSION}" \
        '{
            before: {
                run_id: $before_run_id,
                scan_status: $before_scan_status,
                exit_code: $before_exit_code,
                emergency_items: $before_emergency,
                total_credentials: $before_total,
                active_inline: $before_active_inline,
                secret_delivered: $before_secret_delivered,
                unconfirmed: $before_unconfirmed,
                unowned: $before_unowned,
                orphaned: $before_orphaned,
                coverage: $before_coverage,
                entries_sha256: $before_entries_sha256,
                package_version: $before_pkg_version
            },
            after: {
                run_id: $after_run_id,
                scan_status: $after_scan_status,
                exit_code: $after_exit_code,
                emergency_items: $after_emergency,
                total_credentials: $after_total,
                active_inline: $after_active_inline,
                secret_delivered: $after_secret_delivered,
                unconfirmed: $after_unconfirmed,
                unowned: $after_unowned,
                orphaned: $after_orphaned,
                coverage: $after_coverage,
                entries_sha256: $after_entries_sha256,
                package_version: $after_pkg_version
            }
        }'
else
    # Human-readable output
    echo "=== DISCOVERY RUN COMPARISON ===" >&2
    echo "" >&2
    echo "  before: run_id=${BEFORE_RUN_ID}" >&2
    echo "  after:  run_id=${AFTER_RUN_ID}" >&2
    echo "" >&2

    echo "--- Scan result ---" >&2
    format_delta "scan_status" "${BEFORE_SCAN_STATUS}" "${AFTER_SCAN_STATUS}" >&2
    format_delta "exit_code" "${BEFORE_EXIT_CODE}" "${AFTER_EXIT_CODE}" >&2
    format_delta "emergency_items" "${BEFORE_EMERGENCY}" "${AFTER_EMERGENCY}" >&2
    echo "" >&2

    echo "--- Credential counts ---" >&2
    format_delta "total_credentials" "${BEFORE_TOTAL}" "${AFTER_TOTAL}" >&2
    format_delta "active_inline" "${BEFORE_ACTIVE_INLINE}" "${AFTER_ACTIVE_INLINE}" >&2
    format_delta "secret_delivered" "${BEFORE_SECRET_DELIVERED}" "${AFTER_SECRET_DELIVERED}" >&2
    format_delta "secret_delivered_shared" "${BEFORE_SECRET_SHARED}" "${AFTER_SECRET_SHARED}" >&2
    format_delta "certificate_delivered" "${BEFORE_CERT_DELIVERED}" "${AFTER_CERT_DELIVERED}" >&2
    format_delta "external_secret_delivered" "${BEFORE_EXT_SECRET}" "${AFTER_EXT_SECRET}" >&2
    format_delta "unknown_exposure" "${BEFORE_UNKNOWN_EXP}" "${AFTER_UNKNOWN_EXP}" >&2
    echo "" >&2

    echo "--- Correlation and ownership ---" >&2
    format_delta "unconfirmed_candidates" "${BEFORE_UNCONFIRMED}" "${AFTER_UNCONFIRMED}" >&2
    format_delta "unowned" "${BEFORE_UNOWNED}" "${AFTER_UNOWNED}" >&2
    format_delta "orphaned" "${BEFORE_ORPHANED}" "${AFTER_ORPHANED}" >&2
    format_delta "eligible" "${BEFORE_ELIGIBLE}" "${AFTER_ELIGIBLE}" >&2
    format_delta "blocked" "${BEFORE_BLOCKED}" "${AFTER_BLOCKED}" >&2
    echo "" >&2

    echo "--- Coverage ---" >&2
    if [[ "${BEFORE_COVERAGE}" == "${AFTER_COVERAGE}" ]]; then
        echo "  coverage: unchanged" >&2
    else
        echo "  coverage: CHANGED" >&2
        echo "    before: ${BEFORE_COVERAGE}" >&2
        echo "    after:  ${AFTER_COVERAGE}" >&2
    fi
    echo "" >&2

    echo "--- Provenance ---" >&2
    format_delta "entries_sha256" "${BEFORE_ENTRIES_HASH}" "${AFTER_ENTRIES_HASH}" >&2
    format_delta "package_version" "${BEFORE_PKG_VERSION}" "${AFTER_PKG_VERSION}" >&2
    format_delta "policy_version" "${BEFORE_POLICY_VERSION}" "${AFTER_POLICY_VERSION}" >&2
    echo "" >&2

    # Summary assessment
    echo "--- Assessment ---" >&2
    if [[ "${BEFORE_ACTIVE_INLINE}" -gt 0 && "${AFTER_ACTIVE_INLINE}" -eq 0 ]]; then
        echo "  REMEDIATION VERIFIED: active_inline_credentials ${BEFORE_ACTIVE_INLINE} → 0" >&2
    elif [[ "${BEFORE_ACTIVE_INLINE}" -gt 0 && "${AFTER_ACTIVE_INLINE}" -gt 0 ]]; then
        echo "  REMEDIATION INCOMPLETE: active_inline_credentials ${BEFORE_ACTIVE_INLINE} → ${AFTER_ACTIVE_INLINE}" >&2
    elif [[ "${BEFORE_ACTIVE_INLINE}" -eq 0 && "${AFTER_ACTIVE_INLINE}" -gt 0 ]]; then
        echo "  REGRESSION: active_inline_credentials 0 → ${AFTER_ACTIVE_INLINE}" >&2
    else
        echo "  NO INLINE CREDENTIALS in either run" >&2
    fi

    if [[ "${BEFORE_SCAN_STATUS}" == "completed_with_findings" && "${AFTER_SCAN_STATUS}" == "completed" ]]; then
        echo "  SCAN STATUS IMPROVED: completed_with_findings → completed" >&2
    elif [[ "${BEFORE_SCAN_STATUS}" == "completed" && "${AFTER_SCAN_STATUS}" == "completed_with_findings" ]]; then
        echo "  SCAN STATUS REGRESSED: completed → completed_with_findings" >&2
    fi
fi

exit 0
