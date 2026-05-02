// Stolen from ChosenArchitect https://www.curseforge.com/minecraft/modpacks/chosens-create-integrated
BlockEvents.rightClicked(event => {
    const { block, item } = event
    
    if (block.id.startsWith('createenchantablemachinery:')) {
        if (item.hasTag('c:stones') || 
            item.hasTag('minecraft:stone_tool_materials') || 
            item.id === 'minecraft:stone') {
            
            event.cancel()
            return 
        }
    }

    const targetMachines = [
        'createenchantablemachinery:enchantable_mechanical_press',
        'createenchantablemachinery:enchantable_mechanical_mixer'
    ]

    if (targetMachines.includes(block.id)) {
        if (item.hasTag('create:casing')) {

            event.cancel()
        }
    }
})