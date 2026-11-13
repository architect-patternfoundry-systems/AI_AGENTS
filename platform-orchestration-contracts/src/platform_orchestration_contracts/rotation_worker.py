"""Temporal worker entrypoint for the credential-rotation workflow.

Registers CredentialRotationWorkflow + all side-effecting activities on
the `credential-rotation` task queue. Runs until SIGTERM; exits nonzero
on connection failure so Kubernetes restarts it.
"""
import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from platform_orchestration_contracts import (
    credential_rotation_activities as acts,
    credential_rotation_workflow as wf,
)

log = logging.getLogger("rotation-worker")


async def main() -> None:
    addr = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    ns = os.environ.get("TEMPORAL_NAMESPACE", "default")
    tq = os.environ.get("TEMPORAL_TASK_QUEUE", "credential-rotation")
    client = await Client.connect(addr, namespace=ns)
    worker = Worker(
        client,
        task_queue=tq,
        workflows=[wf.CredentialRotationWorkflow],
        activities=[
            acts.generate_successor_cred,
            acts.create_role,
            acts.sops_encrypt_and_open_pr,
            acts.notify_human,
            acts.wait_consumer_healthy,
            acts.patch_and_roll,
            acts.revoke_predecessor,
            acts.liveness_dead_check,
            acts.post_closure_evidence,
        ],
    )
    log.info("worker listening: addr=%s ns=%s tq=%s", addr, ns, tq)
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except Exception:
        log.exception("worker fatal")
        sys.exit(1)
