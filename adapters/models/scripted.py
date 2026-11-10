"""A deterministic chat client backed by prepared answer cards."""


class ScriptedClient:
    """Return pre-written replies in their supplied order."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = iter(tuple(replies))

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the next reply, raising a clear error when exhausted."""
        try:
            return next(self._replies)
        except StopIteration:
            raise RuntimeError("ScriptedClient has no replies remaining") from None
