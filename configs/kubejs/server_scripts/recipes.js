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
  // Remove the biplane recipe so it can bre replaced.
  event.remove({ output: "immersive_aircraft:biplane" });
  event.remove({ output: "man_of_many_planes:economy_plane" });

  // Add biplane recipe using Create
  event.recipes.createMechanicalCrafting(
    "immersive_aircraft:biplane",
    [
      //prettier-ignore
      " " + " " + "H" + " " + " " + "P",
      " " + " " + " " + "H" + "E" + " ",
      " " + " " + "A" + "S" + "H" + " ",
      "H" + " " + "A" + "A" + " " + "H",
      " " + "H" + " " + " " + " " + " ",
      " " + " " + "H" + " " + " " + " ",
    ],
    {
      //   A: {
      //     item: "create:andesite_alloy",
      //   },
      P: {
        item: "immersive_aircraft:propeller",
      },
      A: {
        item: "create:andesite_casing",
      },
      H: {
        item: "immersive_aircraft:hull",
      },
      S: {
        tag: "create:seats",
      },
      E: {
        item: "kubejs:hardened_engine",
      },
    },
  );

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
          !ids.contains("pamhc2foodcore:saucepanitem")
        ) {
          newIngredients.push(ingredient);
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
      input: ["pamhc2foodcore:mixingbowlitem"],
    },
    (r) => {
      // find and remove utensils from ingredients
      let newIngredients = [];
      for (let ingredient of r.originalRecipeIngredients) {
        let ids = ingredient.getItemIds();
        if (!ids.contains("pamhc2foodcore:mixingbowlitem")) {
          newIngredients.push(ingredient);
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
        if (!ids.contains("pamhc2foodcore:grinderitem")) {
          newIngredients.push(ingredient);
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
  // Fix water items being used instead of fluid
  // TODO FIXME
  event.replaceInput(
    { input: "#c:water", type: "create:mixing" },
    "#c:water",
    "minecraft:water",
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
