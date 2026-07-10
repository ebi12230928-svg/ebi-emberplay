import json
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import Event, BetRecord, Transaction, utcnow
from games.common import credit_winnings
from notifications import notify, notify_all

events_bp = Blueprint("events", __name__)

# 管理者が選べる5つのイベントテンプレート(選んだ後も金額などは自由に調整できる)
EVENT_PRESETS = {
    "daily": {
        "name": "デイリーレース(24時間・全ゲーム対象)",
        "title": "デイリーウェイジャーレース", "hours": 24, "game_filter": None,
        "prizes": [3000, 2000, 1000],
    },
    "weekend": {
        "name": "ウィークエンドレース(48時間・全ゲーム対象)",
        "title": "ウィークエンドレース", "hours": 48, "game_filter": None,
        "prizes": [10000, 6000, 4000, 2000, 1000],
    },
    "slots_only": {
        "name": "スロット限定レース(24時間・スロットのみ対象)",
        "title": "スロット限定レース", "hours": 24, "game_filter": "slots",
        "prizes": [5000, 3000, 2000],
    },
    "high_roller": {
        "name": "ハイローラーレース(72時間・全ゲーム対象・高額賞金)",
        "title": "ハイローラーレース", "hours": 72, "game_filter": None,
        "prizes": [20000, 10000, 5000],
    },
    "newcomer": {
        "name": "みんなでレース(24時間・全ゲーム対象・入賞枠多め)",
        "title": "みんなでレース", "hours": 24, "game_filter": None,
        "prizes": [2000, 1500, 1000, 500, 500],
    },
}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _leaderboard_for(event, limit):
    query = db.session.query(BetRecord.user_id, func.sum(BetRecord.wager).label("wagered")).filter(
        BetRecord.created_at >= event.starts_at, BetRecord.created_at < event.ends_at
    )
    if event.game_filter:
        query = query.filter(BetRecord.game.like(f"{event.game_filter}%"))
    return (
        query.group_by(BetRecord.user_id)
        .order_by(func.sum(BetRecord.wager).desc())
        .limit(limit)
        .all()
    )


def _finalize(event):
    prizes = json.loads(event.prizes_json)
    rows = _leaderboard_for(event, len(prizes))

    results = []
    for rank, (user_id, wagered) in enumerate(rows):
        prize = prizes[rank]
        from models import User
        user = User.query.get(user_id)
        if not user:
            continue
        if prize > 0:
            credit_winnings(user, prize)
            db.session.add(Transaction(
                user_id=user.id, amount=prize, kind="event_prize",
                description=f"「{event.title}」{rank + 1}位入賞"
            ))
            notify(user.id, f"「{event.title}」で{rank + 1}位入賞しました!{prize:,} Embersを獲得しました。")
            try:
                from achievements import check_achievements
                check_achievements(user, event_win=True)
            except Exception:
                pass
        results.append({"username": user.username, "wagered": int(wagered), "rank": rank + 1, "prize": prize})

    event.results_json = json.dumps(results)
    event.status = "finished"
    event.finalized_at = utcnow()
    db.session.commit()

    if results:
        summary = " / ".join(f"{r['rank']}位 {r['username']}" for r in results)
        notify_all(f"「{event.title}」が終了しました。結果: {summary}")
        db.session.commit()


def _sync_events():
    """開催時刻・終了時刻に応じて、イベントの状態を自動更新する(訪問のたびにチェックされる)"""
    now = utcnow()

    scheduled = Event.query.filter_by(status="scheduled").all()
    for event in scheduled:
        if event.starts_at <= now:
            event.status = "active"
    db.session.commit()

    active = Event.query.filter_by(status="active").all()
    for event in active:
        if event.ends_at <= now:
            _finalize(event)


@events_bp.route("/events")
@login_required
def index():
    _sync_events()

    active_events = Event.query.filter_by(status="active").order_by(Event.ends_at.asc()).all()
    scheduled_events = Event.query.filter_by(status="scheduled").order_by(Event.starts_at.asc()).all()
    finished_events = Event.query.filter_by(status="finished").order_by(Event.finalized_at.desc()).limit(10).all()

    active_boards = []
    for event in active_events:
        prizes = json.loads(event.prizes_json)
        rows = _leaderboard_for(event, len(prizes))
        total_prize_pool = sum(prizes)
        hours_left = max(0, round((event.ends_at - utcnow()).total_seconds() / 3600, 1))
        from models import User
        board = []
        for rank, (user_id, wagered) in enumerate(rows):
            user = User.query.get(user_id)
            if user:
                prize = prizes[rank]
                pct = round(prize / total_prize_pool * 100, 1) if total_prize_pool else 0
                board.append({
                    "rank": rank + 1, "username": user.username, "wagered": int(wagered),
                    "prize": prize, "pct": pct
                })
        active_boards.append({
            "event": event, "board": board, "prizes": prizes,
            "total_prize_pool": total_prize_pool, "hours_left": hours_left
        })

    finished_info = []
    for event in finished_events:
        results = json.loads(event.results_json) if event.results_json else []
        finished_info.append({"event": event, "results": results})

    return render_template(
        "events.html", active_boards=active_boards, scheduled_events=scheduled_events, finished_info=finished_info
    )


@events_bp.route("/admin/events/create", methods=["POST"])
@login_required
@admin_required
def create():
    preset_key = request.form.get("preset", "").strip()
    preset = EVENT_PRESETS.get(preset_key)
    if not preset:
        flash("イベントのテンプレートを選んでください。", "error")
        return redirect(url_for("admin.dashboard"))

    title = request.form.get("title", "").strip() or preset["title"]
    description = request.form.get("description", "").strip()
    prizes_raw = request.form.get("prizes", "").strip()

    try:
        prizes = [int(p.strip()) for p in prizes_raw.split(",") if p.strip()] if prizes_raw else preset["prizes"]
    except ValueError:
        flash("賞金の形式が正しくありません(カンマ区切りの数字で入力してください)。", "error")
        return redirect(url_for("admin.dashboard"))

    if not prizes:
        flash("賞金は1つ以上入力してください。", "error")
        return redirect(url_for("admin.dashboard"))

    from datetime import timedelta
    starts_at = utcnow()
    ends_at = starts_at + timedelta(hours=preset["hours"])

    event = Event(
        title=title, description=description, starts_at=starts_at, ends_at=ends_at,
        prizes_json=json.dumps(prizes), game_filter=preset["game_filter"], created_by=current_user.username
    )
    db.session.add(event)
    db.session.commit()

    notify_all(f"新しいイベント「{title}」が開催されます!詳細は/eventsから確認できます。")
    db.session.commit()

    flash(f"イベント「{title}」を作成しました({preset['hours']}時間開催)。", "success")
    return redirect(url_for("admin.dashboard"))


@events_bp.route("/admin/events/<int:event_id>/cancel", methods=["POST"])
@login_required
@admin_required
def cancel(event_id):
    event = Event.query.get(event_id)
    if event and event.status != "finished":
        db.session.delete(event)
        db.session.commit()
        flash("イベントを削除しました。", "success")
    return redirect(url_for("admin.dashboard"))
