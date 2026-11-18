"""Regression tests for _kubectl payload handling.

Covers the 400-byte truncation incident (2026-11): a >400B successful
payload — e.g. the 559-byte pgbouncer-userlist `.data` map — was cut
mid-JSON, so callers' json.loads failed and the rotation workflow spun
forever on RETRYABLE `secret-parse`. In the gitops render path the same
truncation would have silently sealed a corrupted userlist into a PR.

Contract: success returns complete stdout; only failure detail is bounded.
"""

import subprocess
from unittest.mock import patch

import pytest

from platform_orchestration_contracts.credential_rotation_activities import _kubectl

MOD = "platform_orchestration_contracts.credential_rotation_activities.subprocess.run"


def _proc(stdout=b"", stderr=b"", returncode=0):
    return subprocess.CompletedProcess(
        args=["kubectl"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_success_returns_full_payload_over_400b():
    payload = b'{"userlist.txt":"' + b'"user" "pw"\n' * 60 + b'"}'
    assert len(payload) > 400
    with patch(MOD, return_value=_proc(stdout=payload)):
        ok, out = _kubectl("get", "secret", "pgbouncer-userlist",
                           "-n", "infra-data", "-o", "jsonpath={.data}")
    assert ok is True
    assert out == payload.decode()


def test_success_ignores_stderr_and_returns_stdout():
    # kubectl emits warnings (deprecation, permissions) on stderr while
    # succeeding; stdout is the data channel and must not be clobbered.
    with patch(MOD, return_value=_proc(stdout=b'{"a":"b"}',
                                       stderr=b"warning: foo deprecated\n")):
        ok, out = _kubectl("get", "secret", "x")
    assert (ok, out) == (True, '{"a":"b"}')


def test_failure_bounded_at_400b():
    with patch(MOD, return_value=_proc(stderr=b"e" * 1000, returncode=1)):
        ok, out = _kubectl("get", "secret", "x")
    assert ok is False
    assert len(out) == 400


def test_failure_prefers_stderr_then_stdout():
    with patch(MOD, return_value=_proc(stdout=b"o" * 100, stderr=b"err",
                                       returncode=1)):
        ok, out = _kubectl("get", "secret", "x")
    assert (ok, out) == (False, "err")
    # stderr empty → fall back to stdout for the error detail
    with patch(MOD, return_value=_proc(stdout=b"o" * 500, stderr=b"",
                                       returncode=1)):
        ok, out = _kubectl("get", "secret", "x")
    assert ok is False
    assert out == "o" * 400


def test_timeout_returns_not_ok():
    with patch(MOD, side_effect=subprocess.TimeoutExpired("kubectl", 30)):
        ok, out = _kubectl("get", "secret", "x")
    assert (ok, out) == (False, "kubectl-timeout")


@pytest.mark.parametrize("secret_spec,expected", [
    # multi-key mapping form
    ({"keys": {"POSTGRES_USER": "{user}", "POSTGRES_PASSWORD": "{pw}"}},
     {"POSTGRES_USER": "{user}", "POSTGRES_PASSWORD": "{pw}"}),
    # legacy single-key form
    ({"key": "uri", "value_template": "postgresql://{user}:{pw}@h/d"},
     {"uri": "postgresql://{user}:{pw}@h/d"}),
    ({"key": "password"}, {"password": "{pw}"}),
])
def test_secret_keys_forms(secret_spec, expected):
    from platform_orchestration_contracts.credential_rotation_activities import _secret_keys
    assert _secret_keys(secret_spec) == expected
