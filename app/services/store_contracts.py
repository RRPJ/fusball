"""Focused persistence contracts shared by local and hosted adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from services.domain_models import MatchLifecycleResult, MatchWriteResult, PlayerRating


class LifecycleConflict(ValueError):
    pass


class ReplayParityError(RuntimeError):
    pass


@dataclass(frozen=True)
class WriteStoreConfig:
    db_dir: Path
    database_url: str | None


class PlayerRepository(ABC):
    @abstractmethod
    def list_player_keys(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_player_ratings(self, names: Sequence[str]) -> dict[str, PlayerRating]:
        raise NotImplementedError

    @abstractmethod
    def leaderboard_ratings(self, scope: str) -> dict[str, PlayerRating]:
        raise NotImplementedError

    def missing_players(self, names: Sequence[str]) -> list[str]:
        known = set(self.list_player_keys())
        return [name for name in names if name not in known]


class HistoryRepository(ABC):
    @abstractmethod
    def list_match_lifecycle(
        self,
        limit: int = 50,
        include_voided: bool = True,
    ) -> list[dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def list_match_events(self, match_id: str) -> list[dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def query_h2h(self, p1: str, p2: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def query_team_h2h(self, team1: Sequence[str], team2: Sequence[str]) -> dict:
        raise NotImplementedError

    @abstractmethod
    def query_player_stats(self, scope: str = "all") -> dict[str, dict]:
        raise NotImplementedError

    @abstractmethod
    def query_player_profile(
        self,
        player: str,
        scope: str = "all",
        recent_limit: int = 5,
    ) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def query_rating_snapshots(self, player: str, n: int = 10) -> list[dict]:
        raise NotImplementedError


class MatchWriter(ABC):
    uses_local_lock = True

    @abstractmethod
    def add_player(self, player_name: str) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def submit_match(
        self,
        team1: list[str],
        team2: list[str],
        score1: int,
        score2: int,
        source: str,
        actor_subject: str = "legacy:shared-credential",
        idempotency_key: str | None = None,
    ) -> MatchWriteResult:
        raise NotImplementedError

    @abstractmethod
    def change_match_status(
        self,
        match_id: str,
        target_status: str,
        actor_subject: str,
        reason: str,
        request_id: str,
        expected_version: int | None = None,
    ) -> MatchLifecycleResult:
        raise NotImplementedError


class BaseWriteStore(PlayerRepository, HistoryRepository, MatchWriter):
    """Composite contract retained for the existing phone API composition root."""
