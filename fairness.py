"""
プロヴァブリーフェア(Provably Fair)乱数生成
server_seed(秘密・事前にハッシュ値を公開) + client_seed + nonce から
HMAC-SHA256を使って再現可能かつ検証可能な乱数列を作る。
"""
import hashlib
import hmac


def _hmac_bytes(server_seed: str, client_seed: str, nonce: int, cursor: int = 0) -> bytes:
    message = f"{client_seed}:{nonce}:{cursor}"
    return hmac.new(server_seed.encode(), message.encode(), hashlib.sha256).digest()


def get_floats(server_seed: str, client_seed: str, nonce: int, count: int) -> list[float]:
    """0以上1未満の浮動小数点数をcount個生成する"""
    floats = []
    cursor = 0
    while len(floats) < count:
        digest = _hmac_bytes(server_seed, client_seed, nonce, cursor)
        # 32バイトのdigestから4バイトずつ取り出して[0,1)の浮動小数点数に変換
        for i in range(0, len(digest), 4):
            if len(floats) >= count:
                break
            chunk = digest[i:i + 4]
            if len(chunk) < 4:
                continue
            value = int.from_bytes(chunk, "big") / 0xFFFFFFFF
            floats.append(value)
        cursor += 1
    return floats


def get_float(server_seed: str, client_seed: str, nonce: int) -> float:
    return get_floats(server_seed, client_seed, nonce, 1)[0]


def roll_dice_100(server_seed: str, client_seed: str, nonce: int) -> float:
    """0.00〜99.99のダイス目を返す(2桁小数)"""
    f = get_float(server_seed, client_seed, nonce)
    return round(f * 10000) / 100


def crash_point(server_seed: str, client_seed: str, nonce: int, house_edge: float = 0.04) -> float:
    """クラッシュ/リンボ系ゲームの倍率を生成する(1.00倍が最小)"""
    f = get_float(server_seed, client_seed, nonce)
    f = max(f, 1e-9)
    # 業界標準的な分布: houseの取り分をedgeとして反映
    if f < house_edge:
        return 1.00
    result = (1 / (1 - f)) * (1 - house_edge)
    return max(1.00, round(result, 2))


def mines_positions(server_seed: str, client_seed: str, nonce: int, grid_size: int, mine_count: int) -> list[int]:
    """grid_size マスの中から mine_count 個の地雷位置(重複なし)を決定する"""
    floats = get_floats(server_seed, client_seed, nonce, grid_size * 2)
    order = sorted(range(grid_size), key=lambda i: floats[i])
    return sorted(order[:mine_count])


def shuffle_indices(server_seed: str, client_seed: str, nonce: int, count: int) -> list[int]:
    """0..count-1 の並びを公平にシャッフルした順序を返す(トランプのシャッフル等に使用)"""
    floats = get_floats(server_seed, client_seed, nonce, count * 2)
    return sorted(range(count), key=lambda i: floats[i])


def binomial_path(server_seed: str, client_seed: str, nonce: int, steps: int) -> list[int]:
    """Plinko用: 各行で右に落ちたかどうか(0=左,1=右)をsteps回分生成する"""
    floats = get_floats(server_seed, client_seed, nonce, steps)
    return [1 if f >= 0.5 else 0 for f in floats]


def plinko_table(rows: int, risk: str, house_edge: float = 0.03) -> list[float]:
    """行数とリスクからPlinkoの配当テーブルを生成する(期待値が(1-house_edge)になるよう正規化)"""
    from math import comb

    risk_exponent = {"low": 1.6, "medium": 2.4, "high": 3.4}.get(risk, 2.4)
    center = rows / 2

    probs = [comb(rows, i) / (2 ** rows) for i in range(rows + 1)]
    shapes = []
    for i in range(rows + 1):
        distance = abs(i - center) / center if center > 0 else 0
        shapes.append(risk_exponent ** (distance * 3))

    raw_ev = sum(p * s for p, s in zip(probs, shapes))
    scale = (1 - house_edge) / raw_ev if raw_ev > 0 else 1
    return [round(s * scale, 2) for s in shapes]


def wheel_table(segment_count: int, risk: str, house_edge: float = 0.03) -> list[float]:
    """セグメント数とリスクからWheelの配当テーブルを生成する(均等な確率・期待値を正規化)"""
    risk_base = {"low": 1.05, "medium": 1.35, "high": 1.9}.get(risk, 1.35)
    shapes = [risk_base ** i for i in range(segment_count)]
    mean_shape = sum(shapes) / segment_count
    scale = (1 - house_edge) / mean_shape if mean_shape > 0 else 1
    table = [round(s * scale, 2) for s in shapes]
    return table


def keno_paytable(picks: int, drawn: int = 10, total: int = 40, house_edge: float = 0.06) -> list[float]:
    """選択数からKenoの配当テーブル(一致数ごとの倍率)を生成する"""
    from math import comb

    def hypergeom_prob(m):
        if m > picks or m > drawn:
            return 0.0
        denom = comb(total, drawn)
        return comb(picks, m) * comb(total - picks, drawn - m) / denom

    probs = [hypergeom_prob(m) for m in range(picks + 1)]
    base = 2.3
    shapes = [0.0] + [base ** m for m in range(1, picks + 1)]

    raw_ev = sum(p * s for p, s in zip(probs, shapes))
    scale = (1 - house_edge) / raw_ev if raw_ev > 0 else 1
    return [round(s * scale, 2) for s in shapes]


def draw_keno_numbers(server_seed: str, client_seed: str, nonce: int, drawn: int, total: int) -> list[int]:
    floats = get_floats(server_seed, client_seed, nonce, total * 2)
    order = sorted(range(total), key=lambda i: floats[i])
    return sorted(order[:drawn])
