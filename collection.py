"""キャラクター図鑑・ステータス確認ページ(RPG的な収集・育成要素)"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from models import UserCharacter
import characters as ch

collection_bp = Blueprint("collection", __name__)


@collection_bp.route("/collection")
@login_required
def index():
    owned_rows = UserCharacter.query.filter_by(user_id=current_user.id).all()
    owned = {}
    for row in owned_rows:
        info = ch.stats_at_level(row.character_key, row.count)
        if info:
            info["count"] = row.count
            owned[row.character_key] = info

    roster = []
    for key in ch.CHARACTERS:
        if key in owned:
            roster.append(owned[key])
        else:
            base = ch.character_info(key)
            base["locked"] = True
            roster.append(base)

    roster.sort(key=lambda c: (["common", "rare", "epic", "legendary"].index(c["rarity"]), c["name"]))

    total_power = sum(c["attack"] for c in owned.values())

    return render_template(
        "collection.html", roster=roster, owned_count=len(owned), total_count=len(ch.CHARACTERS),
        total_power=round(total_power, 1)
    )
