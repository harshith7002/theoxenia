"""Audited, scoped backports for the pinned turboSETI 2.3.2 serial CPU search.

The upstream function is compiled with two exact expression replacements: use
N-1 sample intervals when counting drift blocks, and format the scalar hit count.
Its installed source must match the audited SHA-256 before either change applies.
No dependency file on disk is modified. The original function is restored even
when a search fails. Calls through this adapter are serialized because upstream
uses module globals; direct concurrent turboSETI calls are unsupported.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any

AUDITED_SOURCE_SHA256 = "5589bfa96ea2294ffa6abdf0b72780af4fd8580dd2a9eda81ffe76dd1bc6a0ea"
COMPATIBILITY_ID = "theoxenia-turboseti-2.3.2-drift-intervals-v1"
_LOCK = RLock()
_REPLACEMENTS = (
    (
        "datah5_obj.drift_rate_resolution * tsteps_valid)",
        "datah5_obj.drift_rate_resolution * (tsteps_valid - 1))",
    ),
    ('" is: %i" % max_val.total_n_hits)', '" is: %i" % max_val.total_n_hits.item())'),
)


def backport_source(source: str) -> str:
    """Refuse upstream drift before applying the two reviewed substitutions."""
    for old, new in _REPLACEMENTS:
        if source.count(old) != 1:
            raise RuntimeError("turboSETI compatibility source differs from the audited function")
        source = source.replace(old, new)
    return source


@contextmanager
def compatible_search(*, enabled: bool) -> Iterator[None]:
    """Apply the validated backport only during a serialized wrapper search."""
    with _LOCK:
        if not enabled:
            yield
            return
        module: Any = importlib.import_module("turbo_seti.find_doppler.find_doppler")
        source_path = Path(module.__file__)
        if sha256(source_path.read_bytes()).hexdigest() != AUDITED_SOURCE_SHA256:
            raise RuntimeError(
                "turboSETI source checksum is unverified; review the compatibility fix"
            )
        original = module.search_coarse_channel
        source = backport_source(inspect.getsource(original))
        namespace: dict[str, Any] = {}
        # The source is the installed, hash-verified dependency, never user input.
        # Globals remain upstream's live namespace so kernels and passive probes
        # resolve normally. Only the function binding is temporary.
        exec(compile(source, "<theoxenia-turboseti-compat>", "exec"), module.__dict__, namespace)
        module.search_coarse_channel = namespace["search_coarse_channel"]
        try:
            yield
        finally:
            module.search_coarse_channel = original
