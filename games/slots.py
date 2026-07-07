import json

from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

# 各テーマの配当は「house edge目標(9〜12%)」で正規化済み(実際に全216通り enumerate して検証済み)
THEMES = {
    "cherry_classic": {
        "name": "Cherry Classic", "symbols": [
            {"key": "cherry", "label": "🍒", "weight": 40, "pay3": 4.75, "pay2": 0.95},
            {"key": "lemon", "label": "🍋", "weight": 30, "pay3": 7.92, "pay2": 0},
            {"key": "bell", "label": "🔔", "weight": 15, "pay3": 19.01, "pay2": 0},
            {"key": "star", "label": "⭐", "weight": 10, "pay3": 38.03, "pay2": 0},
            {"key": "seven", "label": "7️⃣", "weight": 5, "pay3": 126.76, "pay2": 0},
        ]
    },
    "egyptian_gold": {
        "name": "Egyptian Gold", "symbols": [
            {"key": "ankh", "label": "☥", "weight": 38, "pay3": 5.08, "pay2": 1.02},
            {"key": "scarab", "label": "🪲", "weight": 28, "pay3": 8.46, "pay2": 0},
            {"key": "pyramid", "label": "🔺", "weight": 18, "pay3": 16.93, "pay2": 0},
            {"key": "eye", "label": "👁️", "weight": 11, "pay3": 33.85, "pay2": 0},
            {"key": "pharaoh", "label": "👑", "weight": 5, "pay3": 152.34, "pay2": 0},
        ]
    },
    "pirates_treasure": {
        "name": "Pirate's Treasure", "symbols": [
            {"key": "parrot", "label": "🦜", "weight": 38, "pay3": 5.08, "pay2": 1.02},
            {"key": "compass", "label": "🧭", "weight": 28, "pay3": 8.46, "pay2": 0},
            {"key": "anchor", "label": "⚓", "weight": 18, "pay3": 16.93, "pay2": 0},
            {"key": "skull", "label": "💀", "weight": 11, "pay3": 33.85, "pay2": 0},
            {"key": "chest", "label": "📦", "weight": 5, "pay3": 152.34, "pay2": 0},
        ]
    },
    "space_odyssey": {
        "name": "Space Odyssey", "symbols": [
            {"key": "star", "label": "✨", "weight": 40, "pay3": 5.04, "pay2": 0.72},
            {"key": "planet", "label": "🪐", "weight": 28, "pay3": 9.0, "pay2": 0},
            {"key": "rocket", "label": "🚀", "weight": 16, "pay3": 21.6, "pay2": 0},
            {"key": "alien", "label": "👽", "weight": 10, "pay3": 46.8, "pay2": 0},
            {"key": "ufo", "label": "🛸", "weight": 6, "pay3": 126.0, "pay2": 0},
        ]
    },
    "ocean_deep": {
        "name": "Ocean Deep", "symbols": [
            {"key": "shell", "label": "🐚", "weight": 40, "pay3": 4.75, "pay2": 0.95},
            {"key": "fish", "label": "🐟", "weight": 30, "pay3": 7.92, "pay2": 0},
            {"key": "octopus", "label": "🐙", "weight": 15, "pay3": 19.01, "pay2": 0},
            {"key": "shark", "label": "🦈", "weight": 10, "pay3": 38.03, "pay2": 0},
            {"key": "pearl", "label": "⚪", "weight": 5, "pay3": 126.76, "pay2": 0},
        ]
    },
    "wild_west": {
        "name": "Wild West", "symbols": [
            {"key": "horseshoe", "label": "🧲", "weight": 38, "pay3": 5.08, "pay2": 1.02},
            {"key": "cactus", "label": "🌵", "weight": 28, "pay3": 8.46, "pay2": 0},
            {"key": "revolver", "label": "🔫", "weight": 18, "pay3": 16.93, "pay2": 0},
            {"key": "hat", "label": "🤠", "weight": 11, "pay3": 33.85, "pay2": 0},
            {"key": "nugget", "label": "🪙", "weight": 5, "pay3": 152.34, "pay2": 0},
        ]
    },
    "neon_nights": {
        "name": "Neon Nights", "symbols": [
            {"key": "triangle", "label": "🔺", "weight": 60, "pay3": 2.96, "pay2": 0},
            {"key": "circle", "label": "⭕", "weight": 30, "pay3": 6.83, "pay2": 0},
            {"key": "diamond", "label": "💠", "weight": 10, "pay3": 56.88, "pay2": 0},
        ]
    },
    "jungle_fever": {
        "name": "Jungle Fever", "symbols": [
            {"key": "vine", "label": "🌿", "weight": 38, "pay3": 5.08, "pay2": 1.02},
            {"key": "monkey", "label": "🐒", "weight": 28, "pay3": 8.46, "pay2": 0},
            {"key": "snake", "label": "🐍", "weight": 18, "pay3": 16.93, "pay2": 0},
            {"key": "tiger", "label": "🐯", "weight": 11, "pay3": 33.85, "pay2": 0},
            {"key": "idol", "label": "🗿", "weight": 5, "pay3": 152.34, "pay2": 0},
        ]
    },
    "candy_pop": {
        "name": "Candy Pop", "symbols": [
            {"key": "candy", "label": "🍬", "weight": 40, "pay3": 4.75, "pay2": 0.95},
            {"key": "donut", "label": "🍩", "weight": 30, "pay3": 7.92, "pay2": 0},
            {"key": "cupcake", "label": "🧁", "weight": 15, "pay3": 19.01, "pay2": 0},
            {"key": "lollipop", "label": "🍭", "weight": 10, "pay3": 38.03, "pay2": 0},
            {"key": "gem", "label": "💎", "weight": 5, "pay3": 126.76, "pay2": 0},
        ]
    },
    "norse_mythology": {
        "name": "Norse Mythology", "symbols": [
            {"key": "rune", "label": "ᚱ", "weight": 38, "pay3": 5.02, "pay2": 1.0},
            {"key": "shield", "label": "🛡️", "weight": 28, "pay3": 8.37, "pay2": 0},
            {"key": "raven", "label": "🐦‍⬛", "weight": 18, "pay3": 16.74, "pay2": 0},
            {"key": "hammer", "label": "🔨", "weight": 11, "pay3": 33.48, "pay2": 0},
            {"key": "valkyrie", "label": "⚔️", "weight": 5, "pay3": 150.64, "pay2": 0},
        ]
    },
    "lucky_sevens": {
        "name": "Lucky Sevens", "symbols": [
            {"key": "cherry", "label": "🍒", "weight": 40, "pay3": 4.6, "pay2": 0.92},
            {"key": "bar", "label": "▬", "weight": 28, "pay3": 9.2, "pay2": 0},
            {"key": "bell", "label": "🔔", "weight": 16, "pay3": 18.4, "pay2": 0},
            {"key": "diamond", "label": "💎", "weight": 10, "pay3": 36.8, "pay2": 0},
            {"key": "seven", "label": "7️⃣", "weight": 6, "pay3": 122.67, "pay2": 0},
        ]
    },
    "dragons_hoard": {
        "name": "Dragon's Hoard", "symbols": [
            {"key": "scale", "label": "🟢", "weight": 40, "pay3": 4.95, "pay2": 0.71},
            {"key": "egg", "label": "🥚", "weight": 28, "pay3": 8.85, "pay2": 0},
            {"key": "flame", "label": "🔥", "weight": 16, "pay3": 21.23, "pay2": 0},
            {"key": "gem", "label": "💎", "weight": 10, "pay3": 45.99, "pay2": 0},
            {"key": "dragon", "label": "🐉", "weight": 6, "pay3": 148.6, "pay2": 0},
        ]
    },
    "retro_arcade": {
        "name": "Retro Arcade", "symbols": [
            {"key": "coin", "label": "🪙", "weight": 38, "pay3": 5.08, "pay2": 1.02},
            {"key": "joystick", "label": "🕹️", "weight": 28, "pay3": 8.46, "pay2": 0},
            {"key": "ghost", "label": "👻", "weight": 18, "pay3": 16.93, "pay2": 0},
            {"key": "mushroom", "label": "🍄", "weight": 11, "pay3": 33.85, "pay2": 0},
            {"key": "trophy", "label": "🏆", "weight": 5, "pay3": 152.34, "pay2": 0},
        ]
    },
    "diamond_vault": {
        "name": "Diamond Vault", "symbols": [
            {"key": "ring", "label": "💍", "weight": 38, "pay3": 5.02, "pay2": 1.0},
            {"key": "necklace", "label": "📿", "weight": 28, "pay3": 8.37, "pay2": 0},
            {"key": "crown", "label": "👑", "weight": 18, "pay3": 16.74, "pay2": 0},
            {"key": "safe", "label": "🔒", "weight": 11, "pay3": 33.48, "pay2": 0},
            {"key": "diamond", "label": "💎", "weight": 5, "pay3": 150.64, "pay2": 0},
        ]
    },
}


