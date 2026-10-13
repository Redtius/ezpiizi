# LangChain integration

## The middleware

```python
from ezpiizi import prepare
from ezpiizi.middleware import PseudonymisationMiddleware

prepare("tracer-alone")                           # at startup, once: load the detector now (optional)
agent = create_agent(model, tools, middleware=[PseudonymisationMiddleware()], context_schema=Context)
await agent.ainvoke({"messages": [...]}, context=Context(conversation_id="C001:3f2a...", ...))
```

### Choosing the detector

| `mode=` | Detector | Needs |
|---|---|---|
| `"tracer-alone"` (default) | PII-Tracer only, every label (names, addresses, ids, dates, URLs, secrets) | `ezpiizi[tracer]` |
| `"tracer"` | Presidio + PII-Tracer: checksums, trimming, typing, filters (see [detection](detection.md)) | `ezpiizi[tracer]` |
| `"presidio"` | Presidio only: no model, a few ms per message, weaker on names | — |

```python
PseudonymisationMiddleware()                  # PII-Tracer only
PseudonymisationMiddleware(mode="tracer")     # both
PseudonymisationMiddleware(mode="presidio")
```

The mode belongs to the middleware, not to the process: two agents can use two modes, and the global
mode set by `enable_tracer()` is ignored. An unknown mode raises `ValueError` at construction.
Without `prepare()`, the model loads on the first message (~4 s).

`tracer-alone` masks the most (dates and URLs too), but has none of the rules of the `tracer` mode: no IBAN
checksum, spans are not trimmed (`DNI 12345678Z` may be masked with the word `DNI`), identifiers are typed
`ACCOUNT`, and `configure()` allow-list words and identifier patterns are **not** applied. If your app has
its own ids (`A1001`, `CLM-2026-0412`) that the model must see, use `mode="tracer"`.

`PseudonymisationMiddleware` wraps every **model call** of the agent (`awrap_model_call`):

```text
state (real values) ──► messages pseudonymised ──► model ──► answer + tool-call arguments restored ──► state
```

| Message | Before the model call |
|---|---|
| customer message | pseudonymised as text, with the previous assistant message as context |
| tool result | pseudonymised as JSON (known keys) or text; MCP content blocks (`[{"type": "text"}]`) included |
| assistant message (history) | pseudonymised again, tool-call arguments included |

After the call, the answer **and the arguments of its tool calls** are restored: a tool asked for
`<MA_IBAN_1>` receives the real IBAN. The graph state, the checkpoints and the customer only see real
values.

The vault is `vault_for(runtime.context.conversation_id)`. Sub-agents receiving the same `Context` share
it, so a placeholder means the same thing across agents. Scope the id to the customer
(`"C001:<conversation>"`): two customers must never share a vault.

### Order with other middleware

The first middleware in the list is the outermost. Put model-call middleware that must see placeholders
**after** this one, for example a fallback model:

```python
middleware=[prompt_mw, PseudonymisationMiddleware(), ModelFallbackMiddleware(backup_model)]
```

Middleware that call a model **in their own hooks** (`before_model`, `before_agent`), such as LangChain's
`SummarizationMiddleware`, bypass it: their model receives real values. Pseudonymise those calls
yourself (below).

## LLM calls outside an agent

For a guard, a summariser or any direct model call, use the same vault and the same thread:

```python
from ezpiizi.middleware import neutralise, run_pii
from ezpiizi.pseudonymise import pseudonymise_text
from ezpiizi.vault import vault_for

vault = vault_for(conversation_id)
safe = await run_pii(pseudonymise_text, neutralise(text), vault)
answer = await model.ainvoke([..., HumanMessage(safe)])
real = vault.restore(answer.content)
```

## Threading

Detection is CPU/GPU work: 60–430 ms per new message with PII-Tracer. Run on the event loop, it would
block every other request of an async server. The middleware therefore runs it in **one dedicated
thread** (`PII_EXECUTOR`), reached with `run_pii(fn, *args)`:

- the event loop stays free (other conversations keep streaming);
- only that thread uses the PII models;
- on an Apple GPU, two threads submitting Metal work at once crash the process
  (`MTLCommandBuffer` assertion). **Run any other GPU inference of the application (embeddings,
  rerankers) through `run_pii` too.**

Throughput is bounded by that single thread. See [Limitations](limitations.md).

## What stays outside

The middleware protects what the **LLM provider** receives. It does not mask:
- the graph state and checkpoints (real values, by design: tools and the customer need them);
- tracing (OpenInference / Phoenix spans of agent and tool steps contain real values; only LLM spans
  are pseudonymised).

Protect those with encryption at rest, retention policies and span masking.
