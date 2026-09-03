import os


class SplitwiseNotConfigured(RuntimeError):
    """Raised when the SPLITWISE_* env vars are missing."""


class SplitwiseError(RuntimeError):
    """Raised when the Splitwise API rejects a request."""


class SplitwiseClient:
    """Thin wrapper over the ``splitwise`` SDK.

    Auth uses the personal API-key flow (no OAuth redirect):
        Splitwise(consumer_key, consumer_secret, api_key=...)

    Every method returns plain dicts / lists so views and templates never
    touch SDK objects. Mirrors the shape of ``ExpensesDataLayer``
    (``from_env`` + ``is_configured``).
    """

    def __init__(self, consumer_key: str, consumer_secret: str, api_key: str):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.api_key = api_key
        self._sdk = None
        self._me = None  # cached current-user dict

    @classmethod
    def from_env(cls) -> "SplitwiseClient":
        return cls(
            consumer_key=os.environ.get("SPLITWISE_CONSUMER_KEY", ""),
            consumer_secret=os.environ.get("SPLITWISE_CONSUMER_SECRET", ""),
            api_key=os.environ.get("SPLITWISE_API_KEY", ""),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.consumer_key and self.consumer_secret and self.api_key)

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    @property
    def sdk(self):
        if not self.is_configured:
            raise SplitwiseNotConfigured(
                "SPLITWISE_CONSUMER_KEY, SPLITWISE_CONSUMER_SECRET and "
                "SPLITWISE_API_KEY must be set"
            )
        if self._sdk is None:
            from splitwise import Splitwise

            self._sdk = Splitwise(
                self.consumer_key, self.consumer_secret, api_key=self.api_key
            )
        return self._sdk

    def _call(self, fn, *args, **kwargs):
        """Run an SDK call, normalising SDK exceptions to ``SplitwiseError``."""
        try:
            return fn(*args, **kwargs)
        except SplitwiseNotConfigured:
            raise
        except Exception as exc:  # SplitwiseException, network errors, ...
            raise SplitwiseError(str(exc)) from exc

    @staticmethod
    def _full_name(obj) -> str:
        parts = [obj.getFirstName(), getattr(obj, "getLastName", lambda: "")()]
        return " ".join(p for p in parts if p).strip()

    def me(self) -> dict:
        if self._me is None:
            u = self._call(self.sdk.getCurrentUser)
            self._me = {
                "id": u.getId(),
                "name": self._full_name(u),
                "email": u.getEmail(),
                "currency": getattr(u, "getDefaultCurrency", lambda: "")() or "",
            }
        return self._me

    # ------------------------------------------------------------------ #
    #  Serialisers                                                         #
    # ------------------------------------------------------------------ #

    def _expense_to_dict(self, e, me_id: int) -> dict:
        my_paid = my_owed = 0.0
        users = []
        for eu in e.getUsers() or []:
            paid = float(eu.getPaidShare() or 0)
            owed = float(eu.getOwedShare() or 0)
            users.append(
                {
                    "id": eu.getId(),
                    "name": self._full_name(eu),
                    "paid": round(paid, 2),
                    "owed": round(owed, 2),
                }
            )
            if eu.getId() == me_id:
                my_paid, my_owed = paid, owed
        cat = e.getCategory()
        return {
            "id": e.getId(),
            "description": e.getDescription() or "",
            "cost": round(float(e.getCost() or 0), 2),
            "currency": e.getCurrencyCode() or "",
            "date": (e.getDate() or "")[:10],
            "group_id": e.getGroupId(),
            "category": cat.getName() if cat else "",
            "is_payment": bool(e.getPayment()),
            "my_paid_share": round(my_paid, 2),
            "my_owed_share": round(my_owed, 2),
            "my_net": round(my_paid - my_owed, 2),
            "users": users,
        }

    # ------------------------------------------------------------------ #
    #  Reads                                                               #
    # ------------------------------------------------------------------ #

    def get_friends(self) -> list:
        out = []
        for f in self._call(self.sdk.getFriends) or []:
            balances = [
                {"amount": round(float(b.getAmount() or 0), 2), "currency": b.getCurrencyCode()}
                for b in (f.getBalances() or [])
            ]
            out.append(
                {
                    "id": f.getId(),
                    "name": self._full_name(f),
                    "balances": balances,
                    "net": round(sum(b["amount"] for b in balances), 2),
                }
            )
        return out

    def get_groups(self) -> list:
        out = []
        for g in self._call(self.sdk.getGroups) or []:
            members = [
                {"id": m.getId(), "name": self._full_name(m)}
                for m in (g.getMembers() or [])
            ]
            out.append({"id": g.getId(), "name": g.getName(), "members": members})
        return out

    def get_expenses(
        self,
        limit: int = 20,
        offset: int = 0,
        group_id=None,
        friend_id=None,
        dated_after: str = "",
        dated_before: str = "",
    ) -> list:
        kwargs = {"limit": limit, "offset": offset}
        if group_id not in (None, ""):
            kwargs["group_id"] = int(group_id)
        if friend_id not in (None, ""):
            kwargs["friend_id"] = int(friend_id)
        if dated_after:
            kwargs["dated_after"] = dated_after
        if dated_before:
            kwargs["dated_before"] = dated_before

        me_id = self.me()["id"]
        raw = self._call(self.sdk.getExpenses, **kwargs) or []
        return [
            self._expense_to_dict(e, me_id)
            for e in raw
            if not e.getDeletedAt()
        ]

    def get_expense(self, expense_id) -> dict:
        me_id = self.me()["id"]
        e = self._call(self.sdk.getExpense, int(expense_id))
        if e is None or e.getDeletedAt():
            raise SplitwiseError(f"Splitwise expense {expense_id} not found")
        return self._expense_to_dict(e, me_id)

    # ------------------------------------------------------------------ #
    #  Writes                                                              #
    # ------------------------------------------------------------------ #

    def create_expense(
        self,
        *,
        description: str,
        cost,
        participant_ids: list = None,
        group_id=None,
        date: str = "",
        currency: str = "",
        category_id=None,
        shares: dict = None,
    ) -> dict:
        """Create a Splitwise expense.

        ``shares`` (optional): ``{user_id: {"paid": x, "owed": y}}`` for a
        custom split. When omitted, the cost is split equally between the
        current user and ``participant_ids``, with the current user paying
        the full amount.
        """
        from splitwise.expense import Expense
        from splitwise.user import ExpenseUser

        cost = round(float(cost), 2)
        if cost <= 0:
            raise ValueError("Amount must be greater than 0")

        me_id = self.me()["id"]

        if shares:
            paid = {int(k): round(float(v.get("paid", 0)), 2) for k, v in shares.items()}
            owed = {int(k): round(float(v.get("owed", 0)), 2) for k, v in shares.items()}
            ids = list(dict.fromkeys(list(paid) + list(owed)))
        else:
            ids = list(dict.fromkeys([me_id] + [int(x) for x in (participant_ids or [])]))
            per = round(cost / len(ids), 2) if ids else 0.0
            owed = {uid: per for uid in ids}
            if me_id in owed:
                owed[me_id] = round(owed[me_id] + (cost - per * len(ids)), 2)
            paid = {uid: 0.0 for uid in ids}
            paid[me_id] = cost

        if len(ids) < 2:
            raise ValueError("A split needs at least one other participant")

        if round(sum(paid.values()), 2) != cost:
            raise ValueError(
                f"Paid shares ({sum(paid.values()):.2f}) must sum to the cost ({cost:.2f})"
            )
        if round(sum(owed.values()), 2) != cost:
            raise ValueError(
                f"Owed shares ({sum(owed.values()):.2f}) must sum to the cost ({cost:.2f})"
            )

        exp = Expense()
        exp.setDescription(description or "Expense")
        exp.setCost(f"{cost:.2f}")
        if group_id not in (None, ""):
            exp.setGroupId(int(group_id))
        if date:
            # Splitwise wants ISO 8601; noon avoids a timezone day-shift.
            exp.setDate(f"{date}T12:00:00Z" if len(date) == 10 else date)
        if currency:
            exp.setCurrencyCode(currency)
        if category_id:
            from splitwise.category import Category

            cat = Category()
            cat.setId(int(category_id))
            exp.setCategory(cat)

        users = []
        for uid in ids:
            eu = ExpenseUser()
            eu.setId(uid)
            eu.setPaidShare(f"{paid.get(uid, 0.0):.2f}")
            eu.setOwedShare(f"{owed.get(uid, 0.0):.2f}")
            users.append(eu)
        exp.setUsers(users)

        created, errors = self._call(self.sdk.createExpense, exp)
        if errors is not None:
            msgs = self._error_messages(errors)
            if msgs:
                raise SplitwiseError("; ".join(msgs))
        return {
            "id": created.getId(),
            "description": created.getDescription(),
            "cost": round(float(created.getCost() or 0), 2),
        }

    @staticmethod
    def _error_messages(errors) -> list:
        try:
            raw = errors.getErrors()
        except Exception:
            return [str(errors)] if errors else []
        if isinstance(raw, dict):
            flat = []
            for v in raw.values():
                flat.extend(v if isinstance(v, list) else [v])
            return [str(m) for m in flat]
        if isinstance(raw, list):
            return [str(m) for m in raw]
        return [str(raw)] if raw else []
