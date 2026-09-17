from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone
import os
import random

from game_reset import reset_and_create_game

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

ADMIN_CODE = os.getenv("ADMIN_CODE")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
GAME_TICK_SECONDS = int(os.getenv("GAME_TICK_SECONDS", "30"))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/enter", methods=["POST"])
def enter():

    invite_code = request.form.get("invite_code", "").strip().upper()

    if not invite_code:
        return "초대코드를 입력해주세요.", 400

    # 관리자 코드
    if invite_code == ADMIN_CODE:
        return redirect(url_for("admin_login"))

    # 참가자 코드
    result = (
        supabase
        .table("games")
        .select("*")
        .eq("invite_code", invite_code)
        .execute()
    )

    if not result.data:
        return "존재하지 않는 초대코드입니다.", 404

    game = result.data[0]
    if game["status"] == "FINISHED":
        return "게임이 종료되었습니다. 관리자가 다시 시작할 때까지 참가할 수 없습니다.", 403

    existing_player = _session_player(game["game_id"])
    if existing_player:
        if game["status"] == "PLAYING":
            return redirect(url_for("game"))
        return redirect(url_for("waiting"))

    if game["status"] not in {"OPEN", "PLAYING"}:
        return "존재하지 않거나 참가할 수 없는 게임입니다."

    return render_template(
        "join.html",
        game=game,
        tick_seconds=GAME_TICK_SECONDS,
        rejoin=game["status"] == "PLAYING",
    )

@app.route("/start-game/<int:game_id>", methods=["POST"])
def start_game(game_id):

    # 관리자 확인
    if not session.get("admin"):
        return "관리자 권한이 필요합니다."

    # 게임 확인
    result = (
        supabase
        .table("games")
        .select("*")
        .eq("game_id", game_id)
        .eq("status", "OPEN")
        .execute()
    )

    if not result.data:
        return "게임을 찾을 수 없습니다."

    started_at = datetime.now(timezone.utc).isoformat()

    # 게임 시작 시각과 첫 시장일을 기록합니다.
    supabase \
        .table("games") \
        .update({
            "status": "PLAYING",
            "started_at": started_at,
            "current_day": 1
        }) \
        .eq("game_id", game_id) \
        .execute()

    stocks_result = supabase.table("stocks").select("stock_id, initial_price").execute()
    if stocks_result.data:
        existing_prices = (
            supabase
            .table("stock_prices")
            .select("stock_id")
            .eq("game_id", game_id)
            .eq("market_day", 1)
            .execute()
        )
        existing_stock_ids = {row["stock_id"] for row in existing_prices.data}
        initial_prices = [
            {
                "game_id": game_id,
                "stock_id": stock["stock_id"],
                "market_day": 1,
                "price": stock["initial_price"],
                "change_rate": 0,
            }
            for stock in stocks_result.data
            if stock["stock_id"] not in existing_stock_ids
        ]
        if initial_prices:
            supabase.table("stock_prices").insert(initial_prices).execute()

    return redirect(url_for("admin"))


