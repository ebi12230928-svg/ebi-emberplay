import secrets
import json
import uuid
import re
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from extensions import db
from models import User, Transaction, RedeemCode, Announcement, GameSetting, Giveaway, Event, TipRequest, GachaSetting, UserCharacter, Season, EndlessScore, CustomCharacter, Poll, CharacterOverride, TDDifficultySetting, Tournament, RhythmSong
from notifications import notify, notify_all
from games.common import MIN_PAYOUT_SCALAR, MAX_PAYOUT_SCALAR

admin_bp = Blueprint("admin", __name__)

# 管理者パネルで倍率を調整できるゲーム一覧(BetRecord.gameで使っているキーと対応)
GAME_KEYS = [
    ("dice", "Dice"), ("limbo", "Limbo"), ("crash", "Crash"), ("mines", "Mines"),
    ("plinko", "Plinko"), ("keno", "Keno"), ("wheel", "Wheel"), ("hilo", "HiLo"),
    ("tower", "Dragon Tower"), ("coinflip", "Coin Flip"), ("sicbo", "Sic Bo"), ("war", "War"),
    ("roulette", "Roulette(European)"), ("american_roulette", "American Roulette"),
    ("blackjack", "Blackjack"), ("baccarat", "Baccarat"), ("videopoker", "Video Poker"),
    ("reddog", "Red Dog"), ("andarbahar", "Andar Bahar"), ("craps", "Craps"),
    ("threecardpoker", "Three Card Poker"), ("slots", "スロット(全テーマ共通)"),
    ("rps", "Rock Paper Scissors"), ("scratch", "Scratch Card"), ("horserace", "Horse Race"),
    ("market", "Market"), ("fantan", "Fan Tan"), ("overunder7", "Over/Under 7"),
    ("pokerdice", "Poker Dice"), ("fishing", "Fishing Pond"), ("miniroulette", "Mini Roulette"),
    ("ceelo", "Cee-lo"), ("dragontiger", "Dragon Tiger"), ("lottery", "Lucky Numbers Lottery"),
    ("treasurehunt", "Treasure Hunt"), ("numbermatch", "Number Match"),
]

# 勝率補正(win_boost)に対応しているゲーム(二択・シンプルな勝敗判定のもののみ。他は今後拡張予定)
WIN_BOOST_GAMES = {
    "coinflip", "rps", "fantan", "ceelo", "numbermatch", "overunder7", "miniroulette", "dragontiger",
}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/admin")
@login_required
@admin_required
def dashboard():
    query = request.args.get("q", "").strip()
    users_query = User.query.order_by(User.created_at.desc())
    if query:
        users_query = users_query.filter(User.username.ilike(f"%{query}%"))
    users = users_query.limit(50).all()

    recent_tx = Transaction.query.order_by(Transaction.created_at.desc()).limit(30).all()
    codes = RedeemCode.query.order_by(RedeemCode.created_at.desc()).limit(20).all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(20).all()

    settings_rows = {row.game_key: row for row in GameSetting.query.all()}
    game_scalars = [
        (key, name, settings_rows[key].payout_scalar if key in settings_rows else 1.0,
         settings_rows[key].win_boost if key in settings_rows else 0.0, key in WIN_BOOST_GAMES)
        for key, name in GAME_KEYS
    ]

    giveaways = Giveaway.query.order_by(Giveaway.created_at.desc()).limit(20).all()
    events = Event.query.order_by(Event.created_at.desc()).limit(20).all()
    pending_tips = TipRequest.query.filter_by(status="pending").order_by(TipRequest.created_at.desc()).all()

    gacha_settings = GachaSetting.query.get("default")
    if not gacha_settings:
        gacha_settings = GachaSetting(key="default", cost_single=200, cost_ten=1800)
        db.session.add(gacha_settings)
        db.session.commit()

    import characters as ch
    character_choices = []
    for key, info in ch.all_characters_dict().items():
        character_choices.append((key, info[0], info[1]))  # (key, name, rarity)
    character_choices.sort(key=lambda c: (ch.RARITY_ORDER.index(c[2]), c[1]))

    from seasons import get_current_season
    current_season = get_current_season()

    active_polls = Poll.query.filter_by(is_active=True).order_by(Poll.created_at.desc()).all()
    active_tournaments = Tournament.query.filter_by(status="active").order_by(Tournament.created_at.desc()).all()

    from rhythm import DIFFICULTIES as rhythm_difficulties

    from towerdefense import get_enemy_tier, enemy_tier_multiplier, ENEMY_TIER_LABELS, get_reward_multiplier
    current_enemy_tier = get_enemy_tier()
    current_reward_multiplier = get_reward_multiplier()

    from config import Config

    return render_template(
        "admin.html", users=users, recent_tx=recent_tx, query=query, codes=codes, announcements=announcements,
        game_scalars=game_scalars, min_scalar=MIN_PAYOUT_SCALAR, max_scalar=MAX_PAYOUT_SCALAR,
        giveaways=giveaways, events=events, vip_tier_names=Config.VIP_TIER_NAMES, pending_tips=pending_tips,
        gacha_settings=gacha_settings, character_choices=character_choices, rarity_names=ch.RARITY_NAMES,
        rarity_order=ch.RARITY_ORDER,
        current_season=current_season, active_polls=active_polls,
        current_enemy_tier=current_enemy_tier, enemy_tier_multiplier=enemy_tier_multiplier,
        current_reward_multiplier=current_reward_multiplier, active_tournaments=active_tournaments,
        difficulties=rhythm_difficulties,
        enemy_tier_labels=ENEMY_TIER_LABELS
    )


