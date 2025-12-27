StartupEvents.registry("block", (event) => {
    event.create("reinforced_end_stone")
      .hardness(1.5)
      .displayName("Reinforced Endstone")
      // @ts-ignore
      .resistance(2400) // Set resistance (to explosions, etc)
      .fullBlock(true)
      .soundType("metal")
    // .tagBlock('my_custom_tag') // Tag the block with `#minecraft:my_custom_tag` (can have multiple tags)
    .requiresTool(true) // Requires a tool or it won't drop (see tags below)
    // .tagBlock('my_namespace:my_other_tag') // Tag the block with `#my_namespace:my_other_tag`
    // .tagBlock('minecraft:mineable/axe') //can be mined faster with an axe
    .tagBlock('minecraft:mineable/pickaxe') // or a pickaxe
    .tagBlock('minecraft:needs_diamond_tool') // the tool tier must be at least iron;
  });
