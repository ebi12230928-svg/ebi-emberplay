import secrets
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from extensions import db
from models import User, Transaction, RedeemCode, Announcement, GameSetting, Giveaway, Event, TipRequest
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
]


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

    settings_map = {row.game_key: row.payout_scalar for row in GameSetting.query.all()}
    game_scalars = [(key, name, settings_map.get(key, 1.0)) for key, name in GAME_KEYS]

    giveaways = Giveaway.query.order_by(Giveaway.created_at.desc()).limit(20).all()
    events = Event.query.order_by(Event.created_at.desc()).limit(20).all()
    pending_tips = TipRequest.query.filter_by(status="pending").order_by(TipRequest.created_at.desc()).all()

    from config import Config

    return render_template(
        "admin.html", users=users, recent_tx=recent_tx, query=query, codes=codes, announcements=announcements,
        game_scalars=game_scalars, min_scalar=MIN_PAYOUT_SCALAR, max_scalar=MAX_PAYOUT_SCALAR,
        giveaways=giveaways, events=events, vip_tier_names=Config.VIP_TIER_NAMES, pending_tips=pending_tips
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

    scalar = max(MIN_PAYOUT_SCALAR, min(MAX_PAYOUT_SCALAR, scalar))

    row = GameSetting.query.get(game_key)
    if row:
        row.payout_scalar = scalar
    else:
        db.session.add(GameSetting(game_key=game_key, payout_scalar=scalar))
    db.session.commit()

    flash(f"{game_key} の配当倍率スケールを {scalar}x に設定しました。", "success")
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
