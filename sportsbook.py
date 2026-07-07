"""
実際のサッカーの試合結果を使ったスポーツベット機能。
データはTheSportsDB(https://www.thesportsdb.com)の無料APIから取得する。
無料の共通キー"123"を使用(登録不要・1分間30リクエストまで)。
"""
from datetime import datetime

import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from extensions import db
from models import SportsEvent, SportsBet, AppState, Transaction, utcnow
from games.common import validate_wager, apply_rakeback, credit_winnings
from notifications import notify

sportsbook_bp = Blueprint("sportsbook", __name__)

API_BASE = "https://www.thesportsdb.com/api/v1/json/123"
SYNC_COOLDOWN_SECONDS = 300  # 5分に1回だけAPIを叩く(無料枠を節約するため)

LEAGUES = {
    "4328": "プレミアリーグ",
    "4335": "ラ・リーガ",
    "4331": "ブンデスリーガ",
    "4480": "チャンピオンズリーグ",
}

DEFAULT_ODDS = {"home": 1.9, "draw": 3.2, "away": 1.9}
ODDS_HOUSE_EDGE = 0.08
HOME_ADVANTAGE = 0.08  # ホームチームには基本勝率に少し下駄を履かせる


def _get_state(key):
    row = AppState.query.get(key)
    return row.value if row else None


def _set_state(key, value):
    row = AppState.query.get(key)
    if row:
        row.value = value
    else:
        db.session.add(AppState(key=key, value=value))


def _fetch_standings(league_id):
    """リーグの現在の順位表を取得し、{チーム名: 勝ち点} の辞書を返す(失敗時は空辞書)"""
    try:
        resp = requests.get(f"{API_BASE}/lookuptable.php", params={"l": league_id}, timeout=8)
        data = resp.json() if resp.status_code == 200 else {}
        table = data.get("table") or []
        result = {}
        for row in table:
            name = row.get("strTeam")
            if name:
                try:
                    result[name] = float(row.get("intPoints", 0) or 0)
                except (TypeError, ValueError):
                    result[name] = 0.0
        return result
    except (requests.RequestException, ValueError):
        return {}


def _compute_odds(home_points, away_points):
    """順位表の勝ち点差から、ホーム/ドロー/アウェイの倍率を算出する"""
    diff = home_points - away_points
    adj = max(-0.35, min(0.35, diff * 0.01))  # 勝ち点差1につき1%、最大±35%まで調整

    home_p = max(0.10, min(0.80, 0.40 + HOME_ADVANTAGE + adj))
    away_p = max(0.10, min(0.80, 0.30 - adj))
    draw_p = max(0.08, 1 - home_p - away_p)

    total = home_p + away_p + draw_p
    home_p, away_p, draw_p = home_p / total, away_p / total, draw_p / total

    def to_odds(p):
        return round((1 / p) * (1 - ODDS_HOUSE_EDGE), 2)

    return to_odds(home_p), to_odds(draw_p), to_odds(away_p)


def _upsert_event(ev, league_id, standings):
    external_id = ev.get("idEvent")
    if not external_id:
        return

    event = SportsEvent.query.filter_by(external_id=external_id).first()
    if not event:
        event = SportsEvent(
            external_id=external_id,
            odds_home=DEFAULT_ODDS["home"], odds_draw=DEFAULT_ODDS["draw"], odds_away=DEFAULT_ODDS["away"],
        )
        db.session.add(event)

    event.sport = "soccer"
    event.league_name = LEAGUES.get(league_id, ev.get("strLeague") or "")
    event.home_team = ev.get("strHomeTeam") or ""
    event.away_team = ev.get("strAwayTeam") or ""

    # 順位表からチームの勝ち点を取得できる場合は、強さに応じてオッズを再計算する
    # (Champions Leagueなど、国内リーグと違う枠組みのチームは順位表にないため、その場合はデフォルトのまま)
    home_points = standings.get(event.home_team)
    away_points = standings.get(event.away_team)
    if home_points is not None and away_points is not None and event.status != "finished":
        event.odds_home, event.odds_draw, event.odds_away = _compute_odds(home_points, away_points)

    try:
        date_str = f"{ev.get('dateEvent')} {ev.get('strTime') or '00:00:00'}"
        event.event_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass

    home_score = ev.get("intHomeScore")
    away_score = ev.get("intAwayScore")

    if home_score is not None and away_score is not None:
        try:
            hs, aws = int(home_score), int(away_score)
        except (TypeError, ValueError):
            return
        event.status = "finished"
        event.home_score = hs
        event.away_score = aws
        if hs > aws:
            event.winner = "home"
        elif aws > hs:
            event.winner = "away"
        else:
            event.winner = "draw"
    else:
        event.status = "upcoming"


