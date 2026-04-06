/*
 * ServerEvents.recipes(callback) is a function that accepts another function,
 * called the "callback", as a parameter. The callback gets run when the
 * server is working on recipes, and then we can make our own changes.
 * When the callback runs, it is also known as the event "firing".
 */

// Listen for the "recipes" server event.
ServerEvents.recipes((event) => {
  // You can replace `event` with any name you like, as
  // long as you change it inside the callback too!

  // This part, inside the curly braces, is the callback.
  // You can modify as many recipes as you like in here,
  // without needing to use ServerEvents.recipes() again.

  console.log("Hello! The recipe event has fired!");

  // #region fix errors
  // Errors from teleporters
  //   event.remove({ output: "createteleporters:incomplete_q_mechanism" });
  //   event.recipes.createFilling("createteleporters:incomplete_q_mechanism", [
  //     "create:blaze_cake_base",
  //     Fluid.of("createteleporters:quantum_fluid", 250),
  //   ]);
  // #endregion

  // #region Create Recipes
  // Reinforced End Stone
  event.recipes.createCompacting("kubejs:reinforced_end_stone", [
    "minecraft:end_stone",
    "minecraft:netherite_ingot",
    Fluid.of("minecraft:lava", 100),
  ]);
  // Hardened Engine
  event.recipes.createMechanicalCrafting(
    "kubejs:hardened_engine",
    [
      //prettier-ignore
      " NNN ",
      "FEGES",
      "PBBB ",
    ],
    {
      B: {
        item: "create:brass_ingot",
      },
      E: {
        item: "kubejs:reinforced_end_stone",
      },
      G: {
        item: "create:rotation_speed_controller",
      },
      N: {
        item: "minecraft:netherite_ingot",
      },
      F: {
        item: "create:fluid_pipe",
      },
      P: {
        item: "create:mechanical_pump",
      },
      S: {
        item: "create:shaft",
      },
    },
  );

  // #region Immersive Aircraft
  // Remove recipes and replace with https://www.curseforge.com/minecraft/texture-packs/create-immersive-aircrafts-data-pack
  event.remove({ mod: "immersive_aircraft" });
  // event.remove({ output: "immersive_aircraft:biplane" });
  // event.remove({ output: "man_of_many_planes:economy_plane" });

  // Hull
  event.shaped(Item.of("immersive_aircraft:hull", 1), ["AIA", "AIA"], {
    A: {
      item: "create:andesite_casing",
    },
    I: {
      item: "minecraft:iron_ingot", // maybe "create:iron_sheet" instead?
    },
  });

  // Engine (Advanced Engine)
  event.shaped(Item.of("immersive_aircraft:engine", 1), ["BPB", "SES"], {
    B: {
      item: "create:brass_sheet",
    },
    P: {
      item: "create:precision_mechanism",
    },
    S: {
      item: "create:sturdy_sheet",
    },
    E: {
      item: "immersive_aircraft:boiler",
    },
  });

  // Sail (Large Sail)
  event.shaped(Item.of("immersive_aircraft:sail", 1), ["WWW", "WWW"], {
    W: {
      item: "create:white_sail",
    },
  });

  // Propeller (Large Propeller)
  event.shaped(
    Item.of("immersive_aircraft:propeller", 1),
    [" S ", "SPS", " S "],
    {
      S: {
        item: "create:iron_sheet",
      },
      P: {
        item: "create:propeller",
      },
    },
  );

  // Boiler (Basic Engine)
  event.shaped(Item.of("immersive_aircraft:boiler", 1), ["S", "F", "B"], {
    S: {
      item: "create:steam_engine",
    },
    F: {
      item: "create:fluid_tank",
    },
    B: {
      item: "create:blaze_burner",
    },
  });

  // Airship
  event.recipes.createMechanicalCrafting(
    "immersive_aircraft:airship",
    ["LLLLL", " R R ", " HSEP", " HHH "],
    {
      L: {
        item: "immersive_aircraft:sail",
      },
      R: {
        tag: "gf:rope",
      },
      H: {
        item: "immersive_aircraft:hull",
      },
      S: {
        tag: "create:seats",
      },
      E: {
        item: "immersive_aircraft:engine",
      },
      P: {
        item: "create:propeller",
      },
    },
  );

  // Cargo Airship
  event.shaped(Item.of("immersive_aircraft:cargo_airship", 1), ["CAC", "CHC"], {
    C: {
      item: "minecraft:chest",
    },
    A: {
      item: "immersive_aircraft:airship",
    },
    H: {
      item: "immersive_aircraft:hull",
    },
  });

  // Warship
  event.recipes.createMechanicalCrafting(
    "immersive_aircraft:warship",
    [" LLLLLL", "LLIIIEP", " RR RR ", "GSACHEP", "BHHHH  "],
    {
      L: {
        item: "immersive_aircraft:sail",
      },
      I: {
        item: "create:industrial_iron_block",
      },
      E: {
        item: "immersive_aircraft:engine",
      },
      P: {
        item: "immersive_aircraft:propeller",
      },
      R: {
        tag: "gf:rope",
      },
      G: {
        item: "create:industrial_iron_window",
      },
      S: {
        tag: "create:seats",
      },
      A: {
        item: "immersive_aircraft:cargo_airship",
      },
      C: {
        item: "immersive_aircraft:industrial_gears",
      },
      H: {
        item: "immersive_aircraft:hull_reinforcement",
      },
      B: {
        item: "immersive_aircraft:heavy_crossbow",
      },
    },
  );

  // Add biplane recipe using Create
  event.recipes.createMechanicalCrafting(
    "immersive_aircraft:biplane",
    [
      //prettier-ignore
      "   S ",
      "S  S ",
      "HHCEP",
      "S  S ",
      "   S ",
    ],
    {
      //   A: {
      //     item: "create:andesite_alloy",
      //   },
      P: {
        item: "immersive_aircraft:propeller",
      },
      S: {
        item: "immersive_aircraft:sail",
      },
      H: {
        item: "immersive_aircraft:hull",
      },
      C: {
        tag: "create:seats",
      },
      E: {
        item: "kubejs:hardened_engine",
      },
    },
  );

  // Gyrodyne
  event.shaped(
    Item.of("immersive_aircraft:gyrodyne", 1),
    [" P ", "SMS", "HCH"],
    {
      S: {
        item: "immersive_aircraft:sail",
      },
      H: {
        item: "immersive_aircraft:hull",
      },
      P: {
        item: "immersive_aircraft:propeller",
      },
      M: {
        item: "create:precision_mechanism",
      },
      C: {
        tag: "create:seats",
      },
    },
  );

  // Quadrocopter
  event.shaped(
    Item.of("immersive_aircraft:quadrocopter", 1),
    ["PHP", " S ", "PEP"],
    {
      P: {
        item: "create:propeller",
      },
      S: {
        item: "minecraft:string",
      },
      H: {
        item: "immersive_aircraft:hull",
      },
      E: {
        item: "immersive_aircraft:boiler",
      },
    },
  );

  // Copper Seaplane (Bamboo Hopper)
  event.recipes.createMechanicalCrafting(
    "immersive_aircraft:bamboo_hopper",
    [" C SC ", "SCICBG", " CPEAG", "SCICBG", " C SC "],
    {
      C: {
        item: "create:copper_casing",
      },
      S: {
        item: "immersive_aircraft:sail",
      },
      I: {
        item: "minecraft:copper_ingot",
      },
      B: {
        item: "immersive_aircraft:biplane",
      },
      G: {
        item: "create:industrial_iron_window",
      },
      P: {
        item: "immersive_aircraft:propeller",
      },
      E: {
        item: "immersive_aircraft:engine",
      },
      A: {
        tag: "create:seats",
      },
    },
  );

  // Rotary Cannon
  event.shaped(
    Item.of("immersive_aircraft:rotary_cannon", 1),
    ["D", "G", "C"],
    {
      D: {
        item: "minecraft:dispenser",
      },
      G: {
        item: "immersive_aircraft:industrial_gears",
      },
      C: {
        item: "minecraft:copper_ingot",
      },
    },
  );

  // Brass Propeller (Enhanced Propeller)
  event.shaped(
    Item.of("immersive_aircraft:enhanced_propeller", 1),
    [" B ", "BPB", " B "],
    {
      B: {
        item: "create:brass_sheet",
      },
      P: {
        item: "create:propeller",
      },
    },
  );

  // Water Engine (Eco Engine)
  event.shaped(Item.of("immersive_aircraft:eco_engine", 1), ["IWI", "CEC"], {
    I: {
      item: "create:iron_sheet",
    },
    W: {
      item: "minecraft:water_bucket",
    },
    C: {
      item: "create:copper_sheet",
    },
    E: {
      item: "immersive_aircraft:boiler",
    },
  });

  // Lava Engine (Nether Engine)
  event.shaped(Item.of("immersive_aircraft:nether_engine", 1), ["IWI", "CEC"], {
    I: {
      item: "create:iron_sheet",
    },
    W: {
      item: "minecraft:lava_bucket",
    },
    C: {
      item: "create:sturdy_sheet",
    },
    E: {
      item: "immersive_aircraft:boiler",
    },
  });

  // Iron Boiler (steel_boiler)
  event.shaped(Item.of("immersive_aircraft:steel_boiler", 1), ["IFI"], {
    I: {
      item: "create:iron_sheet",
    },
    F: {
      item: "create:fluid_tank",
    },
  });

  // Industrial Gears
  event.shaped(Item.of("immersive_aircraft:industrial_gears", 1), ["ICI"], {
    I: {
      item: "create:iron_sheet",
    },
    C: {
      item: "create:cogwheel",
    },
  });

  // Sturdy Pipes
  event.shaped(Item.of("immersive_aircraft:sturdy_pipes", 1), ["IPI"], {
    P: {
      item: "create:fluid_pipe",
    },
    I: {
      item: "create:iron_sheet",
    },
  });

  // Gyroscope
  event.shaped(Item.of("immersive_aircraft:gyroscope", 1), ["E", "C"], {
    E: {
      item: "create:electron_tube",
    },
    C: {
      item: "minecraft:compass",
    },
  });

  // Electronic Gyroscope
  event.shaped(
    Item.of("immersive_aircraft:gyroscope_hud", 1),
    ["NPN", "GLG", "BYS"],
    {
      N: {
        item: "minecraft:gold_nugget",
      },
      P: {
        item: "minecraft:glass_pane",
      },
      G: {
        item: "minecraft:gold_ingot",
      },
      L: {
        item: "minecraft:redstone_lamp",
      },
      B: {
        item: "minecraft:note_block",
      },
      Y: {
        item: "immersive_aircraft:gyroscope",
      },
      S: {
        item: "minecraft:lever",
      },
    },
  );

  // Advanced Gyroscope
  event.shaped(
    Item.of("immersive_aircraft:gyroscope_dials", 1),
    ["CCC", "NGL"],
    {
      C: {
        item: "minecraft:clock",
      },
      N: {
        item: "minecraft:note_block",
      },
      G: {
        item: "immersive_aircraft:gyroscope",
      },
      L: {
        item: "minecraft:lever",
      },
    },
  );

  // Reinforced Hull
  event.shaped(Item.of("immersive_aircraft:hull_reinforcement", 1), ["IHI"], {
    I: {
      item: "create:iron_sheet",
    },
    H: {
      item: "immersive_aircraft:hull",
    },
  });

  // Improved Landing gear
  event.shaped(
    Item.of("immersive_aircraft:improved_landing_gear", 1),
    ["SI", "B "],
    {
      S: {
        item: "create:iron_sheet",
      },
      I: {
        item: "minecraft:iron_ingot",
      },
      B: {
        item: "create:belt_connector",
      },
    },
  );

  // Economy Plane
  event.recipes.shaped(
    "man_of_many_planes:economy_plane",
    ["PHS", "GEH", "PHS"],
    {
      P: {
        item: "immersive_aircraft:propeller",
      },
      G: {
        item: "immersive_aircraft:industrial_gears",
      },
      H: {
        item: "immersive_aircraft:hull",
      },
      S: {
        item: "immersive_aircraft:sail",
      },
      E: {
        item: "kubejs:hardened_engine",
      },
    },
  );

  // #endregion

  // Make ancient debris renewable
  event.recipes.createCompacting("minecraft:gilded_blackstone", [
    "minecraft:blackstone",
    "minecraft:gold_ingot",
    "minecraft:gold_ingot",
  ]);

  event.recipes.createCompacting("minecraft:gilded_blackstone", [
    "minecraft:blackstone",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
    "minecraft:gold_nugget",
  ]);

  event.recipes
    .createMixing(
      [
        "minecraft:ancient_debris",
        "minecraft:ancient_debris",
        CreateItem.of("minecraft:ancient_debris", 0.005),
      ],
      [
        "minecraft:gilded_blackstone",
        "minecraft:gilded_blackstone",
        "minecraft:netherrack",
        "minecraft:netherrack",
        "minecraft:basalt",
        "minecraft:basalt",
        "minecraft:ancient_debris",
        "minecraft:ancient_debris",
        Fluid.of("minecraft:lava", 1000),
      ],
    )
    .superheated();

  // renewable elytra
  event.recipes
    .createMixing(
      ["minecraft:elytra", CreateItem.of("minecraft:elytra", 0.5)],
      [
        "minecraft:elytra",
        "minecraft:phantom_membrane",
        "minecraft:phantom_membrane",
        "minecraft:phantom_membrane",
        "minecraft:chorus_fruit",
      ],
    )
    .heated();

  // #region ChunkLoaders
  event.remove({ output: "chunkloaders:basic_chunk_loader" });
  event.remove({ output: "chunkloaders:advanced_chunk_loader" });
  event.remove({ output: "chunkloaders:ultimate_chunk_loader" });

  // New recipe for basic chunk loader
  event.recipes.createMechanicalCrafting(
    "chunkloaders:basic_chunk_loader",
    [
      //prettier-ignore
      "T" + "S" + "T",
      "S" + "C" + "S",
      "P" + "F" + "P",
    ],
    {
      //   A: {
      //     item: "create:andesite_alloy",
      //   },
      T: {
        item: "create:electron_tube",
      },
      S: {
        item: "create:sturdy_sheet",
      },
      P: {
        item: "create:precision_mechanism",
      },
      F: {
        item: "minecraft:soul_campfire",
      },
      C: {
        item: "create_power_loader:brass_chunk_loader",
      },
    },
  );
  // New recipe for advanced chunk loader
  event.recipes.createMechanicalCrafting(
    "chunkloaders:advanced_chunk_loader",
    [
      //prettier-ignore
      "E" + "B" + "E",
      "B" + "C" + "B",
      "E" + "B" + "E",
    ],
    {
      E: {
        item: "createaddition:electrum_sheet",
      },
      B: {
        item: "minecraft:blaze_powder",
      },
      C: {
        item: "chunkloaders:basic_chunk_loader",
      },
    },
  );
  // New recipe for ultimate chunk loader
  event.recipes.createMechanicalCrafting(
    "chunkloaders:ultimate_chunk_loader",
    [
      //prettier-ignore
      "D" + "R" + "D",
      "E" + "C" + "E",
      "D" + "R" + "D",
    ],
    {
      D: {
        item: "minecraft:diamond_block",
      },
      R: {
        item: "minecraft:redstone_block",
      },
      E: {
        item: "minecraft:end_rod",
      },
      C: {
        item: "chunkloaders:advanced_chunk_loader",
      },
    },
  );
  // #endregion

  // #region Pam's integration
  // Custom grinder recipe to use the mechanical grindstone
  // event.custom({
  //   type: "create_enchantment_industry:grinding",
  //   ingredients: [
  //     {
  //       tag: "c:flour_plants",
  //     },
  //   ],
  //   sound: "minecraft:block.grindstone.use",
  //   results: [
  //     {
  //       amount: 1,
  //       id: "pamhc2foodcore:flouritem",
  //     },
  //   ],
  // });
  // Prevent using auto generated shapless as it will consume the grinder/mixing bowl/skillet
  event.forEachRecipe(
    {
      type: "minecraft:crafting_shapeless",
      input: [
        "pamhc2foodcore:grinderitem",
        "pamhc2foodcore:mixingbowlitem",
        "pamhc2foodcore:skilletitem",
        "pamhc2foodcore:bakewareitem",
        "pamhc2foodcore:potitem",
        "pamhc2foodcore:rolleritem",
        "pamhc2foodcore:saucepanitem",
        "pamhc2foodcore:cuttingboarditem",
        "pamhc2foodcore:juiceritem",
      ],
    },
    (r) => {
      r.id(r.getOrCreateId() + "_manual_only");
    },
  );

  // Add recipes to heated mixer (skillet and bakeware)
  event.forEachRecipe(
    {
      type: "minecraft:crafting_shapeless",
      input: [
        "pamhc2foodcore:skilletitem",
        "pamhc2foodcore:bakewareitem",
        "pamhc2foodcore:potitem",
        "pamhc2foodcore:saucepanitem",
      ],
    },
    (r) => {
      // find and remove utensils from ingredients
      let newIngredients = [];
      for (let ingredient of r.originalRecipeIngredients) {
        let ids = ingredient.getItemIds();
        if (
          !ids.contains("pamhc2foodcore:skilletitem") &&
          !ids.contains("pamhc2foodcore:bakewareitem") &&
          !ids.contains("pamhc2foodcore:potitem") &&
          !ids.contains("pamhc2foodcore:saucepanitem") &&
          !ids.contains("minecraft:water_bucket")
        ) {
          newIngredients.push(ingredient);
        }
        // Replace water bcukets with water
        if (ids.contains("minecraft:water_bucket")) {
          newIngredients.push(Fluid.of("minecraft:water", 1000));
        }
      }

      event.recipes
        .createMixing(r.originalRecipeResult, newIngredients)
        .heated();
    },
  );

  // Add recipes to non-heated mixer
  event.forEachRecipe(
    {
      type: "minecraft:crafting_shapeless",
      input: [
        "pamhc2foodcore:mixingbowlitem",
        "pamhc2foodcore:cuttingboarditem",
        "pamhc2foodcore:juiceritem",
      ],
    },
    (r) => {
      // find and remove utensils from ingredients
      let newIngredients = [];
      for (let ingredient of r.originalRecipeIngredients) {
        let ids = ingredient.getItemIds();
        if (
          !ids.contains("pamhc2foodcore:mixingbowlitem") &&
          !ids.contains("pamhc2foodcore:cuttingboarditem") &&
          !ids.contains("pamhc2foodcore:juiceritem") &&
          !ids.contains("minecraft:water_bucket")
        ) {
          newIngredients.push(ingredient);
        }
        // Replace water bcukets with water
        if (ids.contains("minecraft:water_bucket")) {
          newIngredients.push(Fluid.of("minecraft:water", 1000));
        }
      }

      event.recipes.createMixing(r.originalRecipeResult, newIngredients);
    },
  );

  // Add grinder recipes to mechanical grindstone and compacting for multiple ingredients
  event.forEachRecipe(
    {
      type: "minecraft:crafting_shapeless",
      input: ["pamhc2foodcore:grinderitem"],
    },
    (r) => {
      let newIngredients = [];
      for (let ingredient of r.originalRecipeIngredients) {
        let ids = ingredient.getItemIds();
        if (
          !ids.contains("pamhc2foodcore:grinderitem") &&
          !ids.contains("minecraft:water_bucket")
        ) {
          newIngredients.push(ingredient);
        }
        // Replace water bcukets with water
        if (ids.contains("minecraft:water_bucket")) {
          newIngredients.push(Fluid.of("minecraft:water", 1000));
        }
      }
      // If only one ingredient, add to grindstone
      if (newIngredients.length == 1) {
        event.custom({
          type: "create_enchantment_industry:grinding",
          ingredients: newIngredients,
          sound: "minecraft:book_page_turn",
          results: [r.originalRecipeResult],
        });
        // If multiple ingredients, add to compacting table (for example, flour + salt)
      } else if (newIngredients.length > 1) {
        event.recipes.createCompacting(r.originalRecipeResult, newIngredients);
      }
    },
  );

  // Add recipes to cutting board (roller)
  event.forEachRecipe(
    {
      type: "minecraft:crafting_shapeless",
      input: ["pamhc2foodcore:rolleritem"],
    },
    (r) => {
      // find and remove skillet from ingredients
      let newIngredients = [];
      for (let ingredient of r.originalRecipeIngredients) {
        let ids = ingredient.getItemIds();
        if (!ids.contains("pamhc2foodcore:rolleritem")) {
          newIngredients.push(ingredient);
        }
      }

      // event.custom({
      //   type: 'farmersdelight:cutting',
      //   ingredients: newIngredients,
      //   tool: { item: 'pamhc2foodcore:rolleritem' },
      //   results: [r.originalRecipeResult]
      // })
      // if more than one ingredient, add to compacting table
      if (newIngredients.length > 1) {
        event.recipes.createCompacting(r.originalRecipeResult, newIngredients);
      } else if (newIngredients.length == 1) {
        // If only one ingredient, add to cutting board
        event.custom({
          type: "farmersdelight:cutting",
          ingredients: newIngredients,
          result: [
            {
              item: r.originalRecipeResult,
            },
          ],
          tool: {
            item: "pamhc2foodcore:rolleritem",
          },
        });
      }
    },
  );

  // Replace flour item with tag so all flour types are accepted
  event.replaceInput(
    { input: "pamhc2foodcore:flouritem" },
    "pamhc2foodcore:flouritem",
    "#gf:food_flour",
  );
  // Allow all doughs
  event.replaceInput(
    { input: "pamhc2foodcore:doughitem" },
    "pamhc2foodcore:doughitem",
    "#c:foods/dough",
  );

  // #endregion

  // #endregion

  // #region Vanilla
  // Craft saddle using the vanilla recipe from the Mounts of Mayhem update
  event.shaped(
    Item.of("minecraft:saddle", 1), // arg 1: output
    [
      " L ",
      "LIL", // arg 2: the shape (array of strings)
    ],
    {
      L: "minecraft:leather",
      I: "minecraft:iron_ingot", //arg 3: the mapping object
    },
  );
  // #endregion
});
