"""ババ抜きのゲームロジック。ジョーカーを1枚含む53枚から1枚減らして配り、ペアを揃えて手札を減らしていく。"""
import random
from collections import Counter
from . import cards_common as cc


def new_game(player_ids, rules):
    deck = cc.make_deck(with_joker=True)
    deck.pop()  # 53枚から1枚除いて、ペアが必ず1枚余る(ジョーカー)状態にする
    hands_raw = cc.deal_even(deck, player_ids)

    hands = {}
    log = ["ゲーム開始!最初のペアを揃えて捨てます。"]
    for pid in player_ids:
        hand = hands_raw[pid]
        hands[str(pid)] = _discard_pairs(hand)

    return {
        "hands": hands,
        "turn_order": list(player_ids),
        "turn_index": 0,
        "out": [],
        "loser": None,
        "rules": rules,
        "log": log,
    }


def _discard_pairs(hand):
    """同じランクのペアを自動で捨てる(ジョーカーはペア対象外)。ペアは2枚とも取り除く"""
    counts = Counter(cc.rank_of(c) for c in hand if c != 52)
    # 偶数枚あるランクは全て捨てる、奇数枚あるランクは1枚だけ手元に残す
    keep_one_more = {r for r, n in counts.items() if n % 2 == 1}
    result = []
    for c in hand:
        if c == 52:
            result.append(c)
            continue
        r = cc.rank_of(c)
        if counts[r] >= 2:
            if r in keep_one_more:
                result.append(c)
                keep_one_more.discard(r)  # 1枚だけ残したら、以降の同ランクは全て捨てる
            # counts[r] >= 2 かつ keep_one_more対象外の場合は捨てる(何もしない)
        else:
            result.append(c)
    return result


def _active_players(state):
    out = set(state["out"])
    return [p for p in state["turn_order"] if p not in out]


def current_turn_player(state):
    active = _active_players(state)
    if len(active) <= 1:
        return None
    idx = state["turn_index"] % len(active)
    return active[idx]


def apply_draw(state, user_id):
    """user_idが、自分の次の手番の相手からカードを1枚引く"""
    active = _active_players(state)
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"

    idx = active.index(user_id)
    target = active[(idx + 1) % len(active)]
    target_hand = state["hands"][str(target)]
    if not target_hand:
        return "相手の手札がありません。"

    drawn = target_hand.pop(random.randrange(len(target_hand)))
    my_hand = state["hands"][str(user_id)]
    my_hand.append(drawn)
    state["hands"][str(user_id)] = _discard_pairs(my_hand)

    state["log"].append("{name}が{target_name}からカードを1枚引いた。")

    if not target_hand:
        state["out"].append(target)
        state["log"].append("{target_name}の手札が無くなり上がった!")

    my_hand_after = state["hands"][str(user_id)]
    if not my_hand_after and user_id not in state["out"]:
        state["out"].append(user_id)
        state["log"].append("{name}の手札が無くなり上がった!")

    active2 = _active_players(state)
    if len(active2) <= 1:
        if active2:
            state["loser"] = active2[0]
            state["log"].append("{loser_name}がジョーカーを持ったまま敗北…")
        return None

    if target in active2:
        state["turn_index"] = active2.index(target)
    else:
        state["turn_index"] = state["turn_index"] % len(active2)
    return None
