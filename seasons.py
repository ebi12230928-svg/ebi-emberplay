"""
シーズン制のエンドレスモードランキング・シーズンパス機能。
シーズンが終わると、エンドレスランキング1位に管理者が指定したレアリティのキャラクターが贈られる。
シーズンパスは誰でも進められるが、最終ティア(キャラクター報酬)はVIP限定で受け取れる。
"""
import json
import random

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Season, EndlessScore, SeasonPassProgress, UserCharacter, Transaction
import characters as ch

seasons_bp = Blueprint("seasons", __name__)

# シーズンパスの各ティア(累計ポイントで解放)。最終ティアだけキャラクター報酬・VIP限定
SEASON_PASS_TIERS = [
    {"points": 50, "reward_type": "embers", "amount": 100},
    {"points": 120, "reward_type": "embers", "amount": 150},
    {"points": 220, "reward_type": "embers", "amount": 200},
    {"points": 350, "reward_type": "embers", "amount": 300},
    {"points": 500, "reward_type": "embers", "amount": 400},
    {"points": 700, "reward_type": "embers", "amount": 500},
    {"points": 950, "reward_type": "embers", "amount": 700},
    {"points": 1250, "reward_type": "embers", "amount": 900},
    {"points": 1600, "reward_type": "embers", "amount": 1200},
    {"points": 2000, "reward_type": "character", "vip_only": True},
]

POINTS_PER_REWARD = 10  # 獲得Embers10につき1シーズンポイント


def get_current_season():
    season = Season.query.filter_by(status="active").order_by(Season.number.desc()).first()
    if not season:
        season = Season(number=1, endless_reward_rarity="epic", pass_reward_rarity="epic")
        db.session.add(season)
        db.session.commit()
    return season


def _get_or_create_pass(user, season):
    progress = SeasonPassProgress.query.filter_by(user_id=user.id, season_id=season.id).first()
    if not progress:
        progress = SeasonPassProgress(user_id=user.id, season_id=season.id, points=0)
        db.session.add(progress)
        db.session.commit()
    return progress


def award_season_points(user, reward_amount):
    """ゲームの報酬額に応じてシーズンパスのポイントを加算する(TD/RPGの各completeルートから呼ばれる)"""
    if reward_amount <= 0:
        return
    season = get_current_season()
    progress = _get_or_create_pass(user, season)
    progress.points += max(1, reward_amount // POINTS_PER_REWARD)
    db.session.commit()


def record_endless_score(user, mode, score):
    """エンドレスモードの記録を保存する(TD/RPGのエンドレス完了時に呼ばれる)"""
    if score <= 0:
        return
    season = get_current_season()
    db.session.add(EndlessScore(user_id=user.id, season_id=season.id, mode=mode, score=score))
    db.session.commit()


def _rarity_excluding_ebi(rarity):
    """指定レアリティの中から「えび」を除いたキーを1つランダムに選ぶ"""
    keys = [k for k in ch.all_keys_by_rarity(rarity) if k != "ebi"]
    if not keys:
        keys = [k for k in ch.all_keys_by_rarity("epic") if k != "ebi"]  # 万一空なら安全にepicへフォールバック
    return random.choice(keys)


def _grant_character(user, key):
    row = UserCharacter.query.filter_by(user_id=user.id, character_key=key).first()
    if row:
        row.count += 1
    else:
        row = UserCharacter(user_id=user.id, character_key=key, count=1)
        db.session.add(row)


def _preview_rarity_char(rarity):
    keys = [k for k in ch.all_keys_by_rarity(rarity) if k != "ebi"]
    return keys[0] if keys else "ebi"


@seasons_bp.route("/seasons")
@login_required
def index():
    season = get_current_season()
    progress = _get_or_create_pass(current_user, season)
    claimed = json.loads(progress.claimed_tiers_json)

    tiers = []
    for i, tier in enumerate(SEASON_PASS_TIERS):
        tiers.append({
            "index": i, "points": tier["points"], "reward_type": tier["reward_type"],
            "amount": tier.get("amount"), "vip_only": tier.get("vip_only", False),
            "unlocked": progress.points >= tier["points"], "claimed": i in claimed,
            "rarity_label": ch.RARITY_NAMES.get(season.pass_reward_rarity) if tier["reward_type"] == "character" else None,
        })

    td_ranking = (
        db.session.query(EndlessScore.user_id, db.func.max(EndlessScore.score).label("best"))
        .filter_by(season_id=season.id, mode="towerdefense").group_by(EndlessScore.user_id)
        .order_by(db.desc("best")).limit(10).all()
    )
    rpg_ranking = (
        db.session.query(EndlessScore.user_id, db.func.max(EndlessScore.score).label("best"))
        .filter_by(season_id=season.id, mode="rpgboss").group_by(EndlessScore.user_id)
        .order_by(db.desc("best")).limit(10).all()
    )

    from models import User
    td_board = [{"username": User.query.get(uid).username, "score": best} for uid, best in td_ranking]
    rpg_board = [{"username": User.query.get(uid).username, "score": best} for uid, best in rpg_ranking]

    return render_template(
        "seasons.html", season=season, progress=progress, tiers=tiers,
        td_board=td_board, rpg_board=rpg_board, is_vip=current_user.is_vip
    )


@seasons_bp.route("/seasons/pass/claim/<int:tier_index>", methods=["POST"])
@login_required
def claim_tier(tier_index):
    if not (0 <= tier_index < len(SEASON_PASS_TIERS)):
        return jsonify({"error": "不正なティアです。"}), 400

    season = get_current_season()
    progress = _get_or_create_pass(current_user, season)
    claimed = json.loads(progress.claimed_tiers_json)

    if tier_index in claimed:
        return jsonify({"error": "すでに受け取り済みです。"}), 400

    tier = SEASON_PASS_TIERS[tier_index]
    if progress.points < tier["points"]:
        return jsonify({"error": "ポイントが不足しています。"}), 400
    if tier.get("vip_only") and not current_user.is_vip:
        return jsonify({"error": "この報酬はVIP限定です。"}), 403

    if tier["reward_type"] == "embers":
        current_user.balance += tier["amount"]
        db.session.add(Transaction(
            user_id=current_user.id, amount=tier["amount"], kind="season_pass",
            description=f"シーズンパス ティア{tier_index + 1} 報酬"
        ))
        message = f"{tier['amount']} Embersを受け取りました。"
    else:
        key = _rarity_excluding_ebi(season.pass_reward_rarity)
        _grant_character(current_user, key)
        info = ch.character_info(key)
        message = f"「{info['name']}」を受け取りました!"

    claimed.append(tier_index)
    progress.claimed_tiers_json = json.dumps(claimed)
    db.session.commit()

    return jsonify({"ok": True, "message": message, "balance": current_user.balance})
