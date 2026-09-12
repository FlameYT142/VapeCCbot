import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Антифлуд. Банит только за систематический флуд, не за отдельные нажатия.
    """
    def __init__(
        self,
        per_user_interval: float = 0.6,
        burst_window: float = 10.0,
        burst_limit: int = 20,
        global_per_second: int = 30,
        ban_duration: float = 60.0,
        ban_threshold: int = 10,
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
        # Доверенные (админы) — не проверяем
        self._trusted = set()

    # ---------- доверенные ----------
    def set_trusted(self, user_ids):
        """Установить список ID, которых НЕ проверять (админы)."""
        self._trusted = set(user_ids)

    def add_trusted(self, user_id):
        self._trusted.add(user_id)

    def remove_trusted(self, user_id):
        self._trusted.discard(user_id)

    # ---------- глобальный лимит ----------
    def _cleanup_global(self, now: float):
        self._global_actions = [t for t in self._global_actions if now - t < 1.0]

    def check(self, user_id: int):
        now = time.time()

        # Админов не трогаем
        if user_id in self._trusted:
            return True, 'trusted'

        # 0. Бан
        banned_until = self._banned.get(user_id, 0)
        if now < banned_until:
            left = int(banned_until - now)
            logger.warning(f"🚫 Забанен user={user_id}, осталось {left} сек")
            return False, 'banned'

        # 1. Слишком часто — НЕ считаем нарушением, просто пропускаем
        last = self._last_action.get(user_id, 0)
        if now - last < self.per_user_interval:
            return False, 'too_fast'

        # 2. Burst — сколько действий за последние N секунд
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
        """Считаем нарушения, баним только при систематическом флуде."""
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

    def unban(self, user_id: int):
        """Снять бан вручную."""
        self._banned.pop(user_id, None)
        self._violations.pop(user_id, None)
        self._burst.pop(user_id, None)
        logger.info(f"✅ user={user_id} разбанен вручную")

    def reset(self, user_id: int):
        self._last_action.pop(user_id, None)
        self._burst.pop(user_id, None)
        self._violations.pop(user_id, None)
        self._banned.pop(user_id, None)


limiter = RateLimiter(
    per_user_interval=0.6,
    burst_window=10.0,
    burst_limit=20,
    global_per_second=30,
    ban_duration=60.0,
    ban_threshold=10,
)
