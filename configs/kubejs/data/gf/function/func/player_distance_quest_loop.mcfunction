# Execute as all players that are within 16 blocks of another player
execute as @a at @s if entity @p[distance=0.1..16] run function gf:func/player_distance_quest_complete
# Only perform this check once per minute
schedule function gf:func/player_distance_quest_loop 60s