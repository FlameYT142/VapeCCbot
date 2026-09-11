import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Универсальный антифлуд-лимитер.
      1. Per-user: не чаще N сек между действиями
      2. Per-user burst: до M действий за окно T секунд
      3. Global: не более G действий в секунду для всего бота
      4. Автобан за повторные нарушения
    """

    def __init__(
        self,
        per_user_interval: float = 1.5,
        burst_window: float = 10.0,
        burst_limit: int = 15,
        global_per_second: int = 25,
        ban_duration: float = 300.0,
        ban_threshold: int = 3,
    ):
        self.per_user_interval = per_user_interval
        self.burst_window = burst_window
        self.burst_limit = burst_limit
        self.global_per_second = global_per_second
        self.ban_duration = ban_duration
        self.ban_threshold = ban_threshold

        self._last_action = {}
        self._burst = defaultdict(list)
        self._violations = defaultdict(int)
        self._banned = {}
        self._global_actions = []

    def _cleanup_global(self, now: float):
        self._global_actions = [t for t in self._global_actions if now - t < 1.0]

    def check(self, user_id: int):
        now = time.time()

        # 0. Бан
        banned_until = self._banned.get(user_id, 0)
        if now < banned_until:
            left = int(banned_until - now)
            logger.warning(f"🚫 Забанен user={user_id}, осталось {left} сек")
            return False, 'banned'

        # 1. Интервал между действиями
        last = self._last_action.get(user_id, 0)
        if now - last < self.per_user_interval:
            self._register_violation(user_id, now)
            return False, 'too_fast'

        # 2. Burst-лимит
        burst = self._burst[user_id]
        burst = [t for t in burst if now - t < self.burst_window]
        if len(burst) >= self.burst_limit:
            self._register_violation(user_id, now)
            self._burst[user_id] = burst
            return False, 'burst'
        burst.append(now)
        self._burst[user_id] = burst

        # 3. Глобальный лимит
        self._cleanup_global(now)
        if len(self._global_actions) >= self.global_per_second:
            return False, 'global'
        self._global_actions.append(now)

        self._last_action[user_id] = now
        return True, 'ok'

    def _register_violation(self, user_id: int, now: float):
        self._violations[user_id] += 1
        if self._violations[user_id] >= self.ban_threshold:
            self._banned[user_id] = now + self.ban_duration
            logger.warning(
                f"🔨 user={user_id} ЗАБАНЕН на {self.ban_duration} сек "
                f"(нарушений: {self._violations[user_id]})"
            )

    def is_banned(self, user_id: int) -> bool:
        return time.time() < self._banned.get(user_id, 0)

    def ban_left(self, user_id: int) -> int:
        left = self._banned.get(user_id, 0) - time.time()
        return max(0, int(left))

    def reset(self, user_id: int):
        self._last_action.pop(user_id, None)
        self._burst.pop(user_id, None)
        self._violations.pop(user_id, None)
        self._banned.pop(user_id, None)


limiter = RateLimiter(
    per_user_interval=1.5,
    burst_window=10.0,
    burst_limit=15,
    global_per_second=25,
    ban_duration=300.0,
    ban_threshold=3,
)
