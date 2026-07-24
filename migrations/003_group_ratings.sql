ALTER TABLE game_results
ADD COLUMN IF NOT EXISTS chat_id BIGINT;

ALTER TABLE game_results
ADD COLUMN IF NOT EXISTS rating_delta INTEGER;

UPDATE game_results
SET rating_delta = CASE
    WHEN is_draw THEN 5
    WHEN mode = 'classic' AND rank = 1 THEN 25
    WHEN mode = 'classic' THEN -10
    WHEN mode = 'battle' AND rank = 1 THEN 30
    WHEN mode = 'battle' AND rank = 2 THEN 10
    ELSE -10
END
WHERE rating_delta IS NULL;

UPDATE game_results AS result
SET chat_id = (session.payload ->> 'group_id')::BIGINT
FROM game_sessions AS session
WHERE session.game_id = result.game_id
  AND result.chat_id IS NULL
  AND COALESCE((session.payload ->> 'is_private')::BOOLEAN, FALSE) = FALSE
  AND COALESCE((session.payload ->> 'is_inline')::BOOLEAN, FALSE) = FALSE
  AND session.payload ->> 'group_id' IS NOT NULL;

ALTER TABLE game_results
ALTER COLUMN rating_delta SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_game_results_chat_rating
ON game_results(chat_id, user_id)
WHERE chat_id IS NOT NULL;
