import time
from threading import RLock


class Stall:
    def __init__(self, owner):
        self.owner = owner
        self.items = []
        self.active = False
        self.last_ad = 0
        self.last_ad_time = 0.0
        self.last_ad_content = None


class Market:
    def __init__(self,
                 min_price=1,
                 fee_rate=0.0,
                 listing_ttl=7 * 24 * 3600,
                 ad_cooldown=30,
                 ad_duplicate_window=300,
                 recommended_slots=3):
        self.listings = []
        self.stalls = {}

        self.min_price = min_price
        self.fee_rate = fee_rate
        self.listing_ttl = listing_ttl
        self.ad_cooldown = ad_cooldown
        self.ad_duplicate_window = ad_duplicate_window
        self.recommended_slots = recommended_slots

        self.collected_fees = 0.0
        self.seller_balances = {}
        self.inventories = {}
        self.mails = {}
        self.ads = []
        self.recommended = set()

        self._lock = RLock()
        self._seq = 0
        self._now = time.time

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def _send_mail(self, recipient, subject, body, attachments=None):
        mail = {
            "subject": subject,
            "body": body,
            "attachments": list(attachments or []),
            "sent_at": self._now(),
            "read": False,
        }
        self.mails.setdefault(recipient, []).append(mail)
        return mail

    def get_mails(self, player):
        return list(self.mails.get(player, []))

    def list_item(self, seller, item, price, qty=1, ttl=None):
        if price is None or price < self.min_price:
            return False
        if qty is None or qty <= 0:
            return False
        now = self._now()
        listing = {
            "seller": seller,
            "item": item,
            "price": price,
            "qty": qty,
            "sales": 0,
            "listed_seq": self._next_seq(),
            "listed_at": now,
            "expire_at": now + (ttl if ttl is not None else self.listing_ttl),
        }
        listing["id"] = id(listing)
        with self._lock:
            self.listings.append(listing)
        return True

    def _find_listing_index(self, listing_id):
        for i, listing in enumerate(self.listings):
            if listing.get("id") == listing_id:
                return i
        return -1

    def buy(self, buyer, listing_id, qty=1):
        if qty is None or qty <= 0:
            return None
        with self._lock:
            i = self._find_listing_index(listing_id)
            if i < 0:
                return None
            listing = self.listings[i]
            if self._now() >= listing["expire_at"]:
                return None
            if listing["seller"] == buyer:
                return None
            if qty > listing["qty"]:
                return None

            listing["qty"] -= qty
            listing["sales"] += qty
            fee = round(listing["price"] * qty * self.fee_rate, 2)
            proceeds = listing["price"] * qty - fee
            self.collected_fees += fee
            balance = self.seller_balances.get(listing["seller"], 0.0)
            self.seller_balances[listing["seller"]] = balance + proceeds

            if listing["qty"] == 0:
                self.listings.pop(i)
            return listing["item"]

    def cancel_listing(self, listing_id):
        with self._lock:
            i = self._find_listing_index(listing_id)
            if i < 0:
                return False
            listing = self.listings.pop(i)
            self.recommended.discard(listing["id"])
            self._send_mail(
                listing["seller"],
                "交易行下架返还",
                "您的物品已下架，全额返还，未收取任何手续费。",
                [{"item": listing["item"], "qty": listing["qty"]}],
            )
            return True

    def process_expired(self):
        now = self._now()
        expired = []
        with self._lock:
            remaining = []
            for listing in self.listings:
                if listing["expire_at"] <= now:
                    expired.append(listing)
                else:
                    remaining.append(listing)
            self.listings = remaining
            for listing in expired:
                self.recommended.discard(listing["id"])
                self._send_mail(
                    listing["seller"],
                    "交易行到期返还",
                    "您的挂售物品已到期，系统自动下架并通过邮件返还。",
                    [{"item": listing["item"], "qty": listing["qty"]}],
                )
        return len(expired)

    def search(self, keyword=None, sort_by="price"):
        now = self._now()
        with self._lock:
            results = [l for l in self.listings if l["expire_at"] > now]

        if keyword:
            keyword = str(keyword).lower()
            results = [
                l for l in results
                if keyword in str(l["item"]).lower()
                or keyword in str(l["seller"]).lower()
            ]

        if sort_by == "time":
            results.sort(key=lambda l: l["listed_seq"])
        elif sort_by == "sales":
            results.sort(key=lambda l: (-l["sales"], l["price"], l["listed_seq"]))
        else:
            results.sort(key=lambda l: (l["price"], l["listed_seq"]))

        if self.recommended_slots and self.recommended:
            pinned = [l for l in results if l["id"] in self.recommended]
            pinned = pinned[: self.recommended_slots]
            pinned_ids = {l["id"] for l in pinned}
            others = [l for l in results if l["id"] not in pinned_ids]
            results = pinned + others
        return results

    def recommend(self, listing_id):
        with self._lock:
            i = self._find_listing_index(listing_id)
            if i < 0:
                return False
            if len(self.recommended) >= self.recommended_slots:
                return False
            self.recommended.add(listing_id)
            return True

    def unrecommend(self, listing_id):
        self.recommended.discard(listing_id)
        return True

    def open_stall(self, owner):
        with self._lock:
            stall = self.stalls.setdefault(owner, Stall(owner))
            stall.active = True
            return True

    def put_on_stall(self, owner, item, price, qty=1):
        if price is None or price < self.min_price:
            return False
        if qty is None or qty <= 0:
            return False
        with self._lock:
            stall = self.stalls.get(owner)
            if stall is None or not stall.active:
                return False
            stall.items.append({
                "item": item,
                "price": price,
                "qty": qty,
                "sales": 0,
            })
            return True

    def buy_from_stall(self, buyer, owner, item, qty=1):
        if qty is None or qty <= 0:
            return False
        with self._lock:
            stall = self.stalls.get(owner)
            if stall is None or not stall.active:
                return False
            for entry in stall.items:
                if entry["item"] == item and entry["qty"] >= qty:
                    entry["qty"] -= qty
                    entry["sales"] += qty
                    proceeds = entry["price"] * qty
                    balance = self.seller_balances.get(owner, 0.0)
                    self.seller_balances[owner] = balance + proceeds
                    if entry["qty"] == 0:
                        stall.items.remove(entry)
                    return True
            return False

    def close_stall(self, owner):
        with self._lock:
            stall = self.stalls.get(owner)
            if stall is None:
                return False
            if stall.active:
                inventory = self.inventories.setdefault(owner, [])
                for entry in stall.items:
                    inventory.append(entry)
                stall.items = []
            stall.active = False
            return True

    def on_player_offline(self, player):
        return self.close_stall(player)

    def send_ad(self, stall_id, content, channel="ad"):
        if not content or not str(content).strip():
            return False
        stall = self.stalls.get(stall_id)
        if stall is None:
            return False
        now = self._now()
        with self._lock:
            elapsed = now - stall.last_ad_time
            if stall.last_ad_time and elapsed < self.ad_cooldown:
                return False
            if (stall.last_ad_content == content
                    and elapsed < self.ad_duplicate_window):
                return False
            stall.last_ad_time = now
            stall.last_ad = now
            stall.last_ad_content = content
            self.ads.append({
                "stall": stall_id,
                "channel": channel,
                "content": content,
                "sent_at": now,
            })
            return True
