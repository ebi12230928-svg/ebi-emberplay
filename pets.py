"""
ペット(相棒)システム。1人1匹まで育てられる。エサ(Embers)を与えるとXPが貯まりレベルアップし、
レベルに応じてカジノ全体の勝利額に小さなボーナスがかかるようになる。
"""
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Pet

pets_bp = Blueprint("pets", __name__)

SPECIES = {
    "dragon": {"name": "ドラゴン", "icon": "🐉"},
    "cat": {"name": "ねこ", "icon": "🐱"},
    "slime": {"name": "スライム", "icon": "🟢"},
    "phoenix": {"name": "フェニックス", "icon": "🔥"},
    "wolf": {"name": "オオカミ", "icon": "🐺"},
}

FEED_COST = 20
XP_PER_FEED = 15
XP_PER_LEVEL = 100


def xp_needed_for(level):
    return XP_PER_LEVEL + (level - 1) * 25


def pet_bonus_percent(level):
    """レベルに応じたカジノ勝利額ボーナス(%)。5レベルごとに+1%、最大20%"""
    return min(20, (level // 5))


def get_pet_bonus_multiplier(user_id):
    """credit_winnings/credit_rewardから呼び出す用。ペットが居なければ1.0倍"""
    pet = Pet.query.filter_by(user_id=user_id).first()
    if not pet:
        return 1.0
    return 1 + pet_bonus_percent(pet.level) / 100


@pets_bp.route("/pets")
@login_required
def index():
    pet = Pet.query.filter_by(user_id=current_user.id).first()
    return render_template(
        "pets.html", pet=pet, species=SPECIES, feed_cost=FEED_COST,
        xp_needed=xp_needed_for(pet.level) if pet else None,
        bonus_percent=pet_bonus_percent(pet.level) if pet else 0,
        next_bonus_level=((pet.level // 5) + 1) * 5 if pet else 5,
    )


@pets_bp.route("/pets/create", methods=["POST"])
@login_required
def create():
    if Pet.query.filter_by(user_id=current_user.id).first():
        flash("すでに相棒がいます。", "error")
        return redirect(url_for("pets.index"))

    name = request.form.get("name", "").strip()[:32]
    species = request.form.get("species", "dragon")
    if not name:
        flash("名前を入力してください。", "error")
        return redirect(url_for("pets.index"))
    if species not in SPECIES:
        species = "dragon"

    pet = Pet(user_id=current_user.id, name=name, species=species, level=1, xp=0)
    db.session.add(pet)
    db.session.commit()
    flash(f"{name}が仲間になりました!", "success")
    return redirect(url_for("pets.index"))


@pets_bp.route("/pets/feed", methods=["POST"])
@login_required
def feed():
    pet = Pet.query.filter_by(user_id=current_user.id).first()
    if not pet:
        return jsonify({"error": "相棒がいません。"}), 400
    if current_user.balance < FEED_COST:
        return jsonify({"error": "Embersが足りません。"}), 400

    current_user.balance -= FEED_COST
    pet.xp += XP_PER_FEED

    leveled_up = False
    while pet.xp >= xp_needed_for(pet.level):
        pet.xp -= xp_needed_for(pet.level)
        pet.level += 1
        leveled_up = True

    db.session.commit()
    return jsonify({
        "ok": True, "balance": current_user.balance, "level": pet.level, "xp": pet.xp,
        "xp_needed": xp_needed_for(pet.level), "leveled_up": leveled_up,
        "bonus_percent": pet_bonus_percent(pet.level),
    })
