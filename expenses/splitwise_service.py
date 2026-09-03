from datetime import date

from .splitwise_client import SplitwiseClient


class SplitwiseService:
    """Validation + shaping on top of :class:`SplitwiseClient`.

    Parallels :class:`ExpensesService` — the view layer only ever talks to
    this class, never the SDK wrapper directly.
    """

    MAX_LIMIT = 100
    DAY_RE_LEN = 10

    def __init__(self, client: SplitwiseClient):
        self.client = client

    # ------------------------------------------------------------------ #
    #  Reads                                                               #
    # ------------------------------------------------------------------ #

    def overview(self) -> dict:
        """Balances + friends + groups in one call (for the dashboard panel)."""
        me = self.client.me()
        friends = self.client.get_friends()
        groups = self.client.get_groups()

        you_are_owed = round(sum(f["net"] for f in friends if f["net"] > 0), 2)
        you_owe = round(-sum(f["net"] for f in friends if f["net"] < 0), 2)

        return {
            "configured": True,
            "me": me,
            "totals": {
                "you_owe": you_owe,
                "you_are_owed": you_are_owed,
                "net": round(you_are_owed - you_owe, 2),
            },
            "friends": sorted(friends, key=lambda f: f["net"]),
            "groups": groups,
        }

    def recent_expenses(
        self,
        limit,
        group_id: str = "",
        friend_id: str = "",
        dated_after: str = "",
        dated_before: str = "",
        offset=0,
    ) -> dict:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise ValueError("limit must be an integer")
        limit = max(1, min(self.MAX_LIMIT, limit))
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0

        for label, value in (("dated_after", dated_after), ("dated_before", dated_before)):
            if value and len(value) != self.DAY_RE_LEN:
                raise ValueError(f"{label} must be YYYY-MM-DD")

        # group_id "0" is a real value (non-group / individual expenses)
        gid = group_id if group_id not in ("", None) else None

        expenses = self.client.get_expenses(
            limit=limit,
            offset=offset,
            group_id=gid,
            friend_id=friend_id or None,
            dated_after=dated_after,
            dated_before=dated_before,
        )
        group_names = {g["id"]: g["name"] for g in self.client.get_groups()}
        for e in expenses:
            e["group_name"] = group_names.get(e["group_id"], "")
        return {
            "count": len(expenses),
            "offset": offset,
            "limit": limit,
            "has_more": len(expenses) == limit,
            "expenses": expenses,
        }

    # ------------------------------------------------------------------ #
    #  Writes                                                              #
    # ------------------------------------------------------------------ #

    def create_split(
        self,
        description: str,
        amount,
        participant_ids: list,
        group_id: str = "",
        date_str: str = "",
        currency: str = "",
        category_id=None,
    ) -> dict:
        description = (description or "").strip()
        if not description:
            raise ValueError("Description is required")
        if amount in (None, ""):
            raise ValueError("Amount is required")
        if not participant_ids:
            raise ValueError("Pick at least one other participant to split with")

        return self.client.create_expense(
            description=description,
            cost=amount,
            participant_ids=participant_ids,
            group_id=group_id or None,
            date=date_str or "",
            currency=currency or "",
            category_id=category_id,
        )

    def push_entry_split(self, entry: dict, mode: str, group_id, shares: dict) -> dict:
        """Push a Notion expense row to Splitwise as a split.

        ``entry`` is a row dict from ``ExpensesService.get_entry`` (needs
        ``title``, ``amount``, ``date``). ``shares`` maps ``user_id -> owed
        amount`` and must include the current user; the current user is
        always recorded as having paid the full amount.
        """
        me = self.client.me()
        amount = round(float(entry.get("amount") or 0), 2)
        if amount <= 0:
            raise ValueError("Expense amount must be greater than 0")

        owed = {}
        for k, v in (shares or {}).items():
            try:
                owed[int(k)] = round(float(v), 2)
            except (TypeError, ValueError):
                raise ValueError("Invalid share amount")

        if len(owed) < 2:
            raise ValueError("Pick at least one other person to split with")
        if me["id"] not in owed:
            raise ValueError("Your own share is missing from the split")
        if round(sum(owed.values()), 2) != amount:
            raise ValueError(
                f"Shares add up to {sum(owed.values()):.2f}, "
                f"but the expense is {amount:.2f}"
            )

        shares_full = {
            uid: {"paid": amount if uid == me["id"] else 0.0, "owed": o}
            for uid, o in owed.items()
        }
        gid = None if mode == "individual" else (group_id or None)

        return self.client.create_expense(
            description=entry.get("title") or "Expense",
            cost=amount,
            group_id=gid,
            date=entry.get("date") or "",
            currency=me.get("currency") or "",
            shares=shares_full,
        )

    def import_to_notion(self, expense_id, expenses_service) -> dict:
        """Copy the current user's share of a Splitwise expense into Notion.

        Amount = your owed share only. Category = ``Splitwise``. Source =
        the person(s) who paid. ``From Split`` is ticked, and the full
        breakdown goes into ``Comment``. Returns
        ``{"page_id", "name", "amount", "date"}``.
        """
        e = self.client.get_expense(expense_id)
        if e["is_payment"]:
            raise ValueError("That entry is a settle-up payment, not an expense")

        already = expenses_service.imported_splitwise_ids()
        if already is not None and int(e["id"]) in already:
            raise ValueError("This Splitwise expense is already imported into Notion")

        my_share = round(e["my_owed_share"] or 0.0, 2)
        if my_share <= 0:
            raise ValueError("Your share of that expense is 0 — nothing to import")

        me_id = self.client.me()["id"]
        users = e.get("users") or []
        payers = [u["name"] for u in users if (u.get("paid") or 0) > 0]
        paid_by = ", ".join(payers) if payers else "Splitwise"

        name = e["description"] or "Splitwise expense"
        date_str = e["date"] or date.today().isoformat()

        lines = [f"Total : {e['cost']}", f"My Split : {my_share}"]
        for u in users:
            if u["id"] != me_id:
                lines.append(f"{u['name']}: {round(u.get('owed') or 0.0, 2)}")
        lines.append(f"Paid By: {paid_by}")

        page_id = expenses_service.create_from_split(
            name, my_share, date_str, payers or ["Splitwise"], "\n".join(lines),
            splitwise_id=e["id"],
        )
        return {
            "page_id": page_id,
            "name": name,
            "amount": my_share,
            "date": date_str,
        }
