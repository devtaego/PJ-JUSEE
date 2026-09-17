"""Delete all simulator data and create a clean starter game."""

from app import supabase
from game_reset import reset_and_create_game


game = reset_and_create_game(supabase)
print(f"created starter game: game_id={game['game_id']}, invite_code={game['invite_code']}")
