"""
「株式市場」に近いゲームとして、実際の暗号資産価格(CoinGecko)を使った値上がり/値下がり予想ゲーム。
本物の株価APIは登録が必須のため、登録不要で無料のCoinGecko(暗号資産)を採用している。
"""
import json
from datetime import timedelta

import requests
from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, MarketGame, AppState, utcnow
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "dogecoin": "DOGE"}
ROUND_SECONDS = 30
MULTIPLIER = 1.9
PRICE_CACHE_SECONDS = 8  # CoinGeckoの無料枠(登録不要・1分10〜30回)を節約するための簡易キャッシュ


def _get_cached_prices():
    row = AppState.query.get("market_price_cache")
    if row:
        try:
            payload = json.loads(row.value)
            cached_at = utcnow().fromisoformat(payload["at"])
            if (utcnow() - cached_at).total_seconds() < PRICE_CACHE_SECONDS:
                return payload["prices"]
        except (ValueError, KeyError, TypeError):
            pass
    return None


def _fetch_prices():
    cached = _get_cached_prices()
    if cached:
        return cached

    resp = requests.get(
        COINGECKO_URL, params={"ids": ",".join(SYMBOLS.keys()), "vs_currencies": "usd"}, timeout=8
    )
    resp.raise_for_status()
    prices = resp.json()

    row = AppState.query.get("market_price_cache")
    payload = json.dumps({"at": utcnow().isoformat(), "prices": prices})
    if row:
        row.value = payload
    else:
        db.session.add(AppState(key="market_price_cache", value=payload))
    db.session.commit()

    return prices


@games_bp.route("/market")
@login_required
def market_page():
    game = MarketGame.query.filter_by(user_id=current_user.id).first()
    try:
        prices = _fetch_prices()
    except (requests.RequestException, ValueError):
        prices = None
    return render_template(
        "games/market.html", symbols=SYMBOLS, prices=prices, game=game, round_seconds=ROUND_SECONDS
    )


@games_bp.route("/market/start", methods=["POST"])
@login_required
def market_start():
    if MarketGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中の予想があります。"}), 400

    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    symbol = data.get("symbol")
    pick = data.get("pick")

    if symbol not in SYMBOLS:
        return jsonify({"error": "対象の銘柄が不正です。"}), 400
    if pick not in ("up", "down"):
        return jsonify({"error": "選択が不正です。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    try:
        prices = _fetch_prices()
        start_price = prices[symbol]["usd"]
    except (requests.RequestException, ValueError, KeyError):
        return jsonify({"error": "価格データの取得に失敗しました。しばらくしてからもう一度お試しください。"}), 503

    user = current_user
    user.balance -= wager

    game = MarketGame(
        user_id=user.id, wager=wager, symbol=symbol, pick=pick, start_price=start_price,
        resolve_at=utcnow() + timedelta(seconds=ROUND_SECONDS)
    )
    db.session.add(game)
    db.session.commit()

    return jsonify({"balance": user.balance, "start_price": start_price, "resolve_in": ROUND_SECONDS})


@games_bp.route("/market/resolve", methods=["POST"])
@login_required
def market_resolve():
    game = MarketGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中の予想がありません。"}), 400

    if utcnow() < game.resolve_at:
        remaining = (game.resolve_at - utcnow()).total_seconds()
        return jsonify({"resolved": False, "remaining": max(0, round(remaining))})

    user = current_user
    try:
        prices = _fetch_prices()
        end_price = prices[game.symbol]["usd"]
    except (requests.RequestException, ValueError, KeyError):
        return jsonify({"error": "価格データの取得に失敗しました。少し待ってからもう一度お試しください。"}), 503

    if end_price == game.start_price:
        outcome = "push"
        multiplier = 1.0
        payout = game.wager
        credit_winnings(user, payout)
    else:
        actual_direction = "up" if end_price > game.start_price else "down"
        won = actual_direction == game.pick
        if won:
            multiplier = scale_multiplier("market", MULTIPLIER)
            payout = round(game.wager * multiplier)
            credit_winnings(user, payout)
            outcome = "win"
        else:
            multiplier = 0
            payout = 0
            outcome = "lose"

    apply_rakeback(user, game.wager)

    db.session.add(BetRecord(
        user_id=user.id, game="market", wager=game.wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=user.nonce,
        result_json=json.dumps({
            "symbol": game.symbol, "pick": game.pick, "start_price": game.start_price,
            "end_price": end_price, "outcome": outcome
        })
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({
        "resolved": True, "outcome": outcome, "start_price": game.start_price, "end_price": end_price,
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
