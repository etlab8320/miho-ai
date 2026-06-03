from __future__ import annotations

import importlib

from . import approval_views, clarify_view, model_picker_view, update_views, view_base
from .view_base import _component_check_auth

VIEW_NAMES = (
    "ExecApprovalView",
    "SlashConfirmView",
    "UpdatePromptView",
    "UpdateAvailableView",
    "ModelPickerView",
    "ClarifyChoiceView",
)


def define_discord_view_classes() -> None:
    missing = any(globals().get(name) is None for name in VIEW_NAMES)
    if missing:
        importlib.reload(view_base)
        for module in (approval_views, update_views, model_picker_view, clarify_view):
            importlib.reload(module)
    _refresh_exports()


def _refresh_exports() -> None:
    globals().update({
        "ExecApprovalView": approval_views.ExecApprovalView,
        "SlashConfirmView": approval_views.SlashConfirmView,
        "UpdatePromptView": update_views.UpdatePromptView,
        "UpdateAvailableView": update_views.UpdateAvailableView,
        "ModelPickerView": model_picker_view.ModelPickerView,
        "ClarifyChoiceView": clarify_view.ClarifyChoiceView,
    })


_refresh_exports()
