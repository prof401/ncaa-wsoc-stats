"""DiscoveryManager: queue for newly discovered team IDs."""

from collections import deque


class DiscoveryManager:
    """
    Tracks known team IDs and a queue of teams to scrape.
    When an opponent is found that isn't in known_ids, add to queue.
    """

    def __init__(self, known_ids: set[str] | None = None):
        """
        Args:
            known_ids: Initial set of team IDs already known (from seed + existing CSV).
        """
        self._known: set[str] = set(known_ids or ())
        self._queue: deque[str] = deque()

    def add_if_new(self, team_id: str) -> bool:
        """
        Add team_id to the discovery queue if not already known.

        Args:
            team_id: NCAA team ID.

        Returns:
            True if newly added to queue, False if already known.
        """
        if not team_id:
            return False
        if team_id in self._known:
            return False
        self._known.add(team_id)
        self._queue.append(team_id)
        return True

    def add_seed_ids(self, team_ids: list[str]) -> None:
        """
        Add seed team IDs to the queue (all are "new" for processing).
        Marks them as known so they won't be re-added from opponent discovery.

        Args:
            team_ids: List of team IDs from rankings seed.
        """
        for tid in team_ids:
            if tid and tid not in self._known:
                self._known.add(tid)
                self._queue.append(tid)

    def pop_next(self) -> str | None:
        """
        Pop the next team ID from the queue.

        Returns:
            Team ID, or None if queue is empty.
        """
        if not self._queue:
            return None
        return self._queue.popleft()

    def is_empty(self) -> bool:
        """Return True if the queue has no more teams to process."""
        return len(self._queue) == 0

    def __len__(self) -> int:
        """Number of teams remaining in the queue."""
        return len(self._queue)
