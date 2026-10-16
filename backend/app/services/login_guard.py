"""Batas percobaan login (aplikasi berjalan di IP publik): mencegah tebak password tanpa batas.

- Email yang sama dari IP yang sama: 5 kali salah -> dikunci 15 menit.
- Email yang sama dari IP mana pun: 20 kali salah -> dikunci 15 menit.
Login yang berhasil menghapus hitungan untuk email itu. Disimpan di memori proses (server satu proses).
"""
import threading
import time

WINDOW_SECONDS = 15 * 60
MAX_PER_IP_EMAIL = 5
MAX_PER_EMAIL = 20

_failures: dict[tuple[str, str], list[float]] = {}
_lock = threading.Lock()


def _recent(key: tuple[str, str], now: float) -> list[float]:
    times = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
    if times:
        _failures[key] = times
    else:
        _failures.pop(key, None)
    return times


def retry_after(ip: str, email: str) -> int:
    """Detik sampai boleh mencoba lagi; 0 bila tidak sedang dikunci."""
    now = time.time()
    with _lock:
        for key, limit in (((ip, email), MAX_PER_IP_EMAIL), (("*", email), MAX_PER_EMAIL)):
            times = _recent(key, now)
            if len(times) >= limit:
                return int(WINDOW_SECONDS - (now - times[-limit])) + 1
    return 0


def record_failure(ip: str, email: str) -> None:
    now = time.time()
    with _lock:
        for key in ((ip, email), ("*", email)):
            _failures.setdefault(key, []).append(now)


def record_success(email: str) -> None:
    with _lock:
        for key in [k for k in _failures if k[1] == email]:
            _failures.pop(key, None)


def reset() -> None:
    with _lock:
        _failures.clear()
