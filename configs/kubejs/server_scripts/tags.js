ServerEvents.tags("item", (event) => {
  // Register the hazmat suits from Create Nuclear as as hazmat suits for Create New Age
  event.add("create_new_age:hazmat_suit", "#createnuclear:all_anti_radiation_armors");

  // Flour
  event.add("gf:food_flour", ["pamhc2foodcore:flouritem", "create:wheat_flour"]);
  // Salt
  event.add("c:salt", ["northstar:salt"]);
  //  Water
  event.add("c:water", ["minecolonies:large_water_bottle"]);
  // Cheese
  event.add("c:cheese", ["minecolonies:cheddar_cheese", "minecolonies:feta_cheese"]);

  // Pork concatenation
  event.add("c:rawpork", "#c:foods/raw_pork");
  // event.add("c:raw_pork", "#c:rawpork");
  // Beef concatenation
  event.add("c:rawbeef", "#c:foods/raw_beef");
  // event.add("c:raw_beef", "#c:rawbeef");
  // testing change
});

// Block tags
ServerEvents.tags("block", (event) => {
  // Remove fences from being turned into diagonal fences
  event.add("diagonalfences:non_diagonal_fences",["mcwfences:deepslate_brick_grass_topped_wall",
        "mcwfences:stone_grass_topped_wall",
        "mcwfences:andesite_grass_topped_wall",
        "mcwfences:diorite_grass_topped_wall",
        "mcwfences:granite_grass_topped_wall",
        "mcwfences:sandstone_grass_topped_wall",
        "mcwfences:red_sandstone_grass_topped_wall",
        "mcwfences:blackstone_grass_topped_wall",
        "mcwfences:nether_brick_grass_topped_wall",
        "mcwfences:end_brick_grass_topped_wall",
        "mcwfences:deepslate_grass_topped_wall",
        "mcwfences:quartz_grass_topped_wall",
        "mcwfences:mud_brick_grass_topped_wall",
        "mcwfences:prismarine_grass_topped_wall",
        "mcwfences:oak_wired_fence",
        "mcwfences:spruce_wired_fence",
        "mcwfences:birch_wired_fence",
        "mcwfences:jungle_wired_fence",
        "mcwfences:acacia_wired_fence",
        "mcwfences:dark_oak_wired_fence",
        "mcwfences:crimson_wired_fence",
        "mcwfences:warped_wired_fence",
        "mcwfences:bamboo_wired_fence"]);

  // Prevent pickup by carryon
  event.add("c:relocation_not_supported", ["sophisticatedbackpacks:backpack",]);
});

// Entity
ServerEvents.tags("entity_type", (event) => {
    // Remove AstikorCarts from being picked up by carryon
    event.add("c:capturing_not_supported", ["astikorcartsredux:plow",
        "astikorcartsredux:supply_cart",
        "astikorcartsredux:hand_cart",
        "astikorcartsredux:reaper",
        "astikorcartsredux:animal_cart",
        "astikorcartsredux:seed_drill",
        "minecraft:horse"]);
});