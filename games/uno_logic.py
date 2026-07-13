"""
UNOのゲームロジック。カードは辞書 {"color": "red/yellow/green/blue/wild", "value": "0-9/skip/reverse/draw2/wild/wild4"} で表現する。
"""
import random

COLORS = ["red", "yellow", "green", "blue"]
NUMBER_VALUES = [str(n) for n in range(10)]
ACTION_VALUES = ["skip", "reverse", "draw2"]


def _make_deck():
    deck = []
    for color in COLORS:
        deck.append({"color": color, "value": "0"})
        for v in NUMBER_VALUES[1:]:
            deck.append({"color": color, "value": v})
            deck.append({"color": color, "value": v})
        for v in ACTION_VALUES:
            deck.append({"color": color, "value": v})
            deck.append({"color": color, "value": v})
    for _ in range(4):
        deck.append({"color": "wild", "value": "wild"})
        deck.append({"color": "wild", "value": "wild4"})
    random.shuffle(deck)
    return deck


def new_game(player_ids, rules):
    deck = _make_deck()
    hands = {str(pid): [deck.pop() for _ in range(7)] for pid in player_ids}

    top = deck.pop()
    while top["value"] in ACTION_VALUES or top["color"] == "wild":
        deck.insert(0, top)
        random.shuffle(deck)
        top = deck.pop()

    return {
        "hands": hands, "draw_pile": deck, "discard": [top],
        "turn_order": list(player_ids), "turn_index": 0, "direction": 1,
        "current_color": top["color"], "winner": None, "pending_draw": 0,
        "rules": rules, "log": ["ゲーム開始!場のカードと同じ色・数字・記号、またはワイルドを出そう。"],
    }


def current_turn_player(state):
    order = state["turn_order"]
    if not order:
        return None
    return order[state["turn_index"] % len(order)]


def _advance_turn(state, skip=1):
    n = len(state["turn_order"])
    state["turn_index"] = (state["turn_index"] + state["direction"] * skip) % n


def _draw_cards(state, user_id, count):
    hand = state["hands"][str(user_id)]
    for _ in range(count):
        if not state["draw_pile"]:
            top = state["discard"][-1]
            rest = state["discard"][:-1]
            if not rest:
                break
            random.shuffle(rest)
            state["draw_pile"] = rest
            state["discard"] = [top]
        if state["draw_pile"]:
            hand.append(state["draw_pile"].pop())


def _card_playable(card, top, current_color):
    if card["color"] == "wild":
        return True
    return card["color"] == current_color or card["value"] == top["value"]


def apply_play(state, user_id, card_index, chosen_color=None):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    hand = state["hands"][str(user_id)]
    if not (0 <= card_index < len(hand)):
        return "そのカードは手札にありません。"
    card = hand[card_index]
    top = state["discard"][-1]
    if not _card_playable(card, top, state["current_color"]):
        return "そのカードは今出せません(色・数字・記号が一致していません)。"
    if card["color"] == "wild" and chosen_color not in COLORS:
        return "ワイルドを出す場合は色を指定してください。"

    hand.pop(card_index)
    state["discard"].append(card)
    state["current_color"] = chosen_color if card["color"] == "wild" else card["color"]
    state["log"].append(f"{{name}}が {card['color']}{card['value']} を出した!")

    if not hand:
        state["winner"] = user_id
        state["log"].append("{name}が手札を出し切って勝利!")
        return None

    skip = 1
    if card["value"] == "skip":
        skip = 2
        state["log"].append("スキップ!次の人は休みです。")
    elif card["value"] == "reverse":
        state["direction"] *= -1
        state["log"].append("リバース!順番が逆になった。")
        if len(state["turn_order"]) == 2:
            skip = 2
    elif card["value"] == "draw2":
        _advance_turn(state, 1)
        victim = current_turn_player(state)
        _draw_cards(state, victim, 2)
        state["log"].append("次の人は2枚引いて、さらにもう1回休み!")
        skip = 2
        state["turn_index"] = (state["turn_index"] - state["direction"]) % len(state["turn_order"])
    elif card["value"] == "wild4":
        _advance_turn(state, 1)
        victim = current_turn_player(state)
        _draw_cards(state, victim, 4)
        state["log"].append("ワイルドドロー4!次の人は4枚引いて休み!")
        skip = 2
        state["turn_index"] = (state["turn_index"] - state["direction"]) % len(state["turn_order"])

    _advance_turn(state, skip)
    return None


def apply_draw(state, user_id):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    _draw_cards(state, user_id, 1)
    state["log"].append("{name}が山札から1枚引いた。")
    _advance_turn(state, 1)
    return None
