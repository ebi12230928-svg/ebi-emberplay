"""
スピード(2人用)のゲームロジック。手札から、場の2つの山より1つ大きい/小さいランクのカードを出していく。
先に手札(+補充札)を全て出し切った方の勝ち。両者とも出せない場合は補充札から場を作り直す。
"""
from . import cards_common as cc

HAND_SIZE = 5


def new_game(player_ids, rules):
    if len(player_ids) != 2:
        raise ValueError("スピードは2人でのみプレイできます")
    deck = cc.make_deck(with_joker=False)
    p1, p2 = player_ids

    hands = {}
    stocks = {}
    for i, pid in enumerate(player_ids):
        start = i * 26
        cards = deck[start:start + 26]
        hands[str(pid)] = cards[:HAND_SIZE]
        stocks[str(pid)] = cards[HAND_SIZE:]

    center = [stocks[str(p1)].pop(0), stocks[str(p2)].pop(0)]

    return {
        "hands": hands, "stocks": stocks, "center": center,
        "turn_order": list(player_ids), "winner": None,
        "rules": rules, "log": ["ゲーム開始!場のカードと連続するランクを出していこう。"],
    }


def _can_place(card, center_card):
    r1, r2 = cc.rank_of(card), cc.rank_of(center_card)
    diff = abs(r1 - r2)
    return diff == 1 or diff == 12  # 12はA-Kのつながり(ラップアラウンド)を許可


def legal_moves(state, user_id):
    hand = state["hands"].get(str(user_id), [])
    moves = []
    for c in hand:
        for pile_idx, center_card in enumerate(state["center"]):
            if _can_place(c, center_card):
                moves.append((c, pile_idx))
    return moves


def apply_play(state, user_id, card, pile_idx):
    hand = state["hands"][str(user_id)]
    if card not in hand:
        return "手札にないカードです。"
    if pile_idx not in (0, 1):
        return "出す山の指定が不正です。"
    if not _can_place(card, state["center"][pile_idx]):
        return "そのカードはそこには出せません(連続するランクのみ)。"

    hand.remove(card)
    state["center"][pile_idx] = card
    state["log"].append(f"{{name}}が{cc.card_label(card)}を出した!")

    stock = state["stocks"][str(user_id)]
    if len(hand) < HAND_SIZE and stock:
        hand.append(stock.pop(0))

    if not hand and not stock:
        state["winner"] = user_id
        state["log"].append("{name}が手札を出し切って勝利!")
    return None


def both_stuck(state):
    for pid in state["turn_order"]:
        if legal_moves(state, pid):
            return False
    return True


def refill_center(state):
    for i, pid in enumerate(state["turn_order"]):
        stock = state["stocks"][str(pid)]
        if stock:
            state["center"][i] = stock.pop(0)
    state["log"].append("両者とも手詰まり。場を補充札から作り直しました。")
