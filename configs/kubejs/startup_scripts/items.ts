// Listen to item registry event
StartupEvents.registry("item", (event) => {
  // The texture for this item has to be placed in kubejs/assets/kubejs/textures/item/test_item.png
  // If you want a custom item model, you can create one in Blockbench and put it in kubejs/assets/kubejs/models/item/test_item.json
  //   event.create('example_item')

  //   // If you want to specify a different texture location you can do that too, like this:
  //   event.create('test_item_1').texture('mobbo:item/lava') // This texture would be located at kubejs/assets/mobbo/textures/item/lava.png

  // You can chain builder methods as much as you like
  event
    .create("hardened_engine")
    .maxStackSize(8)
    .displayName("Hardened Engine")
    .tooltip("A more powerful engine required to make advanced aircraft.");
});
