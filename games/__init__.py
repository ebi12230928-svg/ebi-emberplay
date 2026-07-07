from flask import Blueprint

games_bp = Blueprint("games", __name__, url_prefix="/games")

# 各ゲームモジュールを読み込んでルートを登録する(遅延importで循環importを回避)
from . import dice        # noqa: E402,F401
from . import limbo       # noqa: E402,F401
from . import mines       # noqa: E402,F401
from . import plinko      # noqa: E402,F401
from . import keno        # noqa: E402,F401
from . import wheel       # noqa: E402,F401
from . import hilo        # noqa: E402,F401
from . import tower       # noqa: E402,F401
from . import roulette    # noqa: E402,F401
from . import blackjack   # noqa: E402,F401
from . import baccarat    # noqa: E402,F401
from . import slots       # noqa: E402,F401
from . import crash       # noqa: E402,F401
from . import videopoker  # noqa: E402,F401
from . import coinflip    # noqa: E402,F401
from . import war         # noqa: E402,F401
from . import sicbo       # noqa: E402,F401