@app.route("/restart-game", methods=["POST"])
def restart_game():

    if not session.get("admin"):
        return "관리자 권한이 필요합니다."

    latest_game = (
        supabase
        .table("games")
        .select("invite_code, game_days, reset_minutes, status")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    previous = latest_game.data[0] if latest_game.data else {}
    if previous and previous.get("status") != "FINISHED":
        return "게임이 종료된 뒤에만 다시 시작할 수 있습니다.", 409

    reset_and_create_game(
        supabase,
        invite_code=previous.get("invite_code") or "KDA5",
        game_days=int(previous.get("game_days") or 10),
        reset_minutes=int(previous.get("reset_minutes") or 1),
    )
    return redirect(url_for("admin"))


@app.route("/waiting-status")
def waiting_status():

    player_id = session.get("player_id")
    game_id = session.get("game_id")

    if not player_id or not game_id:
        return {
            "status": "ERROR"
        }

    result = (
        supabase
        .table("games")
        .select("*")
        .eq("game_id", game_id)
        .execute()
    )

    if not result.data:
        return {
            "status": "ERROR"
        }

    game_data = _advance_game(result.data[0])
    return {
        "status": game_data["status"],
        "current_day": game_data.get("current_day", 1),
        "remaining_seconds": _remaining_seconds(game_data),
    }

@app.route("/game")
def game():

    player_id = session.get("player_id")
    game_id = session.get("game_id")

    if not player_id or not game_id:
        return redirect(url_for("index"))

    result = (
        supabase
        .table("games")
        .select("*")
        .eq("game_id", game_id)
        .execute()
    )

    if not result.data:
        session.pop("game_id", None)
        return redirect(url_for("index"))

    game_data = _advance_game(result.data[0])

    player_result = (
        supabase
        .table("players")
        .select("player_id")
        .eq("player_id", player_id)
        .eq("game_id", game_id)
        .execute()
    )
    if not player_result.data:
        session.pop("player_id", None)
        session.pop("game_id", None)
        return redirect(url_for("index"))

    if game_data["status"] != "PLAYING":
        return redirect(url_for("waiting"))

    return render_template(
        "game.html",
        player_id=player_id,
        game_id=game_id,
        game=game_data
    )


def _session_player(game_id):
    player_id = session.get("player_id")
    if not player_id or session.get("game_id") != game_id:
        return None

    player_result = (
        supabase
        .table("players")
        .select("player_id")
        .eq("player_id", player_id)
        .eq("game_id", game_id)
        .execute()
    )
    return player_result.data[0] if player_result.data else None


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _advance_game(game_data):
    if game_data.get("status") != "PLAYING":
        return game_data

    # started_at이 없으면 현재 시간을 시작 시간으로 설정
    if not game_data.get("started_at"):
        game_data["started_at"] = datetime.now(timezone.utc).isoformat()
        game_data["current_day"] = game_data.get("current_day") or 1

        supabase.table("games").update({
            "started_at": game_data["started_at"],
            "current_day": game_data["current_day"],
        }).eq(
            "game_id",
            game_data["game_id"]
        ).execute()

    started_at = datetime.fromisoformat(
        str(game_data["started_at"]).replace("Z", "+00:00")
    )

    elapsed_seconds = max(
        0,
        (datetime.now(timezone.utc) - started_at).total_seconds()
    )

    interval_seconds = GAME_TICK_SECONDS
    game_days = int(game_data.get("game_days") or 1)
    current_day = int(game_data.get("current_day") or 1)

    target_day = min(
        game_days,
        int(elapsed_seconds // interval_seconds) + 1
    )

    # ============================================================
    # 게임 종료 처리
    # ============================================================

    if elapsed_seconds >= interval_seconds * game_days:

        ended_at = datetime.now(timezone.utc).isoformat()

        supabase.table("games").update({
            "status": "FINISHED",
            "ended_at": ended_at,
            "current_day": game_days
        }).eq(
            "game_id",
            game_data["game_id"]
        ).execute()

        game_data["status"] = "FINISHED"
        game_data["current_day"] = game_days

        return game_data

    # ============================================================
    # DAY 변경 처리
    # ============================================================

    if target_day > current_day:

        stocks = (
            supabase
            .table("stocks")
            .select("stock_id, initial_price")
            .execute()
            .data
        )

        previous_prices = (
            supabase
            .table("stock_prices")
            .select("stock_id, price")
            .eq("game_id", game_data["game_id"])
            .eq("market_day", current_day)
            .execute()
            .data
        )

        events = (
            supabase
            .table("game_events")
            .select(
                "market_day, impact_stock_id, impact_rate"
            )
            .eq("game_id", game_data["game_id"])
            .gte("market_day", current_day + 1)
            .lte("market_day", target_day)
            .execute()
            .data
        )

        # 이전 주가를 종목별로 저장
        price_by_stock = {
            row["stock_id"]: _number(row["price"])
            for row in previous_prices
        }

        # 이벤트 영향률 저장
        event_rates = {}

        for event in events:

            if event.get("impact_stock_id") is not None:

                event_key = (
                    event["market_day"],
                    event["impact_stock_id"]
                )

                event_rates[event_key] = (
                    event_rates.get(event_key, 0)
                    + _number(event.get("impact_rate"))
                )

        # ========================================================
        # 새로운 DAY의 주가 생성
        # ========================================================

        for market_day in range(
            current_day + 1,
            target_day + 1
        ):

            next_prices = []

            for stock in stocks:

                stock_id = stock["stock_id"]

                old_price = price_by_stock.get(
                    stock_id,
                    _number(stock["initial_price"])
                )

                # 게임 전반부 / 후반부 변동폭 차이
                if market_day <= (game_days + 1) // 2:
                    natural_rate = random.uniform(-2.5, 2.5)
                else:
                    natural_rate = random.uniform(-4, 4)

                # 이벤트 영향
                event_rate = event_rates.get(
                    (market_day, stock_id),
                    0
                )

                change_rate = round(
                    natural_rate + event_rate,
                    3
                )

                new_price = round(
                    max(
                        0.01,
                        old_price * (1 + change_rate / 100)
                    ),
                    2
                )

                next_prices.append({
                    "game_id": game_data["game_id"],
                    "stock_id": stock_id,
                    "market_day": market_day,
                    "price": new_price,
                    "change_rate": change_rate,
                })

                # 다음 DAY 계산을 위해 현재 가격 갱신
                price_by_stock[stock_id] = new_price

            # 이미 존재하는 데이터가 있어도 에러가 나지 않도록 UPSERT
            if next_prices:
                supabase.table("stock_prices").upsert(
                    next_prices,
                    on_conflict="game_id,stock_id,market_day"
                ).execute()

        # 현재 DAY 갱신
        game_data["current_day"] = target_day

        supabase.table("games").update({
            "current_day": target_day
        }).eq(
            "game_id",
            game_data["game_id"]
        ).execute()

    return game_data

def _remaining_seconds(game_data):
    if game_data.get("status") != "PLAYING" or not game_data.get("started_at"):
        return 0

    started_at = datetime.fromisoformat(str(game_data["started_at"]).replace("Z", "+00:00"))
    total_seconds = int(game_data.get("game_days") or 1) * GAME_TICK_SECONDS
    elapsed_seconds = int(max(0, (datetime.now(timezone.utc) - started_at).total_seconds()))
    return max(0, total_seconds - elapsed_seconds)

def _day_remaining_seconds(game_data):
    if game_data.get("status") != "PLAYING" or not game_data.get("started_at"):
        return 0

    started_at = datetime.fromisoformat(
        str(game_data["started_at"]).replace("Z", "+00:00")
    )

    elapsed_seconds = int(
        max(
            0,
            (datetime.now(timezone.utc) - started_at).total_seconds()
        )
    )

    elapsed_in_day = elapsed_seconds % GAME_TICK_SECONDS

    return GAME_TICK_SECONDS - elapsed_in_day

@app.route("/api/game-state")
def game_state():

    player_id = session.get("player_id")
    game_id = session.get("game_id")

    if not player_id or not game_id:
        return jsonify({"error": "게임 참가 정보가 없습니다."}), 401

    game_result = (
        supabase
        .table("games")
        .select("*")
        .eq("game_id", game_id)
        .execute()
    )
    if not game_result.data:
        return jsonify({"error": "게임을 찾을 수 없습니다."}), 404

    game_data = _advance_game(game_result.data[0])
    if game_data["status"] != "PLAYING":
        return jsonify({"error": "게임이 종료되었거나 시작되지 않았습니다.", "status": game_data["status"]}), 409

    player_result = (
        supabase
        .table("players")
        .select("player_id, player_name, cash")
        .eq("player_id", player_id)
        .eq("game_id", game_id)
        .execute()
    )
    if not player_result.data:
        return jsonify({"error": "참가자를 찾을 수 없습니다."}), 404

    current_day = game_data.get("current_day") or 1
    stocks_result = supabase.table("stocks").select("*").execute()
    prices_result = (
        supabase
        .table("stock_prices")
        .select("stock_id, price, change_rate")
        .eq("game_id", game_id)
        .eq("market_day", current_day)
        .execute()
    )
    holdings_result = (
        supabase
        .table("player_holdings")
        .select("stock_id, quantity, avg_price")
        .eq("player_id", player_id)
        .execute()
    )
    events_result = (
        supabase
        .table("game_events")
        .select("game_event_id, event_type, title, content, info_price, impact_stock_id, impact_rate")
        .eq("game_id", game_id)
        .eq("market_day", current_day)
        .execute()
    )

    prices = {row["stock_id"]: row for row in prices_result.data}
    holdings = {row["stock_id"]: row for row in holdings_result.data}
    stocks = []
    for stock in stocks_result.data:
        price = prices.get(stock["stock_id"], {})
        stocks.append({
            "stock_id": stock["stock_id"],
            "stock_name": stock["stock_name"],
            "ticker": stock["ticker"],
            "sector": stock.get("sector"),
            "price": _number(price.get("price", stock["initial_price"])),
            "change_rate": _number(price.get("change_rate", 0)),
            "quantity": int(holdings.get(stock["stock_id"], {}).get("quantity", 0)),
            "avg_price": _number(holdings.get(stock["stock_id"], {}).get("avg_price", 0)),
        })

    return jsonify({
        "game": {
            "game_id": game_data["game_id"],
            "current_day": current_day,
            "game_days": game_data["game_days"],
            "reset_minutes": game_data["reset_minutes"],
            "tick_seconds": GAME_TICK_SECONDS,
            "remaining_seconds": _remaining_seconds(game_data),
            "day_remaining_seconds": _day_remaining_seconds(game_data),
        },
        "player": {
            "player_id": player_result.data[0]["player_id"],
            "player_name": player_result.data[0]["player_name"],
            "cash": _number(player_result.data[0]["cash"]),
        },
        "stocks": stocks,
        "events": events_result.data,
    })


@app.route("/api/trade", methods=["POST"])
def trade():

    player_id = session.get("player_id")
    game_id = session.get("game_id")
    payload = request.get_json(silent=True) or {}

    if not player_id or not game_id:
        return jsonify({"error": "게임 참가 정보가 없습니다."}), 401

    side = str(payload.get("side", "")).upper()
    try:
        stock_id = int(payload.get("stock_id"))
        quantity = int(payload.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"error": "종목과 수량을 확인해주세요."}), 400

    if side not in {"BUY", "SELL"} or quantity <= 0:
        return jsonify({"error": "매수/매도 종류와 수량을 확인해주세요."}), 400

    game_result = (
        supabase
        .table("games")
        .select("game_id, status, current_day")
        .eq("game_id", game_id)
        .execute()
    )
    player_result = (
        supabase
        .table("players")
        .select("player_id, cash")
        .eq("player_id", player_id)
        .eq("game_id", game_id)
        .execute()
    )
    stock_result = (
        supabase
        .table("stocks")
        .select("stock_id, initial_price")
        .eq("stock_id", stock_id)
        .execute()
    )

    if not game_result.data:
        return jsonify({"error": "진행 중인 게임이 아닙니다."}), 409
    if not game_result.data:
        return jsonify({"error": "진행 중인 게임이 아닙니다."}), 409

    game_data = game_result.data[0]

    if game_data["status"] != "PLAYING":
        return jsonify({"error": "진행 중인 게임이 아닙니다."}), 409

    if not player_result.data or not stock_result.data:
        return jsonify({"error": "플레이어 또는 종목을 찾을 수 없습니다."}), 404

    current_day = game_data.get("current_day") or 1
    price_result = (
        supabase
        .table("stock_prices")
        .select("price")
        .eq("game_id", game_id)
        .eq("stock_id", stock_id)
        .eq("market_day", current_day)
        .execute()
    )
    price = _number(
        price_result.data[0]["price"] if price_result.data else stock_result.data[0]["initial_price"]
    )
    total_amount = price * quantity
    cash = _number(player_result.data[0]["cash"])

    holding_result = (
        supabase
        .table("player_holdings")
        .select("holding_id, quantity, avg_price")
        .eq("player_id", player_id)
        .eq("stock_id", stock_id)
        .execute()
    )
    holding = holding_result.data[0] if holding_result.data else None
    held_quantity = int(holding["quantity"]) if holding else 0

    if side == "BUY":
        if cash < total_amount:
            return jsonify({"error": "보유 현금이 부족합니다."}), 400
        new_cash = cash - total_amount
        new_quantity = held_quantity + quantity
        old_value = _number(holding.get("avg_price", 0)) * held_quantity if holding else 0
        new_avg_price = (old_value + total_amount) / new_quantity
    else:
        if held_quantity < quantity:
            return jsonify({"error": "보유 주식 수량이 부족합니다."}), 400
        new_cash = cash + total_amount
        new_quantity = held_quantity - quantity
        new_avg_price = _number(holding.get("avg_price", 0)) if new_quantity else 0

    supabase.table("players").update({"cash": new_cash}).eq("player_id", player_id).execute()
    if holding:
        supabase.table("player_holdings").update({
            "quantity": new_quantity,
            "avg_price": new_avg_price,
        }).eq("holding_id", holding["holding_id"]).execute()
    else:
        supabase.table("player_holdings").insert({
            "player_id": player_id,
            "stock_id": stock_id,
            "quantity": new_quantity,
            "avg_price": new_avg_price,
        }).execute()

    supabase.table("transactions").insert({
        "player_id": player_id,
        "stock_id": stock_id,
        "transaction_type": side,
        "quantity": quantity,
        "price": price,
        "total_amount": total_amount,
    }).execute()

    return jsonify({
        "message": "매수 완료" if side == "BUY" else "매도 완료",
        "cash": new_cash,
        "quantity": new_quantity,
        "total_amount": total_amount,
    })


@app.route("/admin")
def admin():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    result = (
        supabase
        .table("games")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    if not result.data:
        return "현재 생성된 게임이 없습니다."

    game = result.data[0]

    players = (
        supabase
        .table("players")
        .select("*")
        .eq("game_id", game["game_id"])
        .execute()
    )

    return render_template(
        "admin.html",
        game=game,
        tick_seconds=GAME_TICK_SECONDS,
        players=players.data
    )


@app.route("/api/admin-state")
def admin_state():

    if not session.get("admin"):
        return jsonify({"error": "관리자 권한이 필요합니다."}), 403

    game_id = request.args.get("game_id", type=int)
    games_query = supabase.table("games").select("*").order("created_at", desc=True)
    if game_id:
        games_query = games_query.eq("game_id", game_id)
    games_result = games_query.execute()

    if not games_result.data:
        return jsonify({"error": "게임을 찾을 수 없습니다."}), 404

    game_data = _advance_game(games_result.data[0])
    current_day = int(game_data.get("current_day") or 1)
    game_id = game_data["game_id"]
    players = supabase.table("players").select("player_id, player_name, cash").eq("game_id", game_id).execute().data
    stocks = supabase.table("stocks").select("stock_id, stock_name, ticker, initial_price").execute().data
    prices = supabase.table("stock_prices").select("stock_id, market_day, price, change_rate").eq("game_id", game_id).order("market_day").execute().data
    holdings = supabase.table("player_holdings").select("player_id, stock_id, quantity, avg_price").execute().data
    transactions = supabase.table("transactions").select("player_id, stock_id, transaction_type, quantity, price, total_amount, created_at").order("created_at", desc=True).limit(15).execute().data

    stock_by_id = {stock["stock_id"]: stock for stock in stocks}
    current_prices = {}
    for price in prices:
        if price["market_day"] == current_day:
            current_prices[price["stock_id"]] = price

    holdings_by_player = {}
    for holding in holdings:
        holdings_by_player.setdefault(holding["player_id"], []).append(holding)

    rankings = []
    for player in players:
        portfolio_value = sum(
            _number(holding["quantity"]) * _number(current_prices.get(holding["stock_id"], {}).get("price", stock_by_id.get(holding["stock_id"], {}).get("initial_price", 0)))
            for holding in holdings_by_player.get(player["player_id"], [])
        )
        cash = _number(player["cash"])
        rankings.append({
            "player_id": player["player_id"],
            "player_name": player["player_name"],
            "cash": cash,
            "portfolio_value": portfolio_value,
            "total_assets": cash + portfolio_value,
        })
    rankings.sort(key=lambda player: player["total_assets"], reverse=True)

    market = []
    for stock in stocks:
        price = current_prices.get(stock["stock_id"], {})
        market.append({
            "stock_id": stock["stock_id"],
            "stock_name": stock["stock_name"],
            "ticker": stock["ticker"],
            "price": _number(price.get("price", stock["initial_price"])),
            "change_rate": _number(price.get("change_rate", 0)),
        })

    chart = {}
    for price in prices:
        stock = stock_by_id.get(price["stock_id"])
        if stock:
            chart.setdefault(stock["ticker"], {"name": stock["stock_name"], "points": []})["points"].append({
                "day": price["market_day"],
                "price": _number(price["price"]),
            })

    recent_trades = []
    player_names = {player["player_id"]: player["player_name"] for player in players}
    for trade_row in transactions:
        if trade_row["player_id"] not in player_names:
            continue
        stock = stock_by_id.get(trade_row["stock_id"], {})
        recent_trades.append({
            "player_name": player_names.get(trade_row["player_id"], "알 수 없음"),
            "stock_name": stock.get("stock_name", "알 수 없음"),
            "side": trade_row["transaction_type"],
            "quantity": trade_row["quantity"],
            "price": _number(trade_row["price"]),
            "total_amount": _number(trade_row["total_amount"]),
            "created_at": trade_row.get("created_at"),
        })

    return jsonify({
        "game": {
            "game_id": game_id,
            "invite_code": game_data["invite_code"],
            "status": game_data["status"],
            "current_day": current_day,
            "game_days": game_data["game_days"],
            "remaining_seconds": _remaining_seconds(game_data),
        },
        "market": market,
        "rankings": rankings,
        "chart": list(chart.values()),
        "recent_trades": recent_trades,
    })


@app.route("/api/admin-presence")
def admin_presence():

    if not session.get("admin"):
        return jsonify({"error": "관리자 권한이 필요합니다."}), 403

    game_id = request.args.get("game_id", type=int)
    games_query = supabase.table("games").select("game_id, status").order("created_at", desc=True)
    if game_id:
        games_query = games_query.eq("game_id", game_id)
    game_result = games_query.execute()

    if not game_result.data:
        return jsonify({"error": "게임을 찾을 수 없습니다."}), 404

    current_game = game_result.data[0]
    players = (
        supabase
        .table("players")
        .select("player_id, player_name")
        .eq("game_id", current_game["game_id"])
        .execute()
    )
    return jsonify({
        "game_id": current_game["game_id"],
        "status": current_game["status"],
        "players": players.data,
    })


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "GET":
        return render_template("admin_login.html")

    password = request.form.get("password", "")

    if password != ADMIN_PASSWORD:
        return "관리자 비밀번호가 틀렸습니다."

    session["admin"] = True

    return redirect(url_for("admin"))

@app.route("/waiting")
def waiting():

    player_id = session.get("player_id")
    game_id = session.get("game_id")

    if not player_id or not game_id:
        return redirect(url_for("index"))

    game_result = supabase.table("games").select("*").eq("game_id", game_id).execute()
    player_result = supabase.table("players").select("*").eq("player_id", player_id).execute()
    players_result = supabase.table("players").select("player_name").eq("game_id", game_id).execute()

    if not game_result.data or not player_result.data:
        session.clear()
        return redirect(url_for("index"))

    return render_template(
        "waiting.html",
        game=game_result.data[0],
        player=player_result.data[0],
            tick_seconds=GAME_TICK_SECONDS,
        players=players_result.data
    )


@app.route("/join-game", methods=["POST"])
def join_game():

    game_id_value = request.form.get("game_id", "")
    player_name = request.form.get("player_name", "").strip()

    try:
        game_id = int(game_id_value)
    except (TypeError, ValueError):
        return "올바른 게임 정보가 아닙니다.", 400

    # 이름 입력 확인
    if not player_name:
        return "게임 이름을 입력해주세요."

    # 게임 확인
    result = (
        supabase
        .table("games")
        .select("*")
        .eq("game_id", game_id)
        .execute()
    )

    if not result.data:
        return "참가할 수 없는 게임입니다."

    game = result.data[0]
    status = game["status"]

    if status == "FINISHED":
        return "게임이 종료되었습니다. 관리자가 다시 시작할 때까지 참가할 수 없습니다.", 403

    existing_result = (
        supabase
        .table("players")
        .select("*")
        .eq("game_id", game["game_id"])
        .eq("player_name", player_name)
        .execute()
    )

    if status == "PLAYING":
        if not existing_result.data:
            return "게임이 시작된 뒤에는 기존 참가자만 다시 입장할 수 있습니다.", 403
        player = existing_result.data[0]
        session["player_id"] = player["player_id"]
        session["game_id"] = game["game_id"]
        return redirect(url_for("game"))

    if status != "OPEN":
        return "참가할 수 없는 게임입니다."

    if existing_result.data:
        player = existing_result.data[0]
        session["player_id"] = player["player_id"]
        session["game_id"] = game["game_id"]
        return redirect(url_for("waiting"))

    player_result = (
        supabase
        .table("players")
        .insert({
            "game_id": game["game_id"],
            "player_name": player_name,
            "cash": 1000000
        })
        .select()
        .execute()
    )

    if not player_result.data:
        return "참가자 등록에 실패했습니다."

    player = player_result.data[0]
    session["player_id"] = player["player_id"]
    session["game_id"] = game["game_id"]

    return redirect(url_for("waiting"))

if __name__ == "__main__":
    app.run(debug=True)