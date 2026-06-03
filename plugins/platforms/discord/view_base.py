from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("miho_plugins.discord_platform.adapter")

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    discord = None
    DISCORD_AVAILABLE = False


def _component_check_auth(
    interaction,
    allowed_user_ids: Optional[set],
    allowed_role_ids: Optional[set],
) -> bool:
    user_set = allowed_user_ids or set()
    role_set = allowed_role_ids or set()
    has_users = bool(user_set)
    has_roles = bool(role_set)
    if not has_users and not has_roles:
        return True

    user = getattr(interaction, "user", None)
    if user is None:
        return False

    if has_users:
        try:
            uid = str(user.id)
        except AttributeError:
            uid = ""
        if uid and uid in user_set:
            return True

    if has_roles:
        roles_attr = getattr(user, "roles", None)
        if roles_attr is None:
            return False
        try:
            user_role_ids = {getattr(r, "id", None) for r in roles_attr}
        except TypeError:
            return False
        if user_role_ids & role_set:
            return True

    return False
