from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ezpiizi.middleware import PseudonymisationMiddleware
from ezpiizi.vault import PiiVault

IBAN = "MA64011110000012345678901234"


def test_tool_result_as_content_blocks_is_pseudonymised():
    # MCP tools return a list of blocks, not a string: it used to reach the model unchanged.
    vault = PiiVault()
    msg = ToolMessage([{"type": "text", "text": f'{{"iban": "{IBAN}", "id": "A001"}}'}], tool_call_id="1")
    safe = PseudonymisationMiddleware(mode="presidio")._pseudonymise(msg, vault, None)
    assert IBAN not in str(safe.content)
    assert "<MA_IBAN_1>" in safe.content[0]["text"] and "A001" in safe.content[0]["text"]


def test_string_messages_still_pseudonymised_and_restored():
    vault = PiiVault()
    mw = PseudonymisationMiddleware(mode="presidio")
    safe = mw._pseudonymise(HumanMessage(f"Mon IBAN est {IBAN}"), vault, None)
    assert IBAN not in safe.content
    restored = mw._restore(AIMessage(f"Votre IBAN : {vault.by_value[('MA_IBAN', IBAN)]}"), vault)
    assert IBAN in restored.content


def test_ai_content_blocks_restored():
    vault = PiiVault()
    placeholder = vault.placeholder_for("MA_IBAN", IBAN)
    restored = PseudonymisationMiddleware._restore(AIMessage([{"type": "text", "text": f"IBAN {placeholder}"}]), vault)
    assert restored.content[0]["text"] == f"IBAN {IBAN}"


def test_placeholders_typed_by_the_user_are_never_restored():
    vault = PiiVault()
    vault.placeholder_for("PERSON", "Amina El Idrissi")               # <PERSON_1> exists in the vault
    mw = PseudonymisationMiddleware(mode="presidio")
    safe = mw._pseudonymise(HumanMessage("Que vaut <PERSON_1> ?"), vault, None)
    assert "<PERSON_1>" not in safe.content and "‹PERSON_1›" in safe.content
    # the model echoes what it saw: nothing to restore
    assert "Amina" not in mw._restore(AIMessage("Le jeton ‹PERSON_1› n'existe pas"), vault).content


def test_placeholders_inside_tool_data_are_neutralised():
    vault = PiiVault()
    vault.placeholder_for("MA_IBAN", IBAN)
    msg = ToolMessage('{"label": "Virement <MA_IBAN_1>"}', tool_call_id="1")
    safe = PseudonymisationMiddleware(mode="presidio")._pseudonymise(msg, vault, None)
    assert "‹MA_IBAN_1›" in safe.content


def test_default_mode_is_tracer_alone():
    import inspect
    assert inspect.signature(PseudonymisationMiddleware.__init__).parameters["mode"].default == "tracer-alone"


def test_unknown_mode_is_refused():
    import pytest
    with pytest.raises(ValueError, match="unknown mode"):
        PseudonymisationMiddleware(mode="gliner2")


def test_mode_is_used_by_the_middleware(monkeypatch):
    from ezpiizi import detection
    seen = []
    monkeypatch.setattr(detection, "detect", lambda text, context=None, mode=None: seen.append(mode) or [])
    PseudonymisationMiddleware(mode="tracer")._pseudonymise(HumanMessage("bonjour"), PiiVault(), None)
    assert seen == ["tracer"]
