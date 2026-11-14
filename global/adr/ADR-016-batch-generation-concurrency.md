# ADR-016: Batch Generation Concurrency & Client-Side Orchestration

## Status
Accepted

## Context
With the introduction of the "Multiselect Casting Room," users can now request image and voice asset generation for multiple characters simultaneously. Generative tasks (e.g., Stable Diffusion, LLM inferences, TTS) are resource-intensive. Sending unbounded parallel requests to the backend API could easily exhaust GPU compute capacity, cause rate-limiting from external vendors, and degrade overall cluster health. We must establish a safe and scalable pattern for handling batch operations from the frontend UI.

## Decision
We will employ **Client-Side Bounded Concurrency** for generative batches in the frontend, rather than building a monolithic `/generate-bulk` backend endpoint.

1. **Concurrency Cap:** The client will process generation batches using a maximum concurrency limit (e.g., max 3 active in-flight requests at any given time).
2. **Error Resilience:** Batch execution will bypass failures. If one item in the batch errors, the processor will record the failure status and *continue* to process the remaining queue.
3. **Commit Phase Orchestration:** When persisting the finalized assets to the database (the Roster Bridge step), the client will use `Promise.allSettled()` to dispatch requests. This ensures each item commits independently, and a failure for one character does not crash the commit phase for the rest.

## Rationale
- **Why bounded concurrency?** It protects backend resources (like the A1111 GPU worker queue) from overwhelming spikes without requiring immediate backend rate-limiting middleware.
- **Why client-side orchestration over a bulk API endpoint?** Developing a `/generate-bulk` endpoint pushes batch state tracking and connection management complexity to the backend, necessitating complex job polling and webhook mechanisms. Keeping orchestration on the client ensures the UI is tightly coupled to the real-time status of each item (`idle -> generating -> done -> error`) with minimal backend change.
- **Why not `Promise.all`?** `Promise.all` fails fast. If a user casts 10 characters and the 9th fails, `Promise.all` will reject, complicating recovery for the 8 successful generations. Using bounded chunking + `Promise.allSettled()` allows partial successes, which are highly desirable for lengthy generative pipelines. Note that `Promise.allSettled()` itself fires all promises at once, so the actual rate-limiting requires explicit chunking logic prior to the commit phase.

## Consequences
- **Positive:** Immediate protection against resource exhaustion. Users get a transparent, item-by-item status breakdown during long batch operations. Partial successes can be persisted.
- **Negative:** If a user closes the browser window mid-batch, the generation queue is halted because the client is the orchestrator.
- **When to Revisit:** If generative tasks become extremely long-running (e.g., taking minutes per character), client-side orchestration becomes brittle due to browser timeouts and accidental closures. At that scale, we must migrate to a true asynchronous backend batching system with long-polling or Server-Sent Events (SSE).
