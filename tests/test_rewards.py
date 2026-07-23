from config import SHOP_SKINS
from database import Database


def test_rewards_cover_classic_and_battle_draws():
    assert Database._reward("classic", 1, False, None) == 5_000
    assert Database._reward("classic", 99, True, "full") == 500
    assert Database._reward("battle", 1, False, None) == 10_000
    assert Database._reward("battle", 2, False, None) == 5_000
    assert Database._reward("battle", 2, True, "partial") == 700
    assert Database._reward("battle", 99, True, "full") == 1_000


def test_rating_is_separate_from_wallet_balance():
    assert Database._rating_delta("classic", 1, False) == 25
    assert Database._rating_delta("classic", 2, False) == -10
    assert Database._rating_delta("battle", 1, False) == 30
    assert Database._rating_delta("battle", 2, False) == 10


def test_shop_uses_only_earned_cash_and_balanced_prices():
    assert all("currency" not in skin for skin in SHOP_SKINS)
    prices = {skin["id"]: skin["price"] for skin in SHOP_SKINS}
    assert prices["s_olma"] >= 5 * Database._reward("classic", 1, False, None)
    assert prices["p_uzum"] > prices["s_ananas"]
    assert prices["pre_brilliant"] > prices["p_limon"]
