"""Reset simulator tables and create a fresh OPEN game."""

from seed_game_events import seed_events_for_game


DELETE_ORDER = [
    ("information_purchases", "purchase_id"),
    ("transactions", "transaction_id"),
    ("player_holdings", "holding_id"),
    ("game_events", "game_event_id"),
    ("stock_prices", "price_id"),
    ("players", "player_id"),
    ("games", "game_id"),
    ("stocks", "stock_id"),
]

STOCK_ROWS = [
    {"stock_name": "한빛전자", "ticker": "HBE01", "sector": "반도체", "initial_price": 7000},
    {"stock_name": "모터웍스", "ticker": "MTW02", "sector": "자동차", "initial_price": 20000},
    {"stock_name": "넷플로우", "ticker": "NTF03", "sector": "인터넷", "initial_price": 18000},
    {"stock_name": "픽셀마켓", "ticker": "PXM04", "sector": "플랫폼", "initial_price": 5000},
    {"stock_name": "메모리온", "ticker": "MMO05", "sector": "반도체", "initial_price": 18000},
    {"stock_name": "에너젠", "ticker": "ENZ06", "sector": "배터리", "initial_price": 38000},
    {"stock_name": "새봄금융", "ticker": "SBF07", "sector": "금융", "initial_price": 9500},
]


def reset_and_create_game(supabase, invite_code="KDA5", game_days=10, reset_minutes=1):
    for table_name, primary_key in DELETE_ORDER:
        supabase.table(table_name).delete().gte(primary_key, 0).execute()

    stocks = supabase.table("stocks").insert(STOCK_ROWS).select().execute()
    if not stocks.data:
        raise RuntimeError("종목 생성에 실패했습니다.")

    game = supabase.table("games").insert({
        "invite_code": invite_code,
        "game_days": game_days,
        "reset_minutes": reset_minutes,
        "status": "OPEN",
        "current_day": 1,
    }).select().execute()

    if not game.data:
        raise RuntimeError("새 게임 생성에 실패했습니다.")

    created_game = game.data[0]
    seed_events_for_game(created_game["game_id"], supabase)
    return created_game