@admin_bp.route("/admin/grant", methods=["POST"])
@login_required
@admin_required
def grant_points():
    username = request.form.get("username", "").strip()
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        amount = 0
    reason = request.form.get("reason", "").strip() or "管理者による付与"

    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    if amount == 0:
        flash("付与するポイント数を入力してください(マイナス値で減算も可能です)。", "error")
        return redirect(url_for("admin.dashboard"))

    user.balance = max(0, user.balance + amount)
    db.session.add(Transaction(
        user_id=user.id, amount=amount, kind="admin_grant",
        description=f"{reason}(実行者: {current_user.username})"
    ))
    if amount > 0:
        notify(user.id, f"運営より {amount:,} Embersが付与されました({reason})。")
    else:
        notify(user.id, f"運営により {abs(amount):,} Embersが回収されました({reason})。")
    db.session.commit()

    flash(f"{user.username} に {amount:,} Embersを付与しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/broadcast", methods=["POST"])
@login_required
@admin_required
def broadcast_points():
    """全プレイヤーに対して一括でポイントを付与/回収する"""
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        amount = 0
    reason = request.form.get("reason", "").strip() or "運営からの一斉配布"

    if amount == 0:
        flash("付与するポイント数を入力してください(マイナス値で一斉回収も可能です)。", "error")
        return redirect(url_for("admin.dashboard"))

    users = User.query.all()
    for u in users:
        u.balance = max(0, u.balance + amount)
        db.session.add(Transaction(
            user_id=u.id, amount=amount, kind="admin_broadcast",
            description=f"{reason}(実行者: {current_user.username})"
        ))

    if amount > 0:
        notify_all(f"運営より全プレイヤーに {amount:,} Embersが付与されました({reason})。")
    else:
        notify_all(f"運営により全プレイヤーから {abs(amount):,} Embersが回収されました({reason})。")
    db.session.commit()

    flash(f"全 {len(users)} 人に {amount:,} Embersを一括付与しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/set-debt", methods=["POST"])
@login_required
@admin_required
def set_debt():
    """
    指定したユーザーに借金を負わせる。
    現在の残高はすべて没収され(=「借金ポイント」化)、以降の勝利分は
    借金が完済されるまで残高に反映されなくなる。
    """
    username = request.form.get("username", "").strip()
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        amount = 0
    reason = request.form.get("reason", "").strip() or "管理者による設定"

    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))
    if amount <= 0:
        flash("借金額は1以上を指定してください。", "error")
        return redirect(url_for("admin.dashboard"))

    user.debt = (user.debt or 0) + amount
    if not user.debt_started_at:
        from models import utcnow
        user.debt_started_at = utcnow()
    user.balance = 0  # 現在の残高はすべて借金ポイントとして没収される

    db.session.add(Transaction(
        user_id=user.id, amount=0, kind="debt_set",
        description=f"借金 {amount:,} を設定({reason} / 実行者: {current_user.username})"
    ))
    notify(
        user.id,
        f"{amount:,} Embersの借金が設定されました。残高はいったん0になり、"
        f"以降の勝利分は借金を完済するまで残高に反映されません({reason})。"
    )
    db.session.commit()

    flash(f"{user.username} に借金 {amount:,} を設定しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/clear-debt", methods=["POST"])
@login_required
@admin_required
def clear_debt():
    username = request.form.get("username", "").strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    user.debt = 0
    user.debt_started_at = None
    notify(user.id, "運営により借金が免除されました。")
    db.session.commit()

    flash(f"{user.username} の借金を免除しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/toggle-admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin():
    username = request.form.get("username", "").strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    if user.id == current_user.id:
        flash("自分自身の管理者権限は変更できません。", "error")
        return redirect(url_for("admin.dashboard"))

    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f"{user.username} の管理者権限を{'付与' if user.is_admin else '解除'}しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/toggle-blacklist", methods=["POST"])
