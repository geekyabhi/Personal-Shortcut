import json

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .data_layer import BlogsDataLayer
from .service import BlogsService


class BlogsBaseView(View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        data_layer = BlogsDataLayer.from_env()
        if data_layer.is_configured:
            self.service = BlogsService(data_layer)
        else:
            self.service = None

    def _creds_error(self):
        return JsonResponse({"error": "Notion credentials not configured"}, status=500)

    @staticmethod
    def _api_error(exc):
        try:
            message = exc.response.text
        except AttributeError:
            message = str(exc)
        return JsonResponse({"error": message}, status=502)


class BlogsDashboardView(View):
    def get(self, request):
        return render(request, "blogs/dashboard.html")


class BlogsStatsView(BlogsBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error()
        try:
            stats = self.service.get_stats()
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse(stats)


class ReadBlogsListView(BlogsBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error()
        try:
            result = self.service.list_read(
                status=request.GET.get("status", ""),
                q=request.GET.get("q", "").lower(),
            )
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse(result)


class ReadBlogsCreateView(BlogsBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error()
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            page_id = self.service.create_read(
                topic=body.get("topic", ""),
                status=body.get("status", ""),
                url=body.get("url", ""),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse({"ok": True, "page_id": page_id})


class ReadBlogsUpdateView(BlogsBaseView):
    def patch(self, request, page_id):
        if self.service is None:
            return self._creds_error()
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            self.service.update_read(page_id, body)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse({"ok": True})


class ReadBlogsDeleteView(BlogsBaseView):
    def post(self, request, page_id):
        if self.service is None:
            return self._creds_error()
        try:
            self.service.delete_read(page_id)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse({"ok": True})


class WriteBlogsListView(BlogsBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error()
        try:
            result = self.service.list_write(
                status=request.GET.get("status", ""),
                q=request.GET.get("q", "").lower(),
            )
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse(result)


class WriteBlogsCreateView(BlogsBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error()
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            page_id = self.service.create_write(
                topic=body.get("topic", ""),
                status=body.get("status", ""),
                url=body.get("url", ""),
                topic_to_cover=body.get("topic_to_cover", ""),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse({"ok": True, "page_id": page_id})


class WriteBlogsUpdateView(BlogsBaseView):
    def patch(self, request, page_id):
        if self.service is None:
            return self._creds_error()
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            self.service.update_write(page_id, body)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse({"ok": True})


class WriteBlogsDeleteView(BlogsBaseView):
    def post(self, request, page_id):
        if self.service is None:
            return self._creds_error()
        try:
            self.service.delete_write(page_id)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        return JsonResponse({"ok": True})


class BlogsCacheView(BlogsBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error()
        self.service.bust_cache()
        return JsonResponse({"ok": True})
