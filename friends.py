from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from extensions import db
from models import Friendship, User
from notifications import notify

friends_bp = Blueprint("friends", __name__)


def _friendship_between(user_id_a, user_id_b):
    return Friendship.query.filter(
        or_(
            and_(Friendship.requester_id == user_id_a, Friendship.addressee_id == user_id_b),
            and_(Friendship.requester_id == user_id_b, Friendship.addressee_id == user_id_a),
        )
    ).first()


@friends_bp.route("/friends")
@login_required
def index():
    accepted = Friendship.query.filter(
        Friendship.status == "accepted",
        or_(Friendship.requester_id == current_user.id, Friendship.addressee_id == current_user.id),
    ).all()
    friend_list = []
    for f in accepted:
        other = f.addressee if f.requester_id == current_user.id else f.requester
        friend_list.append(other)

    incoming = Friendship.query.filter_by(addressee_id=current_user.id, status="pending").all()
    outgoing = Friendship.query.filter_by(requester_id=current_user.id, status="pending").all()

    return render_template(
        "friends.html", friends=friend_list, incoming=incoming, outgoing=outgoing
    )


@friends_bp.route("/friends/request", methods=["POST"])
@login_required
def send_request():
    username = request.form.get("username", "").strip()
    target = User.query.filter_by(username=username).first()

    if not target:
        flash("そのユーザーは見つかりません。", "error")
        return redirect(url_for("friends.index"))
    if target.id == current_user.id:
        flash("自分自身にはフレンド申請できません。", "error")
        return redirect(url_for("friends.index"))

    existing = _friendship_between(current_user.id, target.id)
    if existing:
        flash("すでに申請済み、またはフレンドです。", "error")
        return redirect(url_for("friends.index"))

    db.session.add(Friendship(requester_id=current_user.id, addressee_id=target.id))
    db.session.commit()

    notify(target.id, f"{current_user.username} さんからフレンド申請が届いています。")
    db.session.commit()

    flash(f"{target.username} さんにフレンド申請を送りました。", "success")
    return redirect(url_for("friends.index"))


@friends_bp.route("/friends/<int:friendship_id>/accept", methods=["POST"])
@login_required
def accept(friendship_id):
    f = Friendship.query.get(friendship_id)
    if not f or f.addressee_id != current_user.id or f.status != "pending":
        flash("対象の申請が見つかりません。", "error")
        return redirect(url_for("friends.index"))

    f.status = "accepted"
    db.session.commit()

    notify(f.requester_id, f"{current_user.username} さんとフレンドになりました。")
    db.session.commit()

    flash("フレンドになりました。", "success")
    return redirect(url_for("friends.index"))


@friends_bp.route("/friends/<int:friendship_id>/decline", methods=["POST"])
@login_required
def decline(friendship_id):
    f = Friendship.query.get(friendship_id)
    if f and (f.addressee_id == current_user.id or f.requester_id == current_user.id):
        db.session.delete(f)
        db.session.commit()
        flash("処理しました。", "success")
    return redirect(url_for("friends.index"))
