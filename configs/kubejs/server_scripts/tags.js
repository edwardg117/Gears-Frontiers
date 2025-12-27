ServerEvents.tags("item", (event) => {
  // Remove AstikorCarts from being picked up by carryon
  event.add("c:capturing_not_supported", "astikorcartsredux:plow");
  event.add("c:capturing_not_supported", "astikorcartsredux:supply_cart");
  event.add("c:capturing_not_supported", "astikorcartsredux:hand_cart");
  event.add("c:capturing_not_supported", "astikorcartsredux:reaper");
  event.add("c:capturing_not_supported", "astikorcartsredux:animal_cart");
  event.add("c:capturing_not_supported", "astikorcartsredux:seed_drill");

  // Remove fences from being turned into diagonal fences
  event.add("non_diagonal_fences", "mcwfences:deepslate_brick_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:stone_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:andesite_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:diorite_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:granite_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:sandstone_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:red_sandstone_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:blackstone_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:nether_brick_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:end_brick_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:deepslate_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:quartz_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:mud_brick_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:prismarine_grass_topped_wall");
  event.add("non_diagonal_fences", "mcwfences:oak_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:spruce_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:birch_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:jungle_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:acacia_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:dark_oak_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:crimson_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:warped_wired_fence");
  event.add("non_diagonal_fences", "mcwfences:bamboo_wired_fence");

  // Register the hazmat suits from Create Nuclear as as hazmat suits for Create New Age
  event.add("create_new_age:hazmat_suit", "#createnuclear:all_anti_radiation_armors");

});
