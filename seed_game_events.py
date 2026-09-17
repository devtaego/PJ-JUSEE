"""Seed a fresh, randomized event deck for one game.

The news is fictional game content inspired by broad economic themes.
Run with: python seed_game_events.py <game_id>
"""

import random
import sys


NORMAL_EVENTS = [
    ("수출 주문 회복 조짐", "주요 제조업체의 해외 주문이 완만하게 회복되고 있습니다.", "반도체 부품 주문이 예상보다 빠르게 늘고 있습니다.", "HBE01", 1.8),
    ("친환경 이동수단 지원 검토", "친환경 이동수단 보급을 위한 지원 정책이 논의되고 있습니다.", "관련 부품 공급 계약이 함께 검토되고 있습니다.", "MTW02", 2.1),
    ("온라인 소비 흐름 안정", "소비 심리가 급격히 악화되지는 않았다는 조사 결과가 나왔습니다.", "플랫폼 광고 매출이 예상치를 조금 웃돌았습니다.", "PXM04", 1.4),
    ("클라우드 투자 확대", "기업들의 데이터 인프라 투자가 점진적으로 늘고 있습니다.", "대형 고객의 서비스 전환 일정이 앞당겨질 수 있습니다.", "NTF03", 2.4),
    ("배터리 원료 가격 안정", "배터리 원료 가격이 안정되며 비용 부담이 줄어들 전망입니다.", "신규 장기 공급 계약이 발표될 가능성이 있습니다.", "ENZ06", 2.7),
    ("메모리 수요 보합", "메모리 제품 수요가 큰 변화 없이 유지되고 있습니다.", "일부 고객의 재고가 예상보다 빠르게 줄고 있습니다.", "MMO05", 1.2),
    ("금융권 디지털 서비스 확대", "금융권의 디지털 서비스 투자가 이어지고 있습니다.", "비대면 고객 증가율이 시장 전망을 웃돌았습니다.", "SBF07", 1.6),
    ("제조업 재고 조정 시작", "업계가 재고를 조정하면서 단기적인 가격 부담이 예상됩니다.", "일부 주문 일정이 다음 분기로 미뤄졌습니다.", "HBE01", -2.6),
]

BIG_EVENTS = [
    ("글로벌 금융시장 급락", "해외 금융시장의 급락이 국내 시장에도 빠르게 전파되고 있습니다.", "기관의 위험자산 축소 주문이 이어질 가능성이 있습니다.", "SBF07", -18.0),
    ("전기 이동수단 공급망 충격", "핵심 부품 공급 차질로 생산 일정이 다시 조정될 수 있습니다.", "대체 공급선 확보가 예상보다 늦어지고 있습니다.", "MTW02", -24.0),
    ("플랫폼 규제 강화안 발표", "대형 플랫폼의 수수료와 광고 정책을 둘러싼 규제안이 공개됐습니다.", "시장 예상보다 적용 범위가 넓을 수 있습니다.", "PXM04", -28.0),
    ("AI 수요 폭발과 공급 부족", "AI 서버 투자가 급증하면서 관련 부품 공급 부족 우려가 커졌습니다.", "대형 고객의 추가 주문이 곧 발표될 수 있습니다.", "NTF03", 32.0),
    ("배터리 화재 안전 기준 강화", "배터리 안전 기준이 크게 강화될 수 있다는 소식이 전해졌습니다.", "업계 일부 생산라인의 인증 일정이 지연될 수 있습니다.", "ENZ06", -22.0),
    ("메모리 가격 급반등", "서버용 메모리 수요가 한꺼번에 몰리며 가격 전망이 바뀌었습니다.", "대형 고객의 선구매가 이미 시작됐다는 관측이 있습니다.", "MMO05", 30.0),
    ("긴급 소비 부양책 발표", "내수 소비를 살리기 위한 대규모 정책 패키지가 발표됐습니다.", "금융과 플랫폼 분야에 추가 지원이 집중될 수 있습니다.", "SBF07", 18.0),
    ("시장 반등과 차익 실현", "급락 이후 시장이 반등했지만 투자자들의 차익 실현도 나타났습니다.", "장 초반 반등 뒤 변동성이 다시 커질 수 있습니다.", "HBE01", 16.0),
    ("원자재 운송망 일시 중단", "주요 운송 경로의 차질로 원자재 조달 불확실성이 커졌습니다.", "대체 운송 비용이 예상보다 높아질 수 있습니다.", "MTW02", -20.0),
    ("신규 디지털 금융 규칙 도입", "새로운 디지털 금융 규칙이 예상보다 빠르게 시행됩니다.", "선도 사업자에게는 시장 재편 기회가 될 수 있습니다.", "SBF07", 23.0),
]


def make_event(game_id, template, market_day, stock_ids, normal_days):
    title, content, private_content, ticker, impact_rate = template
    return {
        "game_id": game_id,
        "market_day": market_day,
        "event_type": "NORMAL" if market_day <= normal_days else "BIG",
        "title": title,
        "content": content,
        "private_content": private_content,
        "info_price": 10000 if market_day <= normal_days else 30000,
        "impact_stock_id": stock_ids[ticker],
        "impact_rate": impact_rate,
    }


def shuffled_schedule(candidates, count, randomizer):
    schedule = []
    while len(schedule) < count:
        batch = list(candidates)
        randomizer.shuffle(batch)
        if schedule and len(batch) > 1 and batch[0][0] == schedule[-1][0]:
            batch[0], batch[1] = batch[1], batch[0]
        schedule.extend(batch)
    return schedule[:count]


def seed_events_for_game(game_id, supabase):
    game_result = supabase.table("games").select("game_id, game_days").eq("game_id", game_id).execute()
    if not game_result.data:
        raise RuntimeError(f"game_id={game_id} 게임을 찾을 수 없습니다.")

    game_days = min(int(game_result.data[0]["game_days"]), 30)
    stocks = supabase.table("stocks").select("stock_id, ticker").execute().data
    stock_ids = {stock["ticker"]: stock["stock_id"] for stock in stocks}

    if any(ticker not in stock_ids for event in NORMAL_EVENTS + BIG_EVENTS for ticker in [event[3]]):
        raise RuntimeError("종목 데이터가 부족합니다. 먼저 종목을 생성해주세요.")

    supabase.table("game_events").delete().eq("game_id", game_id).execute()
    randomizer = random.SystemRandom()
    rows = []
    normal_days = (game_days + 1) // 2

    normal_schedule = shuffled_schedule(NORMAL_EVENTS, normal_days, randomizer)
    big_schedule = shuffled_schedule(BIG_EVENTS, max(0, game_days - normal_days), randomizer)
    for market_day in range(1, game_days + 1):
        template = normal_schedule[market_day - 1] if market_day <= normal_days else big_schedule[market_day - normal_days - 1]
        rows.append(make_event(game_id, template, market_day, stock_ids, normal_days))

    if rows:
        supabase.table("game_events").insert(rows).execute()

    return len(rows)


if __name__ == "__main__":
    from app import supabase

    game_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    count = seed_events_for_game(game_id, supabase)
    print(f"game_id={game_id}: {count}개 이벤트를 새 조합으로 입력 완료")
