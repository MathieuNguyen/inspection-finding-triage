"""Running a call across a batch under a ceiling, and reporting what failed.

The contract mirrors the CSV loader's: one run names every problem, so a broken
batch is diagnosed in a single pass rather than one finding at a time.
"""

from __future__ import annotations

import asyncio

import pytest

from triage.llm import BatchError, map_bounded


def _key(item: int) -> str:
    return f"F-{item:04d}"


async def test_results_come_back_in_input_order() -> None:
    """Concurrency must not reorder the batch; a ticket belongs to its finding."""

    async def slower_for_smaller(item: int) -> int:
        await asyncio.sleep((10 - item) / 1000)
        return item * 2

    assert await map_bounded(
        list(range(10)), slower_for_smaller, limit=10, key=_key
    ) == [item * 2 for item in range(10)]


async def test_the_ceiling_is_respected() -> None:
    """Twenty-one findings must not become twenty-one simultaneous requests."""
    in_flight = 0
    peak = 0

    async def watched(item: int) -> int:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.001)
        in_flight -= 1
        return item

    await map_bounded(list(range(20)), watched, limit=3, key=_key)
    assert peak <= 3


async def test_the_ceiling_still_allows_concurrency() -> None:
    """A limit above one must actually overlap, or the batch is serial."""
    peak = 0
    in_flight = 0

    async def watched(item: int) -> int:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1
        return item

    await map_bounded(list(range(8)), watched, limit=4, key=_key)
    assert peak > 1


async def test_every_failure_is_reported_together() -> None:
    """One run names every problem, the way a malformed CSV does."""

    async def fails_on_odd(item: int) -> int:
        if item % 2:
            raise ValueError(f"item {item} is odd")
        return item

    with pytest.raises(BatchError) as caught:
        await map_bounded(list(range(6)), fails_on_odd, limit=2, key=_key)

    error = caught.value
    assert len(error.failures) == 3
    assert error.total == 6
    assert [failure.key for failure in error.failures] == ["F-0001", "F-0003", "F-0005"]
    assert "is odd" in str(error)


async def test_a_failure_is_named_by_its_item() -> None:
    """An anonymous traceback in a batch of twenty-one is not actionable."""

    async def always_fails(item: int) -> int:
        raise RuntimeError("nope")

    with pytest.raises(BatchError, match="F-0007"):
        await map_bounded([7], always_fails, limit=1, key=_key)


async def test_one_failure_does_not_abandon_the_rest() -> None:
    """The batch runs to completion, so the report is of the whole run."""
    attempted: list[int] = []

    async def fails_on_first(item: int) -> int:
        attempted.append(item)
        if item == 0:
            raise ValueError("first")
        return item

    with pytest.raises(BatchError):
        await map_bounded(list(range(5)), fails_on_first, limit=1, key=_key)

    assert sorted(attempted) == [0, 1, 2, 3, 4]


async def test_an_empty_batch_is_not_an_error() -> None:
    async def unreached(item: int) -> int:  # pragma: no cover - never called
        raise AssertionError("an empty batch should call nothing")

    assert await map_bounded([], unreached, limit=4, key=_key) == []


async def test_cancellation_is_not_swallowed() -> None:
    """Cancelling a run must stop it, not be filed as one more failed item."""

    async def cancels(item: int) -> int:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await map_bounded([1], cancels, limit=1, key=_key)