def sync_events():
    """TheSportsDBから試合日程・結果・順位表を取得してDBに反映する(頻繁に叩きすぎないようcooldownあり)"""
    last = _get_state("last_sports_sync")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (utcnow() - last_dt).total_seconds() < SYNC_COOLDOWN_SECONDS:
                return
        except ValueError:
            pass

    for league_id in LEAGUES:
        standings = _fetch_standings(league_id)
        for endpoint in ("eventsnextleague.php", "eventspastleague.php"):
            try:
                resp = requests.get(f"{API_BASE}/{endpoint}", params={"id": league_id}, timeout=8)
                data = resp.json() if resp.status_code == 200 else {}
                for ev in (data.get("events") or [])[:15]:
                    _upsert_event(ev, league_id, standings)
            except (requests.RequestException, ValueError):
                continue  # このリーグ・エンドポイントの取得に失敗しても他は続ける

    _set_state("last_sports_sync", utcnow().isoformat())
    db.session.commit()
    resolve_pending_bets()


def resolve_pending_bets():
    """結果が確定した試合について、保留中のベットを精算する"""
    pending = SportsBet.query.filter_by(status="pending").all()
    for bet in pending:
        event = bet.event
        if not event or event.status != "finished" or not event.winner:
            continue

        won = bet.pick == event.winner
        if won:
            payout = round(bet.wager * bet.odds)
            bet.status = "won"
            bet.payout = payout
            credit_winnings(bet.user, payout)
            db.session.add(Transaction(
                user_id=bet.user_id, amount=payout, kind="sportsbook_win",
                description=f"{event.home_team} vs {event.away_team} 的中"
            ))
            notify(
                bet.user_id,
                f"スポーツベット的中: {event.home_team} {event.home_score}-{event.away_score} {event.away_team} ・ "
                f"{payout:,} Embersを獲得しました。"
            )
        else:
            bet.status = "lost"
            bet.payout = 0
    db.session.commit()


@sportsbook_bp.route("/sportsbook")
@login_required
def index():
    sync_events()
    now = utcnow()
    upcoming = (
        SportsEvent.query.filter_by(status="upcoming")
        .filter((SportsEvent.event_time.is_(None)) | (SportsEvent.event_time > now))
        .order_by(SportsEvent.event_time.asc().nullslast())
        .limit(30).all()
    )
    my_bets = (
        SportsBet.query.filter_by(user_id=current_user.id)
        .order_by(SportsBet.created_at.desc()).limit(20).all()
    )
    return render_template("sportsbook.html", events=upcoming, bets=my_bets, leagues=LEAGUES)


@sportsbook_bp.route("/sportsbook/bet", methods=["POST"])
@login_required
def place_bet():
    event_id = request.form.get("event_id")
    pick = request.form.get("pick")
    try:
        wager = int(request.form.get("wager", "0"))
    except ValueError:
        wager = 0

    event = SportsEvent.query.get(event_id)
    if not event or event.status != "upcoming":
        flash("この試合はすでに締め切られています。", "error")
        return redirect(url_for("sportsbook.index"))
    if event.event_time and event.event_time <= utcnow():
        flash("この試合はすでに開始されているため、賭けられません。", "error")
        return redirect(url_for("sportsbook.index"))
    if pick not in ("home", "draw", "away"):
        flash("選択が不正です。", "error")
        return redirect(url_for("sportsbook.index"))

    error = validate_wager(current_user, wager)
    if error:
        flash(error, "error")
        return redirect(url_for("sportsbook.index"))

    odds = {"home": event.odds_home, "draw": event.odds_draw, "away": event.odds_away}[pick]

    current_user.balance -= wager
    apply_rakeback(current_user, wager)
    db.session.add(SportsBet(user_id=current_user.id, event_id=event.id, pick=pick, wager=wager, odds=odds))
    db.session.add(Transaction(
        user_id=current_user.id, amount=-wager, kind="sportsbook_bet",
        description=f"{event.home_team} vs {event.away_team}({pick})"
    ))
    db.session.commit()

    flash(f"{event.home_team} vs {event.away_team} に {wager:,} Embersを賭けました。結果が出たら自動的に精算されます。", "success")
    return redirect(url_for("sportsbook.index"))
