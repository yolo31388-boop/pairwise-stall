
class Stall:
    def __init__(self, owner):
        self.owner = owner
        self.items = []
        self.active = False
        self.last_ad = 0


class Market:
    def __init__(self):
        self.listings = []
        self.stalls = {}

    def list_item(self, seller, item, price):
        # BUG: 无最低限价
        listing = {"seller": seller, "item": item, "price": price}
        self.listings.append(listing)
        return True

    def search(self, keyword=None, sort_by="price"):
        # BUG: 只按价格排序
        return sorted(self.listings, key=lambda x: x["price"])

    def buy(self, buyer, listing_id):
        # BUG: 无库存校验，并发可复制
        for i, l in enumerate(self.listings):
            if id(l) == listing_id:
                self.listings.pop(i)
                return l["item"]
        return None

    def cancel_listing(self, listing_id):
        for i, l in enumerate(self.listings):
            if id(l) == listing_id:
                # BUG: 手续费不退
                self.listings.pop(i)
                return True
        return False

    def send_ad(self, stall_id, content):
        # BUG: 无冷却
        return True
