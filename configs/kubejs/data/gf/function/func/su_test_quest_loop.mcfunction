execute as @a at @s store result score @s gf.SU_TEST run data get block ~ ~ ~ Network.Capacity 1
execute as @a[scores={gf.SU_TEST=4194304..}] run ftbquests change_progress @s complete 79C19D9BB073FB20

schedule function gf:func/su_test_quest_loop 5s