# UndoStack

UndoStack is a reusable GenLayer Intelligent Contract for recording bounded workflows that can be compensated if cancelled. An owner freezes a directed acyclic plan of actions, reverse actions, assigned actors, and dependencies. An actor must start a step before reporting its outcome. GenLayer validators independently assess whether a declaration shows the entire action, shows that it never took effect, or remains uncertain.

Only validated `DONE` steps unlock dependent actions. Cancellation stops new starts, but every step already marked `RUNNING` must be resolved first. A partial, contradictory, missing, or uncertain report leaves the workflow in `CANCELLING`; it cannot silently unlock rollback. Once no work is in flight, completed actions become `UNDO_PENDING`, in reverse dependency order. Each assigned actor submits evidence for its compensation. The workflow reaches `ROLLED_BACK` only after every compensation is judged done. Missing or inconclusive evidence leaves the workflow visibly open for human resolution.

This contract coordinates and records declared evidence; it does not execute actions or guarantee that a service provider, booking system, or physical actor obeys an instruction. A compensating action can be impossible or fail. Its text, reports, roles, and state are public. There are no payments, escrow, identity checks, or hidden timeout assumptions.

## Consensus boundary

GenLayer consensus assesses whether each bounded public report supports the frozen action or compensation in its frozen context. Validators independently repeat the task and must agree on the closed verdict. DAG validation, role checks, immutable plan hash, dependency ordering, cancellation barriers, readiness, and final state are deterministic. Invalid or uncertain semantic results cannot advance the workflow.

Each workflow is creator-scoped and supports at most eight steps. Only the assigned actor can start or report a step; only its owner can activate, cancel, or finish the workflow. Dependency indexes must point to earlier steps, making cycles impossible.

## Local verification

Install the exact versions in `requirements.txt`, run the linter, strict typecheck, and direct test suite. The Windows direct-test shim is test-only and is not deployed.

## Deployment evidence

`deployments/studionet.json` identifies the isolated-wallet submission candidate and records exact on-chain source/ABI readback. A separate full validator flow passed using byte-identical source, as recorded in the manifest. Re-run the release-proof test after any contract or ABI edit; do not submit a source revision whose hash differs from the manifest. StudioNet is chain 61999; Studio-dev chain 61997 is a different network.
