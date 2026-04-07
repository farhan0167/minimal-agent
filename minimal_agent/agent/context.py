"""Context — composes a MessageStore with a system prompt and projection strategy.

The Agent interacts with the conversation exclusively through this class.
Storage is append-only; projection is where shaping lives.
"""

from llm.types import Message

from .message_store import MessageStore


class Context:
    def __init__(
        self,
        *,
        system_prompt: str | None = None,
        store: MessageStore | None = None,
    ) -> None:
        self._store = store if store is not None else MessageStore()
        self._system_prompt = system_prompt

    def add(self, msg: Message) -> None:
        """Append a message to the conversation."""
        self._store.append(msg)

    @property
    def store(self) -> MessageStore:
        """Access to the underlying store (for inspection, debugging, persistence)."""
        return self._store

    def get_messages(self) -> list[Message]:
        """Project the stored messages into what the LLM should see this turn.

        Assembles the message list fresh each call:
        1. Prepend system prompt if set.
        2. Apply the projection strategy to stored messages.

        The default projection returns all stored messages unmodified.
        """
        msgs: list[Message] = []
        if self._system_prompt is not None:
            msgs.append(Message(role="system", content=self._system_prompt))
        msgs.extend(self._project())
        return msgs

    def _project(self) -> list[Message]:
        """The projection strategy. Returns the messages the LLM should see.

        Default: return everything. Override point for future strategies
        (sliding window, summarization, token-aware truncation).
        """
        return self._store.messages
