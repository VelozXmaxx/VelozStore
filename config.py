import os

def _list_from_env(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]

def _list_ints_from_env(name: str) -> list[int]:
    vals = _list_from_env(name)
    out = []
    for v in vals:
        try:
            out.append(int(v))
        except ValueError:
            continue
    return out

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Owner
OWNER_ID = int(os.getenv("OWNER_ID", "0")) or None
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "").lstrip("@") or None  # preferred for deep links

# Social links
SOCIAL_YT = os.getenv("SOCIAL_YT", "https://www.youtube.com/@caperftbl")
SOCIAL_IG = os.getenv("SOCIAL_IG", "https://www.instagram.com/onlyveloz_?igsh=bjl4MjJ3ejVxOXhn")

# Required channels, can be @usernames or numeric IDs as strings (comma-separated)
REQUIRED_CHANNELS = _list_from_env("REQUIRED_CHANNELS")

# Admins
MAIN_ADMIN_ID = int(os.getenv("MAIN_ADMIN_ID", "0")) or None
SECONDARY_ADMINS = _list_ints_from_env("SECONDARY_ADMINS")

# Promo toggle
START_SOCIAL_PROMO = os.getenv("START_SOCIAL_PROMO", "true").lower() in ("1", "true", "yes")
