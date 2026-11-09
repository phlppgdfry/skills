# Offline Tool Contract Testing

Use this path when the user wants to test the application behind an agent tool without a live conversation, credentials or paid evaluations. It does not require API-key setup or onboarding.

## Separate two kinds of evidence

Provider tool-call tests check whether the agent selects a tool and supplies expected parameters. They do not by themselves prove that your implementation validates those arguments, enforces authorization, handles backend failures or returns the requested record.

Test that application boundary locally first. Then use provider evaluations separately for model selection, spoken responses, language and conversation grounding. A passing local fixture is not a model success rate.

## Runnable Python example

The bundled files use Python 3.10+ and standard-library `unittest`, with synthetic data and fake backends only:

```bash
python3 -m unittest discover -s agents/scripts -p 'test_tool_contracts.py' -v
```

Run from the repository root. In an installed skill, use the absolute path to this skill's `scripts` directory as the discovery directory. See [the implementation](../scripts/tool_contracts.py) and [the tests](../scripts/test_tool_contracts.py). They do not load environment variables, import an SDK or make network calls.

The handler accepts `lookup_order` and `request_review` with exactly one string `reference` in the format `ORD-0001`. Its injected backend implements `lookup(reference)` and `request_review(reference)`. The former returns either `None` for an unknown record or exactly `reference` and an allowlisted `status`; the latter returns `reference`, `review_id` and `status: pending_review`.

`Context` carries the allowed reference and review capability. Construct it from an authenticated application session and trusted authorization policy. Never construct it from a tool argument, an LLM instruction, a spoken identity claim or an unverified dynamic variable. A client-side context is not a security boundary for server operations: enforce permission again in the trusted service.

## What to check

| Boundary | Regression | Expected behavior |
|----------|------------|-------------------|
| Arguments | Wrong type, missing/extra field, trailing newline, wrong reference | Reject before calling the backend |
| Facts | Missing/null/unknown status, extra fields or mismatched reference | Return `invalid_response`, never grounded success |
| Source state | No matching record versus a timeout | Preserve `unknown` versus `unavailable` |
| Authorization | `authorized: true` supplied by the model | Reject the extra argument; it cannot grant a capability |
| Review state | Backend reports `approved` for a review proposal | Reject; only `pending_review` is accepted |
| Recovery | Successful lookup followed by a timeout | Return a fresh failure, never reuse stale known facts |
| Error privacy | Exception includes private backend details | Return a bounded error code, not the exception text |

Use fake backends to assert both the returned outcome and that forbidden requests never call the backend. Do not test only that a tool name appears in a trace. Match each returned reference to the requested and authorized reference, even when writing mocks for provider simulations.

## Connecting to ElevenAgents

[Client-tool events](https://elevenlabs.io/docs/eleven-agents/customization/events/client-events) provide tool names, call IDs and parameters. Route parameters to an application handler and serialize its result through the supported client-tool response API, or call equivalent logic in your authenticated webhook service. Keep provider transport handling and tool-call IDs in that adapter rather than treating this local result dictionary as an ElevenLabs wire payload.

The local example does not create agent configuration or implement a conversation adapter. Refer to [Client Tools](client-tools.md) for definitions and registration, and the Testing Agents section of the main skill for provider evaluations.

## Production limits

The injected test backend raises `TimeoutError`; the example does not implement an HTTP deadline. Add actual bounded I/O, authenticated transport, record/tenant scope, rate limits, durable audit logs and idempotency for writes in a real service. A timed-out review request can already have reached the backend: do not automatically retry it without an idempotency strategy or a status check.

Local assertions cannot prove prompt-injection resistance, model grounding, multilingual quality or live voice behavior. Keep those claims separate and respect the user's budget before invoking provider evaluations.
