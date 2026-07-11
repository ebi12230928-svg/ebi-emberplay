"""ガチャ機能。Embersを消費してキャラクターを入手する。必要ポイントは管理者が設定可能。"""
import random

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import GachaSetting, UserCharacter, Transaction
import characters as ch

gacha_bp = Blueprint("gacha", __name__)

DEFAULT_COST_SINGLE = 200
DEFAULT_COST_TEN = 1800


def _get_settings():
    row = GachaSetting.query.get("default")
    if not row:
        row = GachaSetting(key="default", cost_single=DEFAULT_COST_SINGLE, cost_ten=DEFAULT_COST_TEN)
        db.session.add(row)
        db.session.commit()
    return row


def _roll_one(force_min_rarity=None):
    rarities = list(ch.RARITY_WEIGHTS.keys())
    weights = list(ch.RARITY_WEIGHTS.values())

    if force_min_rarity:
        order = ["common", "rare", "epic", "legendary", "ultimate"]
        min_idx = order.index(force_min_rarity)
        allowed = order[min_idx:]
        rarities = [r for r in rarities if r in allowed]
        weights = [ch.RARITY_WEIGHTS[r] for r in rarities]

    rarity = random.choices(rarities, weights=weights, k=1)[0]

    if rarity == "ultimate":
        # アルティメット内はさらに重み付き抽選(「えび」だけ桁違いに低い確率)
        keys = list(ch.ULTIMATE_WEIGHTS.keys())
        w = list(ch.ULTIMATE_WEIGHTS.values())
        return random.choices(keys, weights=w, k=1)[0]

    key = random.choice(ch.all_keys_by_rarity(rarity))
    return key


def _grant_character(user, key):
    """キャラクターを付与し、既に持っていれば所持数(レベル)を増やす。結果として新規かどうかを返す"""
    row = UserCharacter.query.filter_by(user_id=user.id, character_key=key).first()
    if row:
        row.count += 1
        is_new = False
    else:
        row = UserCharacter(user_id=user.id, character_key=key, count=1)
        db.session.add(row)
        is_new = True
    return is_new, row.count


@gacha_bp.route("/gacha")
@login_required
def index():
    settings = _get_settings()
    owned = {c.character_key: c.count for c in UserCharacter.query.filter_by(user_id=current_user.id).all()}
    roster = []
    for key in ch.all_characters_dict():
        info = ch.character_info(key)
        info["owned_count"] = owned.get(key, 0)
        roster.append(info)
    roster.sort(key=lambda c: (["common", "rare", "epic", "legendary", "ultimate"].index(c["rarity"]), c["name"]))

    return render_template(
        "gacha.html", cost_single=settings.cost_single, cost_ten=settings.cost_ten,
        roster=roster, owned_count=len(owned), total_count=len(ch.all_characters_dict())
    )


@gacha_bp.route("/gacha/pull", methods=["POST"])
@login_required
def pull():
    data = request.get_json(force=True)
    count = int(data.get("count", 1))
    if count not in (1, 10):
        return jsonify({"error": "回数の指定が不正です。"}), 400

    settings = _get_settings()
    cost = settings.cost_single if count == 1 else settings.cost_ten

    if current_user.balance < cost:
        return jsonify({"error": "Embersが不足しています。"}), 400

    current_user.balance -= cost
    db.session.add(Transaction(
        user_id=current_user.id, amount=-cost, kind="gacha",
        description=f"ガチャ{count}連" if count > 1 else "ガチャ1回"
    ))

    if count == 1:
        keys = [_roll_one()]
    else:
        keys = [_roll_one() for _ in range(9)]
        keys.append(_roll_one(force_min_rarity="rare"))  # 10連は最後の1枠でレア以上を確定
        random.shuffle(keys)

    results = []
    for key in keys:
        is_new, new_count = _grant_character(current_user, key)
        info = ch.character_info(key)
        info["is_new"] = is_new
        info["new_count"] = new_count
        results.append(info)

    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({"results": results, "balance": current_user.balance})
