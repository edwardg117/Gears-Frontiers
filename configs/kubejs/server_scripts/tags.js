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
  //@pam'sharvestcraft - food
    event.add("pamhc2foodcore:food", "/pamhc2foodcore:.*/");
    // Remove coocking utensils
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:bakewareitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:cuttingboarditem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:juiceritem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:grinderitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:mixingbowlitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:potitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:rolleritem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:saucepanitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:skilletitem");
    // remove recipe bases
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:flouritem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:doughitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:saltitem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:freshwateritem");
    event.remove("pamhc2foodcore:food", "pamhc2foodcore:freshmilkitem");

    // Add Pam's food to Create's food tags
    event.add("c:food", "#pamhc2foodcore:food");

    // let ids = event.get("pamhc2foodcore:food").getObjectIds();
    // console.log("pamhc2foodcore:food items:");
    // console.log(ids);
    // ids.forEach((id) => {
    //     console.log(id);
    // });

    // Seeds
    event.add("c:seeds", "pamhc2foodcore:sunflowerseedsitem");
    event.add("c:seeds", "northstar:dormant_martian_seed");
    event.add("c:seeds", "northstar:mars_tulip_seeds");
    event.add("c:seeds", "northstar:mars_palm_seeds");
    event.add("c:seeds", "northstar:mars_sprout_seeds");
    event.add("c:seeds", "alcocraftplus:hop_seeds");
    event.add("c:seeds", "alcocraftplus:dry_seeds");

    // let seeds = event.get("c:seeds").getObjectIds();
    // console.log("c:seeds items:");
    // console.log(seeds);
    // seeds.forEach((id) => {
    //     console.log(id);
    // });

    console.log("This is a console log");

  //@pams food extended
  event.add("pamhc2foodextended:food", "/pamhc2foodextended:.*/");
  event.add("c:food", "#pamhc2foodextended:food");
  // let extednedFoods = event.get("pamhc2foodextended:food").getObjectIds();
    // console.log("pamhc2foodextended:food items:");
    // console.log(extednedFoods);
    // extednedFoods.forEach((id) => {
    //     console.log(id);
    // });
  // event.add("gf:engineersshaders", "/.*shader.*/");
  // let shaders = event.get("gf:engineersshaders").getObjectIds();
  // console.log("Shader items:");
  // console.log(shaders);
  // shaders.forEach((id) => {
  //       console.log(id);
  //   });

  event.add("gf:rope", ["comforts:rope_and_nail", "farmersdelight:rope", "immersiveengineering:wirecoil_structure_rope"]);
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