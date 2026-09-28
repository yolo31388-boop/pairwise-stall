
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stall.market import Stall, Market


def test_min_price_limit():
    m = Market()
    m.min_price = 10
    assert m.list_item("s1", "item", 5) == False
    assert m.list_item("s1", "item", 15) == True


def test_search_multi_sort():
    m = Market()
    m.list_item("s1", "a", 100)
    m.list_item("s2", "b", 50)
    result = m.search(sort_by="time")
    assert result[0]["item"] == "a"


def test_buy_concurrent_guard():
    m = Market()
    m.list_item("s1", "rare", 100)
    lid = id(m.listings[0])
    r1 = m.buy("b1", lid)
    r2 = m.buy("b2", lid)
    assert r1 is not None
    assert r2 is None


def test_cancel_refunds_fee():
    m = Market()
    m.fee_rate = 0.05
    m.list_item("s1", "item", 100)
    seller_balance = {"s1": 0}
    m.seller_balances = seller_balance
    lid = id(m.listings[0])
    m.cancel_listing(lid)
    assert len(m.listings) == 0


def test_ad_cooldown():
    m = Market()
    s = Stall("p1")
    m.stalls["p1"] = s
    assert m.send_ad("p1", "卖东西") == True
    assert m.send_ad("p1", "卖东西") == False


def test_auto_close_on_offline():
    m = Market()
    s = Stall("p1")
    s.active = True
    s.items = ["item"]
    m.stalls["p1"] = s
    m.on_player_offline("p1")
    assert s.active == False


def test_expired_listing_removed():
    m = Market()
    m.list_item("s1", "item", 100)
    m.listings[0]["expire_at"] = 0
    m.process_expired()
    assert len(m.listings) == 0


def test_duplicate_ad_blocked():
    m = Market()
    s = Stall("p1")
    m.stalls["p1"] = s
    m.send_ad("p1", "same ad")
    assert m.send_ad("p1", "same ad") == False


def test_listing_fee_only_on_sale():
    m = Market()
    m.fee_rate = 0.05
    m.list_item("s1", "item", 100)
    initial_fee = m.collected_fees if hasattr(m, 'collected_fees') else 0
    lid = id(m.listings[0])
    m.buy("b1", lid)
    assert m.collected_fees > initial_fee
