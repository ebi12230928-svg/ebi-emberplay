"""称号システム。実績達成で獲得できる称号を、プロフィールに表示できる。"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import Title, UserCharacter, Pet

titles_bp = Blueprint("titles", __name__)

TITLE_CATALOG = {
    "newcomer": {"name": "新参者", "icon": "🔰", "desc": "EMBERPLAYへようこそ!"},
    "collector": {"name": "コレクター", "icon": "📖", "desc": "キャラクターを10種類以上集めた"},
    "master_collector": {"name": "マスターコレクター", "icon": "🏆", "desc": "キャラクターを50種類以上集めた"},
    "pet_lover": {"name": "相棒思い", "icon": "🐾", "desc": "相棒をLv.10まで育てた"},
    "high_roller": {"name": "ハイローラー", "icon": "💰", "desc": "残高が10,000を超えた"},
    "vip": {"name": "VIP", "icon": "👑", "desc": "VIP会員になった"},
    "guild_founder": {"name": "ギルド創設者", "icon": "🛡️", "desc": "ギルドを設立した"},
}


def check_and_grant_titles(user):
    earned_keys = {t.title_key for t in Title.query.filter_by(user_id=user.id).all()}
    newly_earned = []

    def grant(key):
        if key not in earned_keys:
            db.session.add(Title(user_id=user.id, title_key=key))
            earned_keys.add(key)
            newly_earned.append(key)

    grant("newcomer")

    char_count = UserCharacter.query.filter_by(user_id=user.id).count()
    if char_count >= 10:
        grant("collector")
    if char_count >= 50:
        grant("master_collector")

    pet = Pet.query.filter_by(user_id=user.id).first()
    if pet and pet.level >= 10:
        grant("pet_lover")

    if user.balance >= 10000:
        grant("high_roller")
    if user.is_vip:
        grant("vip")

    from models import Guild
    if Guild.query.filter_by(owner_id=user.id).first():
        grant("guild_founder")

    if newly_earned:
        db.session.commit()
    return newly_earned


@titles_bp.route("/titles")
@login_required
def index():
    check_and_grant_titles(current_user)
    earned = {t.title_key for t in Title.query.filter_by(user_id=current_user.id).all()}
    return render_template("titles.html", catalog=TITLE_CATALOG, earned=earned, active=current_user.active_title)


@titles_bp.route("/titles/set", methods=["POST"])
@login_required
def set_active():
    key = request.get_json(force=True).get("title_key")
    earned = {t.title_key for t in Title.query.filter_by(user_id=current_user.id).all()}
    if key is not None and key not in earned:
        return jsonify({"error": "まだ獲得していない称号です。"}), 400

    current_user.active_title = key
    db.session.commit()
    return jsonify({"ok": True})
