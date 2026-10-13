"""LangChain middleware: only the model sees placeholders; state, tools and user keep real values.

Requires `pip install ezpiizi[langchain]`. The vault is keyed by `runtime.context.conversation_id`,
so sub-agents receiving the same Context share it. Trade-off: checkpoints keep the real values.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from ezpiizi.detection import check_mode
from ezpiizi.pseudonymise import context_words, pseudonymise_content, pseudonymise_text
from ezpiizi.vault import PLACEHOLDER, PiiVault, vault_for

log = logging.getLogger(__name__)

# Detection is CPU/GPU work (60-430 ms per new message): run on the event loop, it blocks every other
# conversation of the server. One dedicated thread: the models are only used from that thread, and
# pseudonymisation of the vaults happens in one place. Other GPU work of the app (embeddings) must use
# this thread too: two threads submitting Metal work at once crash the process on a Mac (MTLCommandBuffer).
PII_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pii")


async def run_pii(fn, *args):
    """Run a pseudonymisation function off the event loop, in the PII thread."""
    return await asyncio.get_running_loop().run_in_executor(PII_EXECUTOR, partial(fn, *args))


def _map_strings(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: _map_strings(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_strings(v, fn) for v in obj]
    return obj


def _map_content(content, fn):
    """A message's content is a string or a list of blocks (MCP tool results: [{"type": "text", ...}])."""
    if isinstance(content, str):
        return fn(content)
    if isinstance(content, list):
        return [fn(b) if isinstance(b, str)
                else {**b, "text": fn(b["text"])} if isinstance(b, dict) and isinstance(b.get("text"), str)
                else b
                for b in content]
    return content


def neutralise(text: str) -> str:
    """Placeholder-like text from outside (typed by the user, or in tool data) is not ours:
    <PERSON_1> -> ‹PERSON_1›, so restore() never turns it into a real value."""
    return PLACEHOLDER.sub(lambda m: f"‹{m.group(1)}›", text)


def _text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b if isinstance(b, str) else b.get("text", "") for b in content
                        if isinstance(b, (str, dict)))
    return None


class PseudonymisationMiddleware(AgentMiddleware):
    """Pseudonymises every model call of the agent and restores its answer.

    mode  "tracer-alone" (default): PII-Tracer alone, every label (dates, URLs and secrets too), no filters
          "tracer": Presidio + PII-Tracer combined (checksums, trimming, typing, filters)
          "presidio": Presidio alone, no model
    The model loads on the first call; call ezpiizi.detection.prepare(mode) at startup to load it earlier.
    """

    def __init__(self, mode: str = "tracer-alone"):
        super().__init__()
        self.mode = check_mode(mode)

    def _pseudonymise(self, msg: BaseMessage, vault: PiiVault, previous: BaseMessage | None) -> BaseMessage:
        if isinstance(msg, ToolMessage):
            return msg.model_copy(update={"content": _map_content(
                msg.content, lambda t: pseudonymise_content(neutralise(t), vault, self.mode))})
        if isinstance(msg, HumanMessage):
            prev = _text(previous.content) if isinstance(previous, AIMessage) else None
            context = context_words(prev) if prev else None
            return msg.model_copy(update={"content": _map_content(
                msg.content, lambda t: pseudonymise_text(neutralise(t), vault, context, self.mode))})
        if isinstance(msg, AIMessage):
            return msg.model_copy(update={
                "content": _map_content(msg.content, lambda t: pseudonymise_text(t, vault, mode=self.mode)),
                "tool_calls": [{**tc, "args": _map_strings(tc["args"],
                                                           lambda s: pseudonymise_text(s, vault, mode=self.mode))}
                               for tc in msg.tool_calls],
            })
        return msg

    def _pseudonymise_all(self, msgs: list[BaseMessage], vault: PiiVault) -> list[BaseMessage]:
        return [self._pseudonymise(m, vault, msgs[i - 1] if i else None) for i, m in enumerate(msgs)]

    @staticmethod
    def _restore(msg: BaseMessage, vault: PiiVault) -> BaseMessage:
        if not isinstance(msg, AIMessage):
            return msg
        return msg.model_copy(update={
            "content": _map_content(msg.content, vault.restore),
            "tool_calls": [{**tc, "args": _map_strings(tc["args"], vault.restore)} for tc in msg.tool_calls],
        })

    async def awrap_model_call(self, request, handler):
        vault = vault_for(request.runtime.context.conversation_id)
        msgs = request.messages
        safe = await run_pii(self._pseudonymise_all, msgs, vault)
        if safe:
            log.debug("model sees: %s", str(safe[-1].content)[:300])
        response = await handler(request.override(messages=safe))
        return ModelResponse(result=[self._restore(m, vault) for m in response.result],
                             structured_response=response.structured_response)
