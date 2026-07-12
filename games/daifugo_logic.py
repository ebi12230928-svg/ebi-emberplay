"""
大富豪(だいふごう)のゲームロジック。純粋な状態遷移関数のみを扱う(DB・Flaskに依存しない)。
ルール: 場に出ているカードと同じ枚数・同ランクを出す。前の場より強いランクでないと出せない。
オプションルール: 8切り(8を出すと場が流れる)、革命(4枚同時出しで強さが逆転)。
"""
from . import cards_common as cc


def _strength(rank):
    if rank == 1:
        return 14  # A
    if rank == 2:
        return 15  # 2(最強)
    return rank


def new_game(player_ids, rules):
    deck = cc.make_deck(with_joker=False)
    hands = cc.deal_even(deck, player_ids)
    return {
        "hands": {str(pid): hands[pid] for pid in player_ids},
        "turn_order": list(player_ids),
        "turn_index": 0,
        "pile": [],
        "pile_owner": None,
        "passed": [],
        "finished_order": [],
        "revolution": False,
        "rules": rules,
        "log": ["ゲーム開始!カードが配られました。"],
    }


def _active_players(state):
    finished = set(state["finished_order"])
    return [p for p in state["turn_order"] if p not in finished]


def current_turn_player(state):
    active = _active_players(state)
    if not active:
        return None
    idx = state["turn_index"] % len(active)
    return active[idx]


def _effective_strength(state, rank):
    s = _strength(rank)
    if state.get("revolution"):
        return 100 - s
    return s


def legal_play(state, user_id, cards):
    hand = state["hands"].get(str(user_id), [])
    if not cards or any(c not in hand for c in cards):
        return "手札にないカードが含まれています。"
    ranks = set(cc.rank_of(c) for c in cards)
    if len(ranks) != 1:
        return "同じランクのカードしか同時に出せません。"
    rank = ranks.pop()

    if state["pile"]:
        if len(cards) != len(state["pile"]):
            return f"場と同じ枚数({len(state['pile'])}枚)を出してください。"
        pile_rank = cc.rank_of(state["pile"][0])
        if _effective_strength(state, rank) <= _effective_strength(state, pile_rank):
            return "場のカードより強いランクを出してください。"
    return None


def apply_play(state, user_id, cards):
    err = legal_play(state, user_id, cards)
    if err:
        return err

    hand = state["hands"][str(user_id)]
    for c in cards:
        hand.remove(c)
    state["pile"] = list(cards)
    state["pile_owner"] = user_id
    state["passed"] = []

    rank = cc.rank_of(cards[0])
    labels = "・".join(cc.card_label(c) for c in cards)
    state["log"].append(f"{{name}}が {labels} を出した!")

    rules = state.get("rules", {})
    cleared = False
    if rules.get("eight_giri") and rank == 8:
        state["log"].append("8切り!場が流れます。")
        cleared = True
    if rules.get("revolution") and len(cards) == 4:
        state["revolution"] = not state["revolution"]
        state["log"].append("革命が発生!強さが逆転した!")

    if not hand:
        state["finished_order"].append(user_id)
        state["log"].append(f"{{name}}が上がった!(第{len(state['finished_order'])}位)")

    active = _active_players(state)
    if len(active) <= 1:
        if active:
            state["finished_order"].append(active[0])
        state["log"].append("ゲーム終了!")
        return None

    if cleared:
        state["pile"] = []
        state["pile_owner"] = None
        state["passed"] = []
        if user_id in state["finished_order"]:
            state["turn_index"] = 0
        else:
            state["turn_index"] = active.index(user_id) if user_id in active else 0
    else:
        if user_id in state["finished_order"]:
            state["turn_index"] = state["turn_index"] % max(1, len(active))
        else:
            state["turn_index"] = (active.index(user_id) + 1) % len(active)
    return None


def apply_pass(state, user_id):
    active = _active_players(state)
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if not state["pile"]:
        return "場が空の時はパスできません(何か出してください)。"

    state["passed"].append(user_id)
    state["log"].append("{name}がパスした。")

    remaining = [p for p in active if p not in state["passed"]]
    if len(remaining) <= 1:
        state["pile"] = []
        state["passed"] = []
        winner = state["pile_owner"]
        active2 = _active_players(state)
        if winner in active2:
            state["turn_index"] = active2.index(winner)
        else:
            state["turn_index"] = 0
        state["log"].append("全員パス。場が流れます。")
    else:
        state["turn_index"] = (state["turn_index"] + 1) % len(active)
    return None
