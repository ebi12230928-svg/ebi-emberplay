from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from extensions import db
from models import SportsEvent, VipAnnouncement

vip_bp = Blueprint("vip", __name__)


def vip_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_vip and not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@vip_bp.route("/vip-lounge")
@login_required
@vip_required
def lounge():
    from sportsbook import sync_events

    sync_events()
    upcoming = (
        SportsEvent.query.filter_by(status="upcoming")
        .order_by(SportsEvent.event_time.asc())
        .limit(15).all()
    )
    finished = (
        SportsEvent.query.filter_by(status="finished")
        .order_by(SportsEvent.event_time.desc())
        .limit(10).all()
    )
    announcements = (
        VipAnnouncement.query.order_by(VipAnnouncement.created_at.desc()).limit(20).all()
    )
    return render_template("vip_lounge.html", upcoming=upcoming, finished=finished, announcements=announcements)


@vip_bp.route("/vip-lounge/announce", methods=["POST"])
@login_required
def post_announcement():
    if not current_user.is_admin:
        abort(403)

    message = request.form.get("message", "").strip()
    if not message:
        flash("メッセージを入力してください。", "error")
        return redirect(url_for("vip.lounge"))

    db.session.add(VipAnnouncement(message=message, created_by=current_user.username))
    db.session.commit()

    from notifications import notify_vips
    notify_vips(f"VIPラウンジに新しいお知らせが届きました:「{message[:50]}」")
    db.session.commit()

    flash("お知らせを投稿しました。", "success")
    return redirect(url_for("vip.lounge"))


@vip_bp.route("/vip-lounge/announce/delete", methods=["POST"])
@login_required
def delete_announcement():
    if not current_user.is_admin:
        abort(403)

    announcement_id = request.form.get("announcement_id")
    ann = VipAnnouncement.query.get(announcement_id)
    if ann:
        db.session.delete(ann)
        db.session.commit()
        flash("お知らせを削除しました。", "success")
    return redirect(url_for("vip.lounge"))
