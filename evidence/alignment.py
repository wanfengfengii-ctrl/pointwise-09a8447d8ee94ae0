from collections.abc import Iterable


def _max_chain(eligible: frozenset[tuple[int, int]], old_count: int, new_count: int,
               banned: tuple[int, int] | None = None) -> int:
    """Longest chain of eligible pairs with old and new positions strictly increasing."""
    suffix = [[0] * (new_count + 1) for _ in range(old_count + 1)]
    for old_index in range(old_count - 1, -1, -1):
        row, next_row = suffix[old_index], suffix[old_index + 1]
        for new_index in range(new_count - 1, -1, -1):
            best = row[new_index + 1] if row[new_index + 1] > next_row[new_index] else next_row[new_index]
            pair = (old_index, new_index)
            if pair in eligible and pair != banned:
                candidate = 1 + next_row[new_index + 1]
                if candidate > best:
                    best = candidate
            row[new_index] = best
    return suffix[0][0]


def _reachable_bounds(eligible: frozenset[tuple[int, int]], old_count: int, new_count: int):
    """Longest chain lengths inside every prefix and every suffix rectangle."""
    prefix = [[0] * (new_count + 1) for _ in range(old_count + 1)]
    for old_index in range(old_count):
        current, previous = prefix[old_index + 1], prefix[old_index]
        for new_index in range(new_count):
            best = current[new_index] if current[new_index] > previous[new_index + 1] else previous[new_index + 1]
            if (old_index, new_index) in eligible:
                candidate = 1 + previous[new_index]
                if candidate > best:
                    best = candidate
            current[new_index + 1] = best
    suffix = [[0] * (new_count + 1) for _ in range(old_count + 1)]
    for old_index in range(old_count - 1, -1, -1):
        row, next_row = suffix[old_index], suffix[old_index + 1]
        for new_index in range(new_count - 1, -1, -1):
            best = row[new_index + 1] if row[new_index + 1] > next_row[new_index] else next_row[new_index]
            if (old_index, new_index) in eligible:
                candidate = 1 + next_row[new_index + 1]
                if candidate > best:
                    best = candidate
            row[new_index] = best
    return prefix, suffix


def unambiguous_pairs(old_names: tuple[str, ...], new_names: tuple[str, ...],
                      eligible: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Return the pairs present in *every* maximum-cardinality order-preserving alignment.

    Every stage of both revisions takes part in the alignment, including stages
    without a reading.  A pair is pinned down by the evidence only when it sits
    inside some maximum alignment *and* removing it lowers the maximum
    cardinality; then no maximum alignment can route either side elsewhere.
    Reading values never influence the alignment, so equal source readings on
    competing stages do not make an ambiguous pair carryable.
    """
    old_positions = {name: index for index, name in enumerate(old_names)}
    new_positions = {name: index for index, name in enumerate(new_names)}
    eligible_positions = frozenset(
        (old_positions[old_name], new_positions[new_name])
        for old_name, new_name in eligible
    )
    old_count, new_count = len(old_names), len(new_names)
    if not eligible_positions:
        return ()
    total = _max_chain(eligible_positions, old_count, new_count)
    prefix, suffix = _reachable_bounds(eligible_positions, old_count, new_count)
    pinned = []
    for old_index, new_index in eligible_positions:
        through = prefix[old_index][new_index] + 1 + suffix[old_index + 1][new_index + 1]
        if through != total:
            continue
        if _max_chain(eligible_positions, old_count, new_count, banned=(old_index, new_index)) < total:
            pinned.append((old_index, new_index))
    pinned.sort(key=lambda pair: pair[1])
    return tuple((old_names[old_index], new_names[new_index]) for old_index, new_index in pinned)
