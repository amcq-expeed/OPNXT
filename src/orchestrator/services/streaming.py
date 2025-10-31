# --- opnxt-stream ---
from typing import AsyncIterator, Iterator, Dict, Any, Iterable


def iter_as_async(it: Iterable[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
    async def gen() -> AsyncIterator[Dict[str, Any]]:
        for x in it:
            yield x

    return gen()
