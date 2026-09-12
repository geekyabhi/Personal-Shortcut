import re
from datetime import date, timedelta

import requests

from .data_layer import HabitsDataLayer


class HabitsService:
    VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily", "custom")
    VALID_BUCKETS = ("day", "week", "month", "year")
    YEAR_RE  = re.compile(r"^\d{4}$")
    MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    WEEK_RE  = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
    DAY_RE   = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    _TRUTHY  = frozenset({"true", "1", "yes", "on"})

    def __init__(self, data_layer: HabitsDataLayer):
        self.data_layer = data_layer

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self, period, year, month, week, day, start="", end="", bucket=""):
        if period not in self.VALID_PERIODS:
            raise ValueError(f"Invalid period '{period}'. Valid: {', '.join(self.VALID_PERIODS)}")
        if bucket and bucket not in self.VALID_BUCKETS:
            raise ValueError(f"Invalid bucket '{bucket}'. Valid: {', '.join(self.VALID_BUCKETS)}")
        if year  and not self.YEAR_RE.match(year):   raise ValueError("Invalid year. Use YYYY")
        if month and not self.MONTH_RE.match(month): raise ValueError("Invalid month. Use YYYY-MM")
        if week  and not self.WEEK_RE.match(week):   raise ValueError("Invalid week. Use YYYY-Www")
        if day   and not self.DAY_RE.match(day):     raise ValueError("Invalid day. Use YYYY-MM-DD")
        if period == "custom":
            if not start or not end:            raise ValueError("Custom period requires both start and end")
            if not self.DAY_RE.match(start):    raise ValueError("Invalid start date. Use YYYY-MM-DD")
            if not self.DAY_RE.match(end):      raise ValueError("Invalid end date. Use YYYY-MM-DD")
            if start > end:                     raise ValueError("start must be on or before end")

    # ── Date filter ───────────────────────────────────────────────────────────

    def _build_date_filter(self, period, year=None, month=None, week=None, day=None, start=None, end=None):
        today = date.today()
        if period == "all":
            return None, None, None
        if period == "yearly":
            y = int(year) if year else today.year
            s, e = date(y, 1, 1), date(y + 1, 1, 1)
        elif period == "monthly":
            s = date(int(month[:4]), int(month[5:]), 1) if month else today.replace(day=1)
            e = date(s.year + 1, 1, 1) if s.month == 12 else date(s.year, s.month + 1, 1)
        elif period == "weekly":
            s = date.fromisocalendar(int(week[:4]), int(week[6:]), 1) if week else today - timedelta(days=today.weekday())
            e = s + timedelta(days=7)
        elif period == "daily":
            s = date.fromisoformat(day) if day else today
            e = s + timedelta(days=1)
        elif period == "custom":
            s = date.fromisoformat(start) if start else date(today.year, 1, 1)
            e = date.fromisoformat(end) + timedelta(days=1) if end else today + timedelta(days=1)
        notion_filter = {
            "and": [
                {"property": "Date", "date": {"on_or_after": s.isoformat()}},
                {"property": "Date", "date": {"before": e.isoformat()}},
            ]
        }
        return notion_filter, s, e - timedelta(days=1)

    # ── Row accessors ─────────────────────────────────────────────────────────

    def _habit_fields(self, rows):
        if not rows:
            return []
        props = rows[0].get("properties", {})
        return sorted([k for k, v in props.items() if v.get("type") == "checkbox"])

    def _row_date(self, row):
        return (((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or "")[:10]

    def _row_computed_score(self, row, habit_names):
        """Score is derived, not a Notion property: checked habits / total habits,
        as a 0-100 percentage for that row's own day."""
        if not habit_names:
            return None
        props = row.get("properties", {})
        done = sum(1 for h in habit_names if (props.get(h) or {}).get("checkbox"))
        return round(done / len(habit_names) * 100, 1)

    def _to_bool(self, v):
        if isinstance(v, bool): return v
        if isinstance(v, str):  return v.strip().lower() in self._TRUTHY
        return bool(v)

    # ── Period metadata ───────────────────────────────────────────────────────

    def _period_meta(self, period, year, month, week, range_start, range_end):
        if period == "yearly":  return {"year": year or str(date.today().year)}
        if period == "monthly": return {"month": month or date.today().strftime("%Y-%m")}
        if period == "weekly":  return {"week_start": range_start.isoformat(), "week_end": range_end.isoformat()}
        if period == "daily":   return {"date": range_start.isoformat()}
        if period == "custom":  return {"start": range_start.isoformat(), "end": range_end.isoformat()}
        return {}

    # ── Chart builders ────────────────────────────────────────────────────────

    def _generic_bucket_keys(self, range_start, range_end, unit):
        """(bucket_keys, key_fn, fmt) for an explicit bucket unit — 'day', 'week',
        'month', or 'year' — spanning [range_start, range_end] inclusive, letting the
        user pick a time-frame independent of the period's own default granularity."""
        if unit == "day":
            keys = []
            d = range_start
            while d <= range_end:
                keys.append(d.isoformat())
                d += timedelta(days=1)
            return keys, (lambda ds: ds[:10]), (lambda k: date.fromisoformat(k).strftime("%-d %b %Y"))

        if unit == "week":
            d = range_start - timedelta(days=range_start.weekday())  # back up to Monday
            keys = []
            while d <= range_end:
                keys.append(d.isoformat())
                d += timedelta(days=7)

            def key_fn(ds):
                dd = date.fromisoformat(ds[:10])
                return (dd - timedelta(days=dd.weekday())).isoformat()

            return keys, key_fn, (lambda k: "Wk of " + date.fromisoformat(k).strftime("%-d %b"))

        if unit == "month":
            keys = []
            y, m = range_start.year, range_start.month
            while date(y, m, 1) <= range_end:
                keys.append(f"{y}-{m:02d}")
                m += 1
                if m > 12:
                    m, y = 1, y + 1
            return keys, (lambda ds: ds[:7]), (lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y"))

        # "year"
        keys = [str(y) for y in range(range_start.year, range_end.year + 1)]
        return keys, (lambda ds: ds[:4]), (lambda k: k)

    def _bucket_override_range(self, rows, range_start, range_end):
        """When the period has no fixed range (e.g. 'all'), derive one from the
        actual row dates so an explicit bucket override still has bounds."""
        if range_start is not None and range_end is not None:
            return range_start, range_end
        dates = sorted(d for d in (self._row_date(r) for r in rows) if d)
        if not dates:
            return None, None
        return date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])

    def _score_trend(self, period, year, rows, range_start, range_end, bucket="", habit_names=None):
        habit_names = habit_names if habit_names is not None else self._habit_fields(rows)

        if bucket in self.VALID_BUCKETS:
            rs, re_ = self._bucket_override_range(rows, range_start, range_end)
            if rs is None:
                return {"labels": [], "values": []}
            keys, key_fn, fmt = self._generic_bucket_keys(rs, re_, bucket)
            buckets = {k: [] for k in keys}
            for row in rows:
                d, s = self._row_date(row), self._row_computed_score(row, habit_names)
                if not d or s is None:
                    continue
                k = key_fn(d)
                if k in buckets:
                    buckets[k].append(s)
            return {
                "labels": [fmt(k) for k in keys],
                "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in keys]],
            }

        if period == "daily" or not rows:
            scores = [s for r in rows if (s := self._row_computed_score(r, habit_names)) is not None]
            return {
                "labels": [range_start.strftime("%d %b %Y") if range_start else "-"],
                "values": [round(sum(scores) / len(scores), 1) if scores else None],
            }

        if period in ("monthly", "weekly"):
            buckets: dict[str, list] = {}
            d = range_start
            while d <= range_end:
                buckets[d.isoformat()] = []
                d += timedelta(days=1)
            for row in rows:
                k, s = self._row_date(row), self._row_computed_score(row, habit_names)
                if k in buckets and s is not None:
                    buckets[k].append(s)
            fmt = "%a %d" if period == "weekly" else "%-d"
            return {
                "labels": [date.fromisoformat(k).strftime(fmt) for k in sorted(buckets)],
                "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
            }

        if period == "yearly":
            y = int(year) if year else date.today().year
            buckets = {f"{y}-{m:02d}": [] for m in range(1, 13)}
            for row in rows:
                k, s = self._row_date(row)[:7], self._row_computed_score(row, habit_names)
                if k in buckets and s is not None:
                    buckets[k].append(s)
            return {
                "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b") for k in sorted(buckets)],
                "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
            }

        if period == "custom":
            delta = (range_end - range_start).days
            if delta <= 60:
                buckets = {}
                d = range_start
                while d <= range_end:
                    buckets[d.isoformat()] = []
                    d += timedelta(days=1)
                for row in rows:
                    k, s = self._row_date(row), self._row_computed_score(row, habit_names)
                    if k in buckets and s is not None:
                        buckets[k].append(s)
                return {
                    "labels": [date.fromisoformat(k).strftime("%-d %b") for k in sorted(buckets)],
                    "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
                }
            buckets2: dict[str, list] = {}
            d = range_start
            while d <= range_end:
                k = d.strftime("%Y-%m")
                buckets2.setdefault(k, [])
                d += timedelta(days=1)
            for row in rows:
                k, s = self._row_date(row)[:7], self._row_computed_score(row, habit_names)
                if k in buckets2 and s is not None:
                    buckets2[k].append(s)
            keys2 = sorted(buckets2)
            return {
                "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys2],
                "values": [round(sum(buckets2[k]) / len(buckets2[k]), 1) if buckets2[k] else None for k in keys2],
            }

        # all — monthly buckets
        buckets: dict[str, list] = {}
        for row in rows:
            k, s = self._row_date(row)[:7], self._row_computed_score(row, habit_names)
            if len(k) == 7 and s is not None:
                buckets.setdefault(k, []).append(s)
        keys = sorted(buckets)
        return {
            "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys],
            "values": [round(sum(buckets[k]) / len(buckets[k]), 1) for k in keys],
        }

    def _habit_grid(self, rows, range_start, range_end):
        if not rows or range_start is None or range_end is None:
            return None
        habits = self._habit_fields(rows)
        dates = []
        d = range_start
        while d <= range_end:
            dates.append(d.isoformat())
            d += timedelta(days=1)
        row_by_date = {self._row_date(r): r for r in rows if self._row_date(r)}
        result = []
        for h in habits:
            vals = []
            for date_str in dates:
                row = row_by_date.get(date_str)
                if row is None:
                    vals.append(None)
                else:
                    done = (row.get("properties", {}).get(h) or {}).get("checkbox", False)
                    vals.append(1 if done else 0)
            result.append({"name": h, "values": vals})
        return {"dates": dates, "habits": result}

    # ── Internal fetch helper ─────────────────────────────────────────────────

    def _fetch_rows(self, period, year, month, week, day, start, end, bucket=""):
        self._validate(period, year, month, week, day, start, end, bucket=bucket)
        notion_filter, range_start, range_end = self._build_date_filter(
            period,
            year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        rows = self.data_layer.fetch_all_rows(notion_filter)
        return rows, range_start, range_end

    # ── Public interface ──────────────────────────────────────────────────────

    def list_entries(self, period, year, month, week, day, start, end):
        """Raw per-day entries for the period — backs the dashboard's Browse
        list and its client-side filter builder (mirrors expenses' /list/)."""
        rows, range_start, range_end = self._fetch_rows(period, year, month, week, day, start, end)
        habit_names = self._habit_fields(rows)

        entries = []
        for row in rows:
            props = row.get("properties", {})
            entry = {
                "page_id": row.get("id", ""),
                "date": self._row_date(row),
                "score": self._row_computed_score(row, habit_names),
            }
            for h in habit_names:
                entry[h] = bool((props.get(h) or {}).get("checkbox"))
            entries.append(entry)
        entries.sort(key=lambda e: e["date"], reverse=True)

        return {
            "period": period,
            "habit_names": habit_names,
            "entries": entries,
            **self._period_meta(period, year, month, week, range_start, range_end),
        }

    def get_summary(self, period, year, month, week, day, start, end):
        rows, range_start, range_end = self._fetch_rows(period, year, month, week, day, start, end)

        habits = self._habit_fields(rows)
        total_days = len(rows)
        done = {h: 0 for h in habits}
        scores = []

        for row in rows:
            props = row.get("properties", {})
            for h in habits:
                if (props.get(h) or {}).get("checkbox"):
                    done[h] += 1
            s = self._row_computed_score(row, habits)
            if s is not None:
                scores.append(s)

        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        total_possible = total_days * len(habits)
        overall_rate = round(sum(done.values()) / total_possible * 100, 1) if total_possible else 0

        habit_stats = sorted([
            {
                "name": h,
                "done": done[h],
                "total": total_days,
                "rate": round(done[h] / total_days * 100, 1) if total_days else 0,
            }
            for h in habits
        ], key=lambda x: -x["rate"])

        return {
            "period": period,
            "total_days": total_days,
            "avg_score": avg_score,
            "overall_completion_rate": overall_rate,
            "habits": habit_stats,
            **self._period_meta(period, year, month, week, range_start, range_end),
        }

    def get_chart_data(self, period, year, month, week, day, start, end, bucket=""):
        rows, range_start, range_end = self._fetch_rows(period, year, month, week, day, start, end, bucket)

        habits = self._habit_fields(rows)
        total_days = len(rows)
        done = {h: 0 for h in habits}

        for row in rows:
            props = row.get("properties", {})
            for h in habits:
                if (props.get(h) or {}).get("checkbox"):
                    done[h] += 1

        sorted_habits = sorted(done.items(), key=lambda x: -x[1])
        habit_counts = {
            "labels": [h for h, _ in sorted_habits],
            "values": [c for _, c in sorted_habits],
        }

        show_grid = period in ("daily", "weekly", "monthly") or (
            period == "custom" and range_start and range_end
            and (range_end - range_start).days <= 60
        )
        grid = self._habit_grid(rows, range_start, range_end) if show_grid else None

        return {
            "period": period,
            "total_days": total_days,
            "score_trend": self._score_trend(period, year, rows, range_start, range_end, bucket, habits),
            "habit_counts": habit_counts,
            "habit_grid": grid,
            **self._period_meta(period, year, month, week, range_start, range_end),
        }

    def backfill(self, start=None, end=None):
        """Create missing daily entries in [start, end] — defaults to Jan 1 of
        the current year through today when no range is given."""
        if start and not self.DAY_RE.match(start):
            raise ValueError("Invalid start date. Use YYYY-MM-DD")
        if end and not self.DAY_RE.match(end):
            raise ValueError("Invalid end date. Use YYYY-MM-DD")

        today = date.today()
        start_d = date.fromisoformat(start) if start else date(today.year, 1, 1)
        end_d = date.fromisoformat(end) if end else today
        if start_d > end_d:
            raise ValueError("start must be on or before end")
        if (end_d - start_d).days > 400:
            raise ValueError("Range too large — please backfill at most ~400 days at a time")

        notion_filter = {
            "and": [
                {"property": "Date", "date": {"on_or_after": start_d.isoformat()}},
                {"property": "Date", "date": {"on_or_before": end_d.isoformat()}},
            ]
        }
        rows = self.data_layer.fetch_all_rows(notion_filter)
        existing = {self._row_date(r) for r in rows if self._row_date(r)}

        all_dates = []
        d = start_d
        while d <= end_d:
            all_dates.append(d.isoformat())
            d += timedelta(days=1)

        missing = [d for d in all_dates if d not in existing]

        created, failed = [], []
        for date_str in missing:
            try:
                self.data_layer.create_page(date_str)
                created.append(date_str)
            except requests.HTTPError as exc:
                try:
                    err = exc.response.json() if exc.response else str(exc)
                except Exception:
                    err = str(exc)
                failed.append({"date": date_str, "error": err})
            except requests.RequestException as exc:
                failed.append({"date": date_str, "error": str(exc)})

        return {"created": len(created), "dates": created, "failed": failed}

    def get_today(self):
        today = date.today().isoformat()
        notion_filter = {"property": "Date", "date": {"equals": today}}
        rows = self.data_layer.fetch_all_rows(notion_filter)
        schema = self.data_layer.fetch_schema()
        habit_names = sorted([k for k, v in schema.items() if v.get("type") == "checkbox"])

        props = rows[0].get("properties", {}) if rows else {}
        habits = [
            {"name": h, "done": bool((props.get(h) or {}).get("checkbox"))}
            for h in habit_names
        ]
        return {"date": today, "habits": habits}

    def _schema_and_habits(self):
        schema = self.data_layer.fetch_schema()
        habit_names = sorted([k for k, v in schema.items() if v.get("type") == "checkbox"])
        return schema, habit_names

    def _write_score(self, page_id, score, schema):
        """Mirror the computed score (checked/total) back onto the row's own
        "Score" column in Notion, so it's visible there too — not just derived
        on the fly in the dashboard. "Score" must be a plain number: a formula
        property silently ignores writes (Notion's API returns 200 and no-ops
        rather than erroring), so the type has to be checked up front rather
        than reacted to after the fact — if it's missing or still the old
        formula column, convert it to number first."""
        if score is None:
            return
        score_prop = schema.get("Score")
        if not score_prop or score_prop.get("type") != "number":
            self.data_layer.add_number_property("Score")
        self.data_layer.patch_page(page_id, {"Score": {"number": score}})

    def check_habits(self, habits_dict):
        today = date.today().isoformat()
        notion_filter = {"property": "Date", "date": {"equals": today}}
        rows = self.data_layer.fetch_all_rows(notion_filter)

        created = False
        if rows:
            page_id = rows[0]["id"]
        else:
            page = self.data_layer.create_page(today)
            page_id = page["id"]
            created = True

        score = None
        if habits_dict:
            schema, habit_names = self._schema_and_habits()
            patch_props = {name: {"checkbox": self._to_bool(val)} for name, val in habits_dict.items()}
            page = self.data_layer.patch_page(page_id, patch_props)
            score = self._row_computed_score(page, habit_names)
            self._write_score(page_id, score, schema)

        return {
            "date": today,
            "page_id": page_id,
            "created": created,
            "updated": habits_dict,
            "score": score,
        }

    def update_entry(self, page_id, habits_dict):
        """Patch an arbitrary day's habit checkboxes directly by page_id — used by
        the Browse Entries grid for editing past days (check_habits only ever
        touches today's row). Also recomputes and writes the derived Score back
        to Notion so the two stay in sync."""
        score = None
        if habits_dict:
            schema, habit_names = self._schema_and_habits()
            patch_props = {name: {"checkbox": self._to_bool(val)} for name, val in habits_dict.items()}
            page = self.data_layer.patch_page(page_id, patch_props)
            score = self._row_computed_score(page, habit_names)
            self._write_score(page_id, score, schema)
        return {"page_id": page_id, "updated": habits_dict, "score": score}

    # ── Habit management (add/remove columns in the Notion schema) ─────────────

    def list_habit_names(self):
        """All checkbox habit columns, from the schema directly — independent of
        whether any row currently exists (unlike `_habit_fields`, which only
        sees whatever columns happen to be on an already-loaded row)."""
        _, habit_names = self._schema_and_habits()
        return habit_names

    def add_habit(self, name, default_checked=False):
        name = (name or "").strip()
        if not name:
            raise ValueError("Habit name is required")
        schema = self.data_layer.fetch_schema()
        if name in schema:
            raise ValueError(f'A column named "{name}" already exists')

        self.data_layer.add_checkbox_property(name)

        backfilled, failed = 0, 0
        if default_checked:
            rows = self.data_layer.fetch_all_rows(None)
            for row in rows:
                try:
                    self.data_layer.patch_page(row["id"], {name: {"checkbox": True}})
                    backfilled += 1
                except requests.RequestException:
                    failed += 1

        return {"name": name, "created": True, "backfilled": backfilled, "backfill_failed": failed}

    def remove_habit(self, name):
        name = (name or "").strip()
        schema = self.data_layer.fetch_schema()
        if name not in schema or schema[name].get("type") != "checkbox":
            raise ValueError(f'No habit column named "{name}" found')
        self.data_layer.remove_property(name)
        return {"name": name, "removed": True}
