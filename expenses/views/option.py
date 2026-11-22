import json

from django.http import JsonResponse

from ..data_services.options import OptionError
from .expense import ExpensesBaseView


def _name(request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, ValueError):
        raise OptionError("Invalid JSON")
    return data.get("name") if isinstance(data, dict) else None


class _OptionView(ExpensesBaseView):
    """Turns OptionError into a JSON error with its status code."""

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except OptionError as exc:
            return JsonResponse({"error": str(exc), **exc.extra}, status=exc.status)


class OptionsListView(_OptionView):
    """GET → the person's categories, sources and modes (with how many expenses use each)."""

    def get(self, request):
        if not self.service:
            return self._creds_error()
        return JsonResponse(self.service.dl.options())


class OptionsCreateView(_OptionView):
    """POST {name} → add to one list (`categories`, `sources` or `modes`)."""

    def post(self, request, kind):
        if not self.service:
            return self._creds_error()
        option, created = self.service.dl.add_option(kind, _name(request))
        return JsonResponse(
            {"ok": True, "created": created, "option": {"id": option.pk, "name": option.name}},
            status=201 if created else 200,
        )


class OptionDetailView(_OptionView):
    def patch(self, request, kind, option_id):
        """Rename, carrying the new name onto the expenses that use it."""
        if not self.service:
            return self._creds_error()
        result = self.service.dl.rename_option(kind, option_id, _name(request))
        opt = result["option"]
        return JsonResponse({"ok": True, "option": {"id": opt.pk, "name": opt.name},
                             "expenses_updated": result["expenses_updated"]})

    def delete(self, request, kind, option_id):
        """Stop offering it. If expenses use it, send {"replace_with": "<name>"} (or
        ?replace_with=) — they are moved to that name first. Without it, an entry
        that is in use is refused with 409 (needs_replacement, uses)."""
        if not self.service:
            return self._creds_error()
        replace_with = request.GET.get("replace_with")
        if replace_with is None and request.body:
            try:
                body = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                raise OptionError("Invalid JSON")
            if isinstance(body, dict):
                replace_with = body.get("replace_with")
        result = self.service.dl.delete_option(kind, option_id, replace_with)
        return JsonResponse({"ok": True, **result})