@login_required
@admin_required
def toggle_blacklist():
    username = request.form.get("username", "").strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    if user.id == current_user.id:
        flash("自分自身をブラックリストに登録することはできません。", "error")
        return redirect(url_for("admin.dashboard"))

    user.is_blacklisted = not user.is_blacklisted
    db.session.commit()

    if user.is_blacklisted:
        flash(f"{user.username} をブラックリストに登録しました。以降、何をしても残高が増えなくなります。", "success")
    else:
        flash(f"{user.username} のブラックリスト登録を解除しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/set-vip", methods=["POST"])
@login_required
@admin_required
def set_vip():
    username = request.form.get("username", "").strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    try:
        tier = int(request.form.get("vip_tier", "0"))
    except ValueError:
        tier = 0

    if tier <= 0:
        user.is_vip = False
        user.vip_tier = 1
        db.session.commit()
        notify(user.id, "VIP権限が解除されました。")
        db.session.commit()
        flash(f"{user.username} のVIPを解除しました。", "success")
        return redirect(url_for("admin.dashboard"))

    tier = min(4, max(1, tier))
    user.is_vip = True
    user.vip_tier = tier
    db.session.commit()

    from config import Config
    tier_name = Config.VIP_TIER_NAMES.get(tier, "Bronze")
    notify(user.id, f"{tier_name} VIPに認定されました。VIPラウンジ(/vip-lounge)と各種特典が利用できるようになりました。")
    try:
        from achievements import check_achievements
        check_achievements(user)
    except Exception:
        pass
    db.session.commit()

    flash(f"{user.username} を {tier_name} VIP に設定しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/create-code", methods=["POST"])
