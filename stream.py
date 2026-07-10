"""
画面配信(WebRTC)機能。
サーバー側は接続情報(SDP/ICE)のポーリング中継だけを行い、
実際の映像はブラウザ同士が直接つながるP2P通信で送られる(サーバーには映像データは一切通らない)。
音声は使わず、画面映像のみ。
"""
import json
from datetime import timedelta

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import StreamSession, StreamViewer, StreamSignal, utcnow

stream_bp = Blueprint("stream", __name__)

VIEWER_TIMEOUT_SECONDS = 20  # この秒数、視聴者からの反応がなければ離脱したとみなす


def _active_session():
    return StreamSession.query.filter_by(is_active=True).first()


@stream_bp.route("/stream")
@login_required
def index():
    session_obj = _active_session()
    is_broadcaster = bool(session_obj and session_obj.broadcaster_id == current_user.id)

    viewer_count = 0
    if session_obj:
        cutoff = utcnow() - timedelta(seconds=VIEWER_TIMEOUT_SECONDS)
        viewer_count = StreamViewer.query.filter(
            StreamViewer.session_id == session_obj.id, StreamViewer.last_seen >= cutoff
        ).count()

    return render_template(
        "stream.html", session=session_obj, is_broadcaster=is_broadcaster, viewer_count=viewer_count
    )


@stream_bp.route("/stream/start", methods=["POST"])
@login_required
def start():
    existing = _active_session()
    if existing and existing.broadcaster_id != current_user.id:
        flash("すでに他の人が配信中です。終了してからもう一度お試しください。", "error")
        return redirect(url_for("stream.index"))

    if not existing:
        title = request.form.get("title", "").strip() or f"{current_user.username}の配信"
        existing = StreamSession(broadcaster_id=current_user.id, title=title)
        db.session.add(existing)
        db.session.commit()

    return redirect(url_for("stream.index"))


@stream_bp.route("/stream/stop", methods=["POST"])
@login_required
def stop():
    session_obj = _active_session()
    if session_obj and (session_obj.broadcaster_id == current_user.id or current_user.is_admin):
        session_obj.is_active = False
        session_obj.ended_at = utcnow()
        StreamViewer.query.filter_by(session_id=session_obj.id).delete()
        StreamSignal.query.filter_by(session_id=session_obj.id).delete()
        db.session.commit()
        flash("配信を終了しました。", "success")
    return redirect(url_for("stream.index"))


@stream_bp.route("/stream/join", methods=["POST"])
@login_required
def join():
    session_obj = _active_session()
    if not session_obj:
        return jsonify({"error": "現在配信中の番組がありません。"}), 400
    if session_obj.broadcaster_id == current_user.id:
        return jsonify({"error": "自分自身の配信は視聴できません。"}), 400

    viewer = StreamViewer.query.filter_by(session_id=session_obj.id, user_id=current_user.id).first()
    if viewer:
        viewer.last_seen = utcnow()
    else:
        db.session.add(StreamViewer(session_id=session_obj.id, user_id=current_user.id))
    db.session.commit()

    return jsonify({"ok": True, "session_id": session_obj.id, "broadcaster_id": session_obj.broadcaster_id})


@stream_bp.route("/stream/heartbeat", methods=["POST"])
@login_required
def heartbeat():
    """視聴者・配信者ともに定期的に呼び、生存確認と視聴者一覧の更新を行う"""
    session_obj = _active_session()
    if not session_obj:
        return jsonify({"active": False})

    if session_obj.broadcaster_id != current_user.id:
        viewer = StreamViewer.query.filter_by(session_id=session_obj.id, user_id=current_user.id).first()
        if viewer:
            viewer.last_seen = utcnow()
            db.session.commit()

    cutoff = utcnow() - timedelta(seconds=VIEWER_TIMEOUT_SECONDS)
    viewers = (
        StreamViewer.query.filter(StreamViewer.session_id == session_obj.id, StreamViewer.last_seen >= cutoff).all()
    )

    return jsonify({
        "active": True, "session_id": session_obj.id, "broadcaster_id": session_obj.broadcaster_id,
        "viewer_ids": [v.user_id for v in viewers],
    })


@stream_bp.route("/stream/signal/send", methods=["POST"])
@login_required
def send_signal():
    data = request.get_json(force=True)
    session_obj = _active_session()
    if not session_obj:
        return jsonify({"error": "配信が見つかりません。"}), 400

    to_user_id = data.get("to_user_id")
    kind = data.get("kind")
    payload = data.get("payload")

    if kind not in ("offer", "answer", "ice") or not to_user_id or payload is None:
        return jsonify({"error": "シグナルの形式が不正です。"}), 400

    db.session.add(StreamSignal(
        session_id=session_obj.id, from_user_id=current_user.id, to_user_id=to_user_id,
        kind=kind, payload=json.dumps(payload)
    ))
    db.session.commit()
    return jsonify({"ok": True})


@stream_bp.route("/stream/signal/poll")
@login_required
def poll_signal():
    since_id = request.args.get("since_id", type=int, default=0)
    signals = (
        StreamSignal.query.filter(StreamSignal.to_user_id == current_user.id, StreamSignal.id > since_id)
        .order_by(StreamSignal.id.asc()).limit(50).all()
    )
    return jsonify({
        "signals": [
            {"id": s.id, "from_user_id": s.from_user_id, "kind": s.kind, "payload": json.loads(s.payload)}
            for s in signals
        ]
    })
