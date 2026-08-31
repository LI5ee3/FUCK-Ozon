import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from pathlib import Path

_failures = {}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return salt, digest


def password_matches(password, salt, expected):
    try:
        actual = password_hash(password, salt)[1]
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def migrate_env_password(path):
    path = Path(path)
    if not path.exists():
        return False
    lines = path.read_text().splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and not line.lstrip().startswith("#"))
    password = values.get("ADMIN_PASSWORD", "")
    if not password or values.get("ADMIN_PASSWORD_HASH"):
        return False
    salt, digest = password_hash(password)
    kept = [line for line in lines if not line.startswith(("ADMIN_PASSWORD=", "ADMIN_PASSWORD_SALT=", "ADMIN_PASSWORD_HASH="))]
    kept += [f"ADMIN_PASSWORD_SALT={salt}", f"ADMIN_PASSWORD_HASH={digest}"]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(kept) + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return True


def login_limited(key, now=None):
    now = time.time() if now is None else now
    # ponytail: scan the small login failure map; use timed eviction if login volume grows.
    for address, attempts in list(_failures.items()):
        while attempts and attempts[0] < now - 300:
            attempts.popleft()
        if not attempts:
            _failures.pop(address, None)
    return len(_failures.get(key, ())) >= 5


def record_login_failure(key, now=None):
    _failures.setdefault(key, deque()).append(time.time() if now is None else now)


def clear_login_failures(key):
    _failures.pop(key, None)
