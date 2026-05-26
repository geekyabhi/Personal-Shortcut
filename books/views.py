import json
import os

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .data_layer import BooksDataLayer, DriveDataLayer
from .service import BooksService


class BooksBaseView(View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        data_layer = BooksDataLayer.from_env()
        drive_layer = DriveDataLayer.from_env()
        self.service = BooksService(data_layer, drive_layer)
        self.drive_layer = drive_layer

    @staticmethod
    def _api_error(exc: requests.HTTPError) -> JsonResponse:
        try:
            text = exc.response.text
        except Exception:
            text = str(exc)
        return JsonResponse({"error": text}, status=502)


class BooksDashboardView(View):
    def get(self, request):
        return render(request, "books/dashboard.html")


class BooksChartsView(View):
    def get(self, request):
        return render(request, "books/charts.html")


class BooksListView(BooksBaseView):
    def get(self, request):
        result = self.service.get_list(
            status=request.GET.get("status", ""),
            genre=request.GET.get("genre", ""),
            author=request.GET.get("author", ""),
            search=request.GET.get("q", ""),
        )
        return JsonResponse(result)


class BooksStatsView(BooksBaseView):
    def get(self, request):
        return JsonResponse(self.service.get_stats())


class BooksChartsDataView(BooksBaseView):
    def get(self, request):
        return JsonResponse(self.service.get_chart_data())


class BooksCreateView(BooksBaseView):
    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name = body.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Book name is required"}, status=400)

        try:
            page_id = self.service.create_book(
                name=name,
                status=body.get("status", "To Read"),
                authors=body.get("authors", []),
                genres=body.get("genres", []),
                summary=body.get("summary", "").strip(),
                drive_url=body.get("drive_url", "").strip(),
            )
        except requests.HTTPError as exc:
            return self._api_error(exc)

        return JsonResponse({"ok": True, "page_id": page_id})


class BooksDriveFilesView(BooksBaseView):
    def get(self, request):
        if not self.drive_layer.is_configured:
            return JsonResponse({"configured": False, "files": []})

        try:
            files = self.service.list_drive_files()
        except Exception as exc:
            return JsonResponse({"configured": False, "files": [], "error": str(exc)})

        return JsonResponse({"configured": True, "files": files})


class BooksDriveUploadView(BooksBaseView):
    def post(self, request):
        if not self.drive_layer.is_configured:
            return JsonResponse({"error": "Google Drive not configured"}, status=400)

        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"error": "No file provided"}, status=400)

        if upload.size > 50 * 1024 * 1024:
            return JsonResponse({"error": "File too large (max 50 MB)"}, status=400)

        try:
            folder_id = os.environ.get("GOOGLE_DRIVE_UPLOAD_FOLDER_ID", "").strip()
            drive_file = self.service.upload_drive_file(upload, folder_id)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=502)

        return JsonResponse({
            "ok": True,
            "name": drive_file.get("name", upload.name),
            "url": drive_file.get("webViewLink", ""),
            "id": drive_file.get("id", ""),
        })


class BooksUpdateView(BooksBaseView):
    def patch(self, request, page_id):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            self.service.update_book(page_id, body)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)

        return JsonResponse({"ok": True})


class BooksDeleteView(BooksBaseView):
    def post(self, request, page_id):
        try:
            self.service.delete_book(page_id)
        except requests.HTTPError as exc:
            return self._api_error(exc)

        return JsonResponse({"ok": True})


class BooksCacheView(BooksBaseView):
    def post(self, request):
        self.service.bust_cache()
        return JsonResponse({"ok": True})
