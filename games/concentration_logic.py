"""神経衰弱。52枚を裏向きに並べ、2枚めくって同じランクならペア成立で自分の得点、外れたら手番交代。"""
from . import cards_common as cc


def new_game(player_ids, rules):
    deck = cc.make_deck(with_joker=False)
    return {
        "board": deck,
        "revealed": [],
        "matched": [False] * 52,
        "scores": {str(pid): 0 for pid in player_ids},
        "turn_order": list(player_ids), "turn_index": 0,
        "winner": None, "is_draw": False, "rules": rules,
        "last_pair_result": None,  # "match" / "miss" / None(直前の結果。演出用)
        "log": ["ゲーム開始!2枚めくって同じランクを揃えよう。"],
    }


def current_turn_player(state):
    if state["winner"] is not None or state.get("is_draw"):
        return None
    return state["turn_order"][state["turn_index"] % len(state["turn_order"])]


def apply_flip(state, user_id, position):
    if current_turn_player(state) != user_id:
        return "あなたの手番ではありません。"
    if not (0 <= position < 52) or state["matched"][position] or position in state["revealed"]:
        return "そのカードはめくれません。"
    if len(state["revealed"]) >= 2:
        state["revealed"] = []

    state["revealed"].append(position)
    state["log"].append("{name}がカードをめくった。")

    if len(state["revealed"]) < 2:
        return None

    p1, p2 = state["revealed"]
    card1, card2 = state["board"][p1], state["board"][p2]
    if cc.rank_of(card1) == cc.rank_of(card2):
        state["matched"][p1] = True
        state["matched"][p2] = True
        state["scores"][str(user_id)] += 1
        state["last_pair_result"] = "match"
        state["log"].append("ペア成立!もう一度めくれます。")
        if all(state["matched"]):
            _finish(state)
    else:
        state["last_pair_result"] = "miss"
        state["log"].append("ペアになりませんでした。次の人の番です。")
        state["turn_index"] += 1
    return None


def _finish(state):
    scores = state["scores"]
    max_score = max(scores.values())
    leaders = [uid for uid, s in scores.items() if s == max_score]
    if len(leaders) == 1:
        state["winner"] = int(leaders[0])
        state["log"].append("全て揃いました!ゲーム終了。")
    else:
        state["is_draw"] = True
        state["log"].append("全て揃いました!同点で引き分けです。")
