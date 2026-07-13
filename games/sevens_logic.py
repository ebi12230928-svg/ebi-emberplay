"""
七並べ。52枚を均等に配り、各スートの7から左右に数字を伸ばして並べていく。
自分の番に出せるカードがなければパス。手札を先に出し切った人の勝ち。
"""
from . import cards_common as cc


def new_game(player_ids, rules):
    deck = cc.make_deck(with_joker=False)
    hands = cc.deal_even(deck, player_ids)
    return {
        "hands": {str(pid): hands[pid] for pid in player_ids},
        "turn_order": list(player_ids), "turn_index": 0,
        "table": {s: {"min": None, "max": None} for s in range(4)},
        "winner": None, "rules": rules,
        "log": ["ゲーム開始!各スートの7から数字を伸ばして出していこう。"],
    }


def current_turn_player(state):
    if state["winner"]:
        return None
    return state["turn_order"][state["turn_index"] % len(state["turn_order"])]


def _playable(state, card):
    suit = cc.suit_of(card)
    rank = cc.rank_of(card)
    entry = state["table"][suit]
    if rank == 7:
        return entry["min"] is None
    if entry["min"] is None:
        return False
    return rank == entry["min"] - 1 or rank == entry["max"] + 1


def legal_cards(state, user_id):
    hand = state["hands"].get(str(user_id), [])
    return [c for c in hand if _playable(state, c)]


def apply_play(state, user_id, card):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    hand = state["hands"][str(user_id)]
    if card not in hand:
        return "手札にないカードです。"
    if not _playable(state, card):
        return "そのカードは今出せません。"

    hand.remove(card)
    suit, rank = cc.suit_of(card), cc.rank_of(card)
    entry = state["table"][suit]
    if rank == 7:
        entry["min"] = entry["max"] = 7
    elif rank < entry["min"]:
        entry["min"] = rank
    else:
        entry["max"] = rank

    state["log"].append(f"{{name}}が{cc.card_label(card)}を出した!")

    if not hand:
        state["winner"] = user_id
        state["log"].append("{name}が手札を出し切って勝利!")
        return None

    state["turn_index"] += 1
    return None


def apply_pass(state, user_id):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if legal_cards(state, user_id):
        return "出せるカードがあります。出してください。"
    state["log"].append("{name}がパスした。")
    state["turn_index"] += 1
    return None
