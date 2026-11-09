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
            return JsonResponse({"error": str(exc)}, status=exc.status)


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
        """Stop offering it. Expenses already saved with it are not changed."""
        if not self.service:
            return self._creds_error()
        self.service.dl.delete_option(kind, option_id)
        return JsonResponse({"ok": True})
