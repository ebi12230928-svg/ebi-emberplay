import secrets
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from extensions import db
from models import User, Transaction, RedeemCode
from notifications import notify, notify_all

admin_bp = Blueprint("admin", __name__)


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
    return render_template("admin.html", users=users, recent_tx=recent_tx, query=query, codes=codes)


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
