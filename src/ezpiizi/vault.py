import logging
import re
import threading
from collections import Counter

log = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"<([A-Z_]+_\d+)>")
UNKNOWN_PLACEHOLDER = "[information non disponible]"


class PiiVault:
    """placeholder <-> real value for one conversation. In production: an encrypted store with a TTL."""

    def __init__(self):
        self.by_value: dict[tuple[str, str], str] = {}
        self.by_placeholder: dict[str, str] = {}
        self.counters: Counter = Counter()
        self.cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def placeholder_for(self, entity: str, value: str) -> str:
        key = (entity, value.strip())
        with self._lock:
            if key not in self.by_value:
                self.counters[entity] += 1
                placeholder = f"<{entity}_{self.counters[entity]}>"
                self.by_value[key] = placeholder
                self.by_placeholder[placeholder] = value.strip()
            return self.by_value[key]

    def restore(self, text: str) -> str:
        """Unknown placeholders were invented by the model: never shown as data."""
        def replace(m: re.Match) -> str:
            if m.group(0) in self.by_placeholder:
                return self.by_placeholder[m.group(0)]
            log.warning("model invented placeholder %s", m.group(0))
            return UNKNOWN_PLACEHOLDER
        return PLACEHOLDER.sub(replace, text)


VAULTS: dict[str, PiiVault] = {}


def vault_for(conversation_id: str) -> PiiVault:
    return VAULTS.setdefault(conversation_id, PiiVault())
