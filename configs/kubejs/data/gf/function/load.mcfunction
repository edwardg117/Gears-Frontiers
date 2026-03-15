# Run init
function gf:func/init

# Schedule the player distance quest detector loop
schedule function gf:func/player_distance_quest_loop 60s
schedule function gf:func/su_test_quest_loop 5s


tellraw @a {"text":"Gears & Frontiers datapack loaded!","color":"green"}