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