@login_required
@admin_required
def create_code():
    code_text = request.form.get("code", "").strip() or secrets.token_hex(4).upper()
    code_type = request.form.get("code_type", "once_per_user")
    try:
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        amount = 0
    try:
        max_global_uses = int(request.form.get("max_global_uses", "0")) or None
    except ValueError:
        max_global_uses = None

    if amount <= 0:
        flash("コードで付与するポイント数を1以上で指定してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if code_type not in ("once_per_user", "global_limit"):
        flash("コード種別が不正です。", "error")
        return redirect(url_for("admin.dashboard"))
    if code_type == "global_limit" and not max_global_uses:
        flash("「全体で何回」タイプの場合は、利用回数の上限を指定してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if RedeemCode.query.filter_by(code=code_text).first():
        flash("同じコードがすでに存在します。", "error")
        return redirect(url_for("admin.dashboard"))

    rc = RedeemCode(
        code=code_text, amount=amount, code_type=code_type,
        max_global_uses=max_global_uses, created_by=current_user.username
    )
    db.session.add(rc)

    if code_type == "once_per_user":
        notify_all(f"新しいコードが発行されました:「{code_text}」(1人1回まで、{amount:,} Embers) /redeem ページで入力してください。")
    else:
        notify_all(f"新しいコードが発行されました:「{code_text}」(全体で{max_global_uses}回まで、{amount:,} Embers) /redeem ページで入力してください。")

    db.session.commit()
    flash(f"コード「{code_text}」を発行しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/deactivate-code", methods=["POST"])
@login_required
@admin_required
def deactivate_code():
    code_id = request.form.get("code_id")
    rc = RedeemCode.query.get(code_id)
    if rc:
        rc.active = False
        db.session.commit()
        flash(f"コード「{rc.code}」を無効化しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/post-announcement", methods=["POST"])
@login_required
@admin_required
def post_announcement():
    message = request.form.get("message", "").strip()
    if not message:
        flash("メッセージを入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    db.session.add(Announcement(message=message, created_by=current_user.username))
    notify_all(f"新しいお知らせが掲示されました:「{message[:50]}」")
    db.session.commit()

    flash("お知らせを掲示しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/delete-announcement", methods=["POST"])
@login_required
@admin_required
def delete_announcement():
    announcement_id = request.form.get("announcement_id")
    ann = Announcement.query.get(announcement_id)
    if ann:
        db.session.delete(ann)
        db.session.commit()
        flash("お知らせを削除しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/tips/<int:tip_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_tip(tip_id):
    tip = TipRequest.query.get(tip_id)
    if not tip or tip.status != "pending":
        flash("対象のチップ申請が見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    from models import utcnow

    if tip.from_user.balance < tip.amount:
        tip.status = "rejected"
        tip.resolved_at = utcnow()
        db.session.commit()
        notify(tip.from_user_id, f"{tip.to_user.username} さんへのチップ申請は、残高不足のため自動的に却下されました。")
        db.session.commit()
        flash("送信者の残高が不足していたため、自動的に却下しました。", "error")
        return redirect(url_for("admin.dashboard"))

    tip.from_user.balance -= tip.amount
    tip.to_user.balance += tip.amount
    tip.status = "approved"
    tip.resolved_at = utcnow()

    db.session.add(Transaction(
        user_id=tip.from_user_id, amount=-tip.amount, kind="tip_sent", description=f"{tip.to_user.username} にチップ"
    ))
    db.session.add(Transaction(
        user_id=tip.to_user_id, amount=tip.amount, kind="tip_received", description=f"{tip.from_user.username} からチップ"
    ))
    db.session.commit()

    notify(tip.to_user_id, f"{tip.from_user.username} さんから {tip.amount:,} Embersのチップが届きました。")
    notify(tip.from_user_id, f"{tip.to_user.username} さんへのチップ({tip.amount:,} Embers)が承認されました。")
    db.session.commit()

    flash("チップを承認し、送金しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/tips/<int:tip_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_tip(tip_id):
    tip = TipRequest.query.get(tip_id)
    if not tip or tip.status != "pending":
        flash("対象のチップ申請が見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    from models import utcnow
    tip.status = "rejected"
    tip.resolved_at = utcnow()
    db.session.commit()

    notify(tip.from_user_id, f"{tip.to_user.username} さんへのチップ申請({tip.amount:,} Embers)は却下されました。")
    db.session.commit()

    flash("チップ申請を却下しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/season/set-rarities", methods=["POST"])
@login_required
@admin_required
def season_set_rarities():
    import characters as ch
    from seasons import get_current_season

    endless_rarity = request.form.get("endless_reward_rarity", "epic")
    pass_rarity = request.form.get("pass_reward_rarity", "epic")
    valid_rarities = [r for r in ch.RARITY_NAMES if r != "ultimate"]  # えびを含むultimateは対象外にする(安全のため一括除外)
    if endless_rarity not in valid_rarities or pass_rarity not in valid_rarities:
        flash("えび(アルティメット)をシーズン報酬に設定することはできません。", "error")
        return redirect(url_for("admin.dashboard"))

    season = get_current_season()
    season.endless_reward_rarity = endless_rarity
    season.pass_reward_rarity = pass_rarity
    db.session.commit()
    flash("シーズン報酬のレアリティを更新しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/season/end", methods=["POST"])
@login_required
@admin_required
def season_end():
    import random
    import characters as ch
    from seasons import get_current_season

    season = get_current_season()

    top_score = (
        EndlessScore.query.filter_by(season_id=season.id).order_by(EndlessScore.score.desc()).first()
    )

    if top_score:
        winner = User.query.get(top_score.user_id)
        candidates = [k for k in ch.all_keys_by_rarity(season.endless_reward_rarity) if k != "ebi"]
        if candidates:
            key = random.choice(candidates)
            row = UserCharacter.query.filter_by(user_id=winner.id, character_key=key).first()
            if row:
                row.count += 1
            else:
                db.session.add(UserCharacter(user_id=winner.id, character_key=key, count=1))
            info = ch.character_info(key)

            from notifications import notify
            notify(winner.id, f"🏆 シーズン{season.number}のエンドレスランキング1位おめでとうございます!「{info['name']}」を獲得しました。")

            season.winner_user_id = winner.id
            season.winner_character_key = key
            flash(f"シーズン{season.number}終了。1位の{winner.username}に「{info['name']}」を贈りました。", "success")
        else:
            flash("報酬レアリティに該当するキャラクターが見つかりませんでした。", "error")
    else:
        flash(f"シーズン{season.number}終了。エンドレスモードの記録がなかったため、今回は受賞者なしです。", "success")

    season.status = "finished"
    from models import utcnow
    season.ended_at = utcnow()

    new_season = Season(
        number=season.number + 1, endless_reward_rarity=season.endless_reward_rarity,
        pass_reward_rarity=season.pass_reward_rarity
    )
    db.session.add(new_season)
    db.session.commit()

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/generate-character", methods=["POST"])
@login_required
@admin_required
def generate_character():
    import random
    import characters as ch

    rarity = request.form.get("rarity", "common")
    if rarity not in ch.RARITY_NAMES:
        flash("レアリティの指定が不正です。", "error")
        return redirect(url_for("admin.dashboard"))

    STAT_RANGES = {
        "common":       {"atk": (8, 16), "def": (5, 10), "range": (1, 2), "speed": (0.6, 1.6), "cost": (16, 26)},
        "uncommon":     {"atk": (12, 20), "def": (8, 14), "range": (1, 2), "speed": (0.6, 1.5), "cost": (18, 28)},
        "rare":         {"atk": (16, 26), "def": (10, 20), "range": (1, 3), "speed": (0.7, 1.4), "cost": (38, 48)},
        "super_rare":   {"atk": (20, 32), "def": (14, 22), "range": (1, 3), "speed": (0.7, 1.4), "cost": (40, 52)},
        "epic":         {"atk": (26, 40), "def": (18, 32), "range": (2, 3), "speed": (0.8, 1.5), "cost": (68, 82)},
        "elite":        {"atk": (32, 48), "def": (22, 34), "range": (2, 3), "speed": (0.8, 1.5), "cost": (72, 88)},
        "heroic":       {"atk": (38, 56), "def": (26, 40), "range": (2, 3), "speed": (0.8, 1.4), "cost": (95, 115)},
        "mythic":       {"atk": (44, 64), "def": (30, 46), "range": (3, 4), "speed": (0.8, 1.4), "cost": (120, 145)},
        "legendary":    {"atk": (50, 72), "def": (32, 48), "range": (3, 4), "speed": (0.9, 1.5), "cost": (125, 150)},
        "ancient":      {"atk": (56, 80), "def": (38, 56), "range": (3, 4), "speed": (0.9, 1.5), "cost": (150, 175)},
        "divine":       {"atk": (62, 88), "def": (42, 62), "range": (3, 4), "speed": (0.8, 1.4), "cost": (180, 210)},
        "celestial":    {"atk": (68, 96), "def": (46, 68), "range": (3, 5), "speed": (0.8, 1.3), "cost": (215, 245)},
        "astral":       {"atk": (74, 104), "def": (50, 74), "range": (3, 5), "speed": (0.7, 1.3), "cost": (250, 285)},
        "ethereal":     {"atk": (80, 112), "def": (54, 80), "range": (4, 5), "speed": (0.7, 1.2), "cost": (290, 325)},
        "transcendent": {"atk": (86, 120), "def": (58, 86), "range": (4, 5), "speed": (0.7, 1.2), "cost": (330, 365)},
        "cosmic":       {"atk": (92, 128), "def": (62, 92), "range": (4, 5), "speed": (0.6, 1.1), "cost": (370, 410)},
        "primordial":   {"atk": (98, 136), "def": (66, 98), "range": (4, 6), "speed": (0.6, 1.1), "cost": (420, 460)},
        "absolute":     {"atk": (104, 144), "def": (70, 104), "range": (4, 6), "speed": (0.6, 1.0), "cost": (470, 510)},
        "supreme":      {"atk": (110, 152), "def": (74, 110), "range": (5, 6), "speed": (0.5, 1.0), "cost": (520, 570)},
        "ultimate":     {"atk": (160, 195), "def": (110, 150), "range": (4, 6), "speed": (0.6, 0.85), "cost": (220, 260)},
    }
    PREFIXES = [
        "紅蓮の", "蒼き", "翠玉の", "漆黒の", "黄金の", "銀白の", "深緑の", "灼熱の", "氷結の", "疾風の",
        "聖なる", "呪われし", "古の", "幼き", "猛き", "気高き", "闇纏う", "光帯びる", "嵐呼ぶ", "大地の",
        "深淵の", "天空の", "煌めく", "朽ちた", "不滅の", "血染めの", "月影の", "陽炎の", "雷鳴の", "白銀の",
        "夜叉の", "朧げな", "獄炎の", "凍てつく", "常闇の", "薄明の", "剛力の", "俊足の", "堅牢な", "狡猾な",
    ]
    SPECIES = [
        ("ドラゴン", "🐉"), ("ウルフ", "🐺"), ("フェニックス", "🦅"), ("ゴーレム", "🗿"), ("ウィッチ", "🧙"),
        ("ナイト", "🛡️"), ("デーモン", "👹"), ("エンジェル", "😇"), ("グリフォン", "🦁"), ("ユニコーン", "🦄"),
        ("リッチ", "💀"), ("パラディン", "⚔️"), ("アサシン", "🗡️"), ("レンジャー", "🏹"), ("シャーマン", "🪄"),
        ("ヴァンパイア", "🧛"), ("ミノタウロス", "🐂"), ("ハーピー", "🦉"), ("ペガサス", "🐴"), ("キマイラ", "🐐"),
        ("スフィンクス", "🐈"), ("ケルベロス", "🐕"), ("トロール", "🧌"), ("バジリスク", "🦎"), ("ジャイアント", "🧌"),
    ]
    ELEMENTS = list(ch.ELEMENT_NAMES.keys())
    ABILITY_KEYS = list(ch.ABILITIES.keys())
    DESCRIPTIONS = [
        "その名を聞いた者は恐れおののく。", "戦場に舞い降りる度、勝利を約束する。", "静かなる強さを秘めた戦士。",
        "一撃に全てを込める破壊者。", "仲間を守るため、盾となる者。", "古より伝わる力を宿す。",
        "管理者の手によって生み出された、新たな戦力。",
    ]

    rng = STAT_RANGES[rarity]
    prefix = random.choice(PREFIXES)
    species, icon = random.choice(SPECIES)
    name = prefix + species

    attack = round(random.uniform(*rng["atk"]), 1)
    defense = round(random.uniform(*rng["def"]), 1)
    range_ = random.randint(*rng["range"])
    speed = round(random.uniform(*rng["speed"]), 2)
    cost = random.randint(*rng["cost"])
    element = random.choice(ELEMENTS)
    description = random.choice(DESCRIPTIONS)

    # レアリティが上がるほど、アビリティ(特殊能力)の数も多くなる
    rarity_idx = ch.RARITY_ORDER.index(rarity)
    if rarity_idx <= 1:
        ability_count = 0
    elif rarity_idx <= 3:
        ability_count = 1
    elif rarity_idx <= 8:
        ability_count = 2
    elif rarity_idx <= 14:
        ability_count = 3
    else:
        ability_count = 4
    abilities = random.sample(ABILITY_KEYS, min(ability_count, len(ABILITY_KEYS))) if ability_count > 0 else []
    splash = 1 if ("aoe" in abilities or "splash" in abilities) else 0

    key = f"custom_{uuid.uuid4().hex[:12]}"
    db.session.add(CustomCharacter(
        key=key, name=name, rarity=rarity, element=element, icon=icon, attack=attack, defense=defense,
        range=range_, speed=speed, cost=cost, splash=splash, abilities_json=json.dumps(abilities),
        description=description, created_by=current_user.username,
    ))
    db.session.commit()

    flash(
        f"新キャラクター「{name}」({ch.RARITY_NAMES[rarity]})を生成しました。"
        f"攻撃力{attack} / 防御力{defense} / アビリティ: {', '.join(ch.ABILITIES[a]['label'] for a in abilities) or 'なし'}",
        "success"
    )
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/polls/create", methods=["POST"])
@login_required
@admin_required
def poll_create():
    question = request.form.get("question", "").strip()
    raw_options = request.form.get("options", "")
    options = [o.strip() for o in raw_options.split("\n") if o.strip()]
    try:
        reward = int(request.form.get("reward", "0"))
    except ValueError:
        reward = 0

    if not question or len(options) < 2:
        flash("質問と、2つ以上の選択肢(改行区切り)を入力してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if len(options) > 8:
        flash("選択肢は最大8個までです。", "error")
        return redirect(url_for("admin.dashboard"))

    db.session.add(Poll(
        question=question, options_json=json.dumps(options), reward=max(0, reward),
        created_by=current_user.username
    ))
    db.session.commit()

    try:
        notify_all(f"📊 新しいアンケート「{question}」が始まりました。ぜひ投票してください。")
        db.session.commit()
    except Exception:
        pass

    flash("アンケートを作成しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/polls/<int:poll_id>/close", methods=["POST"])
@login_required
@admin_required
def poll_close(poll_id):
    poll = Poll.query.get(poll_id)
    if poll:
        poll.is_active = False
        db.session.commit()
        flash("アンケートを終了しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/character-stats/<key>")
@login_required
@admin_required
def character_stats(key):
    """AJAX用: 指定キャラクターの現在の攻撃力・防御力・コストを返す(編集フォームの自動入力に使う)"""
    import characters as ch
    info = ch.character_info(key)
    if not info:
        return jsonify({"error": "キャラクターが見つかりません。"}), 404
    return jsonify({
        "name": info["name"], "icon": info["icon"], "attack": info["attack"],
        "defense": info["defense"], "cost": info["cost"], "rarity_label": info["rarity_label"],
    })


@admin_bp.route("/admin/edit-character", methods=["POST"])
@login_required
@admin_required
def edit_character():
    import characters as ch

    key = request.form.get("character_key", "").strip()
    info = ch.character_info(key)
    if not info:
        flash("指定されたキャラクターが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    def parse_optional_number(field_name, cast):
        raw = request.form.get(field_name, "").strip()
        if raw == "":
            return None
        try:
            return cast(raw)
        except ValueError:
            return None

    attack = parse_optional_number("attack", float)
    defense = parse_optional_number("defense", float)
    cost = parse_optional_number("cost", int)

    if attack is None and defense is None and cost is None:
        flash("変更する項目(攻撃力・防御力・必要なお金のいずれか)を入力してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if (attack is not None and attack < 0) or (defense is not None and defense < 0) or (cost is not None and cost < 0):
        flash("マイナスの値は設定できません。", "error")
        return redirect(url_for("admin.dashboard"))

    if key in ch.CHARACTERS:
        # 静的カタログのキャラクター(えびなど)は、上書き専用テーブルに調整値を保存する
        row = CharacterOverride.query.get(key)
        if not row:
            row = CharacterOverride(key=key)
            db.session.add(row)
        if attack is not None:
            row.attack = attack
        if defense is not None:
            row.defense = defense
        if cost is not None:
            row.cost = cost
        row.updated_by = current_user.username
    else:
        # 管理者作成キャラクターは、CustomCharacterの行を直接更新する
        row = CustomCharacter.query.get(key)
        if not row:
            flash("指定されたキャラクターが見つかりません。", "error")
            return redirect(url_for("admin.dashboard"))
        if attack is not None:
            row.attack = attack
        if defense is not None:
            row.defense = defense
        if cost is not None:
            row.cost = cost

    db.session.commit()
    flash(f"「{info['name']}」のステータスを更新しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/grant-character", methods=["POST"])
@login_required
@admin_required
def grant_character():
    import characters as ch

    username = request.form.get("username", "").strip()
    character_key = request.form.get("character_key", "").strip()
    try:
        count = int(request.form.get("count", "1"))
    except ValueError:
        count = 1
    count = max(1, min(999, count))

    user = User.query.filter_by(username=username).first()
    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    if character_key not in ch.all_characters_dict():
        flash("指定されたキャラクターが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    row = UserCharacter.query.filter_by(user_id=user.id, character_key=character_key).first()
    if row:
        row.count += count
    else:
        row = UserCharacter(user_id=user.id, character_key=character_key, count=count)
        db.session.add(row)
    db.session.commit()

    info = ch.character_info(character_key)
    notify(user.id, f"管理者から「{info['name']}」を{count}体受け取りました。")
    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(user)
    except Exception:
        pass

    flash(f"{user.username} に「{info['name']}」を{count}体付与しました(所持数: {row.count})。", "success")
    return redirect(url_for("admin.dashboard"))


def _extract_youtube_id(text):
    """YouTubeのURL(様々な形式)、または動画IDそのものから、動画IDだけを取り出す"""
    text = text.strip()
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtube\.com/live/|youtube\.com/shorts/|youtube\.com/embed/|youtu\.be/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    # URLではなく、動画IDそのものが入力された場合(11文字の英数字・-・_)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    return None


@admin_bp.route("/admin/rhythm/add-song", methods=["POST"])
@login_required
@admin_required
def rhythm_add_song():
    title = request.form.get("title", "").strip()
    youtube_input = request.form.get("youtube_id", "").strip()
    try:
        duration = int(request.form.get("duration_seconds", "90"))
        bpm = int(request.form.get("bpm", "120"))
        offset_seconds = float(request.form.get("offset_seconds", "0") or "0")
    except ValueError:
        flash("再生時間・BPM・拍の開始位置は数値で入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    def parse_optional_seconds(field_name):
        raw = request.form.get(field_name, "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    verse1_end = parse_optional_seconds("verse1_end_seconds")
    verse2_end = parse_optional_seconds("verse2_end_seconds")
    difficulties = request.form.getlist("difficulties")
    valid_difficulties = [d for d in difficulties if d in ("easy", "normal", "hard", "oni")]
    if not valid_difficulties:
        valid_difficulties = ["easy", "normal", "hard", "oni"]

    if not title or not youtube_input:
        flash("曲名とYouTubeのURL(または動画ID)を入力してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if bpm <= 0 or duration <= 0:
        flash("BPM・再生時間は1以上で指定してください。", "error")
        return redirect(url_for("admin.dashboard"))

    youtube_id = _extract_youtube_id(youtube_input)
    if not youtube_id:
        flash("YouTubeのURLから動画IDを読み取れませんでした。URLをそのまま貼り付けてみてください。", "error")
        return redirect(url_for("admin.dashboard"))

    db.session.add(RhythmSong(
        title=title, youtube_id=youtube_id, duration_seconds=duration, bpm=bpm, offset_seconds=max(0.0, offset_seconds),
        verse1_end_seconds=verse1_end, verse2_end_seconds=verse2_end,
        available_difficulties_json=json.dumps(valid_difficulties),
    ))
    db.session.commit()
    flash(f"楽曲「{title}」を追加しました。(動画ID: {youtube_id})", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/tournament/create", methods=["POST"])
@login_required
@admin_required
def tournament_create():
    name = request.form.get("name", "").strip()
    game_key = request.form.get("game_key", "").strip()
    prize_character_key = request.form.get("prize_character_key", "").strip() or None
    try:
        prize_amount = int(request.form.get("prize_amount", "0"))
    except ValueError:
        prize_amount = 0

    if not name or not game_key:
        flash("大会名と対象ゲームを入力してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if prize_amount < 0:
        flash("優勝賞品(Embers)は0以上で指定してください。", "error")
        return redirect(url_for("admin.dashboard"))

    db.session.add(Tournament(
        name=name, game_key=game_key, prize_amount=prize_amount,
        prize_character_key=prize_character_key, created_by=current_user.username,
    ))
    db.session.commit()

    try:
        notify_all(f"🏆 新しい大会「{name}」が始まりました!対象ゲーム: {game_key}")
        db.session.commit()
    except Exception:
        pass

    flash("大会を開催しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/tournament/<int:tournament_id>/end", methods=["POST"])
@login_required
@admin_required
def tournament_end(tournament_id):
    from tournament import compute_scores
    t = Tournament.query.get(tournament_id)
    if not t or t.status != "active":
        flash("この大会はすでに終了しています。", "error")
        return redirect(url_for("admin.dashboard"))

    scores = compute_scores(t)
    if scores:
        winner_id = max(scores, key=scores.get)
        winner = User.query.get(winner_id)
        t.winner_id = winner_id

        if t.prize_amount > 0:
            from games.common import credit_reward
            credit_reward(winner, t.prize_amount)
            db.session.add(Transaction(
                user_id=winner_id, amount=t.prize_amount, kind="tournament_prize",
                description=f"大会優勝賞品: {t.name}"
            ))
        if t.prize_character_key:
            existing = UserCharacter.query.filter_by(user_id=winner_id, character_key=t.prize_character_key).first()
            if existing:
                existing.count += 1
            else:
                db.session.add(UserCharacter(user_id=winner_id, character_key=t.prize_character_key, count=1))

        try:
            from notifications import notify
            notify(winner_id, f"🏆 「{t.name}」で優勝しました!賞品を獲得しました。")
        except Exception:
            pass
        flash(f"大会を終了し、{winner.username} に賞品を付与しました。", "success")
    else:
        flash("大会を終了しました(参加者がいなかったため賞品は付与されていません)。", "success")

    t.status = "finished"
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/set-enemy-tier", methods=["POST"])
@login_required
@admin_required
def set_enemy_tier():
    try:
        tier = int(request.form.get("enemy_tier", "1"))
        reward_mult = float(request.form.get("reward_multiplier", "1.0"))
    except ValueError:
        flash("数値の指定が不正です。", "error")
        return redirect(url_for("admin.dashboard"))

    if not (1 <= tier <= 10):
        flash("強さの段階は1〜10の範囲で指定してください。", "error")
        return redirect(url_for("admin.dashboard"))
    if reward_mult < 0:
        flash("報酬倍率は0以上で指定してください。", "error")
        return redirect(url_for("admin.dashboard"))

    row = TDDifficultySetting.query.get("default")
    if not row:
        row = TDDifficultySetting(key="default")
        db.session.add(row)
    row.enemy_tier = tier
    row.reward_multiplier = reward_mult
    db.session.commit()

    from towerdefense import enemy_tier_multiplier
    mult = enemy_tier_multiplier(tier)
    flash(f"敵の強さを段階{tier}(約{mult}倍)、勝利報酬を{reward_mult}倍に設定しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/set-gacha-cost", methods=["POST"])
@login_required
@admin_required
def set_gacha_cost():
    try:
        cost_single = int(request.form.get("cost_single", "200"))
        cost_ten = int(request.form.get("cost_ten", "1800"))
    except ValueError:
        flash("必要ポイントは数値で入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    if cost_single <= 0 or cost_ten <= 0:
        flash("必要ポイントは1以上にしてください。", "error")
        return redirect(url_for("admin.dashboard"))

    row = GachaSetting.query.get("default")
    if not row:
        row = GachaSetting(key="default")
        db.session.add(row)
    row.cost_single = cost_single
    row.cost_ten = cost_ten
    db.session.commit()

    flash(f"ガチャの必要ポイントを 1回={cost_single:,} / 10連={cost_ten:,} に設定しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/set-game-scalar", methods=["POST"])
@login_required
@admin_required
def set_game_scalar():
    game_key = request.form.get("game_key", "").strip()
    valid_keys = {key for key, _ in GAME_KEYS}
    if game_key not in valid_keys:
        flash("指定されたゲームが見つかりません。", "error")
        return redirect(url_for("admin.dashboard"))

    try:
        scalar = float(request.form.get("payout_scalar", "1.0"))
    except ValueError:
        flash("倍率は数値で入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    try:
        boost = float(request.form.get("win_boost", "0.0"))
    except ValueError:
        boost = 0.0
    boost = max(-1.0, min(1.0, boost))  # ±1.0で「常に勝ち/常に負け」になるため、これが数学的な上限・下限

    scalar = max(MIN_PAYOUT_SCALAR, min(MAX_PAYOUT_SCALAR, scalar))

    row = GameSetting.query.get(game_key)
    if row:
        row.payout_scalar = scalar
        row.win_boost = boost
    else:
        db.session.add(GameSetting(game_key=game_key, payout_scalar=scalar, win_boost=boost))
    db.session.commit()

    flash(f"{game_key} の配当倍率を {scalar}x、勝率補正を {boost:+.2f} に設定しました。", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/reset-game-scalar", methods=["POST"])
@login_required
@admin_required
def reset_game_scalar():
    game_key = request.form.get("game_key", "").strip()
    row = GameSetting.query.get(game_key)
    if row:
        db.session.delete(row)
        db.session.commit()
        flash(f"{game_key} の配当倍率を通常(1.0x)に戻しました。", "success")
    return redirect(url_for("admin.dashboard"))
