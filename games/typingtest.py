"""カジノ要素とは無関係のミニゲーム。タイピング速度と正確さに応じてEmbersを直接獲得できる(賭け金なし)。"""
import random

from flask import render_template, request, jsonify, session
from flask_login import login_required, current_user

from extensions import db
from models import Transaction
from . import games_bp

REWARD_BASE = 30
REWARD_PER_CPS = 25  # 1秒あたり1文字につきボーナス
MAX_REWARD = 300
MIN_ACCURACY = 0.85  # これを下回ると報酬なし

SENTENCES = [
    "きつねが素早く走り抜ける夜道は静かだった",
    "毎朝コーヒーを飲んでから仕事を始めます",
    "図書館で静かに本を読むのが好きです",
    "新しい街に引っ越してから半年が経ちました",
    "山の上から見る景色はとても美しかった",
    "友達と一緒に映画を見に行く約束をした",
    "雨の日は家でゆっくり過ごすのが一番だ",
    "駅前のパン屋のクロワッサンはとても美味しい",
    "週末は公園でランニングをしています",
    "新しいレシピに挑戦してみようと思う",
]


@games_bp.route("/typingtest")
@login_required
def typingtest_page():
    return render_template("games/typingtest.html")


@games_bp.route("/typingtest/start", methods=["POST"])
@login_required
def typingtest_start():
    sentence = random.choice(SENTENCES)
    session["typingtest_sentence"] = sentence
    return jsonify({"sentence": sentence})


@games_bp.route("/typingtest/submit", methods=["POST"])
@login_required
def typingtest_submit():
    data = request.get_json(force=True)
    typed = (data.get("typed") or "")
    try:
        elapsed_ms = float(data.get("elapsed_ms"))
    except (TypeError, ValueError):
        return jsonify({"error": "計測データが不正です。"}), 400

    original = session.pop("typingtest_sentence", None)
    if not original:
        return jsonify({"error": "出題情報が見つかりません。もう一度スタートしてください。"}), 400
    if elapsed_ms <= 0:
        return jsonify({"error": "計測データが不正です。"}), 400

    # 文字単位の一致率で正確さを判定(簡易的なLevenshtein距離の代わりに位置ごとの一致で近似)
    matches = sum(1 for a, b in zip(original, typed) if a == b)
    accuracy = matches / len(original) if original else 0

    if accuracy < MIN_ACCURACY:
        return jsonify({
            "reward": 0, "accuracy": round(accuracy * 100, 1), "balance": current_user.balance,
            "message": "正確さが足りませんでした(85%以上必要です)。"
        })

    chars_per_sec = len(original) / (elapsed_ms / 1000)
    reward = min(MAX_REWARD, round(REWARD_BASE + chars_per_sec * REWARD_PER_CPS))

    current_user.balance += reward
    db.session.add(Transaction(
        user_id=current_user.id, amount=reward, kind="typingtest",
        description=f"タイピングテスト({round(chars_per_sec,1)}文字/秒)"
    ))
    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({
        "reward": reward, "accuracy": round(accuracy * 100, 1),
        "chars_per_sec": round(chars_per_sec, 1), "balance": current_user.balance
    })
