-- 관리자 게임 생성에서 1분, 2분, 5분, 하루 주기를 사용할 수 있게 합니다.
-- Supabase SQL Editor에서 한 번 실행하세요.

ALTER TABLE public.games
    DROP CONSTRAINT IF EXISTS games_reset_minutes_check;

ALTER TABLE public.games
    ADD CONSTRAINT games_reset_minutes_check
    CHECK (reset_minutes = ANY (ARRAY[1, 2, 5, 1440]));