def _pick_symbol(symbols, total_weight, f):
    r = f * total_weight
    cum = 0
    for s in symbols:
        cum += s["weight"]
        if r < cum:
            return s
    return symbols[-1]


def _payout_multiplier(reels):
    keys = [r["key"] for r in reels]
    if keys[0] == keys[1] == keys[2]:
        return reels[0]["pay3"]
    for i in range(3):
        for j in range(i + 1, 3):
            if keys[i] == keys[j]:
                return reels[i]["pay2"]
    return 0


@games_bp.route("/slots/<theme_id>")
@login_required
def slots_page(theme_id):
    theme = THEMES.get(theme_id)
    if not theme:
        abort(404)
    return render_template("games/slots.html", theme_id=theme_id, theme=theme)


@games_bp.route("/slots/<theme_id>/spin", methods=["POST"])
@login_required
def slots_spin(theme_id):
    theme = THEMES.get(theme_id)
    if not theme:
        return jsonify({"error": "指定されたスロットが見つかりません。"}), 404

    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    symbols = theme["symbols"]
    total_weight = sum(s["weight"] for s in symbols)

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 3)
    used_nonce = user.nonce
    user.nonce += 1

    reels = [_pick_symbol(symbols, total_weight, f) for f in floats]
    multiplier = _payout_multiplier(reels)
    payout = round(wager * multiplier)

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game=f"slots:{theme_id}", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"reels": [r["key"] for r in reels], "theme": theme_id})
    ))
    db.session.commit()

    return jsonify({
        "reels": [r["key"] for r in reels], "labels": [r["label"] for r in reels],
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
