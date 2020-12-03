# ##### BEGIN GPL LICENSE BLOCK #####
#
#  Isolate Collection Layers = Toggle Collection Layer Isolation
#  Copyright (C) 2020  Marcel Toele
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Isolate Collection Layers",
    "author": "Marcel Toele",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D",
    "description": "Toggle Collection Layer Isolation",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
}

import bpy

############# Generic Python Utility Functions ##############

def flatten(l):
    """Flatten arbitrarily nested list"""
    def flatten_(arr):
        for i in arr:
            if isinstance(i, list):
                yield from flatten_(i)
            else:
                yield i

    return list(flatten_(l))

############ Generic Blender Utility Functions #############

def as_list(node):
#    print("traversing %s" % node.name)
    head = []
    if node.name != "Master Collection":
        head = [node]
    return head + flatten([as_list(c) for c in node.children])

# @TODO
def ancestors(node):
    return []

def is_part_of_isolation_layer(collection, layer_id):
    if collection.get("isolation_layer", 0) == layer_id:
        return True
    else:
        for c in collection.children:
            if is_part_of_isolation_layer(c, layer_id):
                return True
    
    return False
    

def is_isolation_mode_on(context, layer_id):
    layer_collections = as_list(context.view_layer.layer_collection)
    some_collections_are_hidden = False
    all_collections_in_isolation_layer_are_fully_visible = True
    for lc in layer_collections:
        if lc.hide_viewport:
            some_collections_are_hidden = True

        collection =  bpy.data.collections[lc.name]
        if collection.get("isolation_layer", 0) == layer_id:
            all_collections_in_isolation_layer_are_fully_visible = (
                all_collections_in_isolation_layer_are_fully_visible and
                not lc.hide_viewport and
                len([c for c in as_list(lc) if c.hide_viewport]) == 0
            )

    return some_collections_are_hidden and all_collections_in_isolation_layer_are_fully_visible

def isolate_collection_layer(context, layer_id):
#    print("isolate collection layer: %d" % layer_id)
    should_isolate = not is_isolation_mode_on(context, layer_id)
    layer_collections = as_list(context.view_layer.layer_collection)
    if should_isolate:
        collections_in_layer = [c for c in bpy.data.collections if c.get("isolation_layer", 0) in [layer_id, -1]]
        visible_collections =  flatten([as_list(c) for c in collections_in_layer]) + flatten([ancestors(c) for c in collections_in_layer])
        for lc in layer_collections:
            collection =  bpy.data.collections[lc.name]
            lc.hide_viewport = not collection in visible_collections
    else:
        for lc in layer_collections:
            lc.hide_viewport = False

    # Old code:
    # for lc in layer_collections:
    #     collection =  bpy.data.collections[lc.name]
    #     if should_isolate:
    #         lc.hide_viewport = not is_part_of_isolation_layer(collection, layer_id)
    #     else:
    #         lc.hide_viewport = False

# PRO MEMORI
#C.scene.view_layers[0].layer_collection.children[0].hide_viewport = Fals
#context.view_layer.active_layer_collection = context.view_layer.layer_collection.children[-1]

############# Blender Extension Classes ##############

class IsolateCollectionsPanel(bpy.types.Panel):
    """Creates the Isolate-Collections Panel in the Object properties window"""
    bl_label = "Isolate Collections"
    bl_idname = "OBJECT_PT_ISOCOL"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        active_collection_name = bpy.context.view_layer.active_layer_collection.name
        if active_collection_name != "Master Collection":
            active_collection = bpy.data.collections[active_collection_name]
            row.prop(active_collection, "isolation_layer")

def IsolateCollectionLayerOperator(layer_id):
    class IsolateCollectionLayerOperator_(bpy.types.Operator):
        """Isolate Collection Layer"""
        bl_idname = "collection.isolate_collection_layer_%d" % layer_id
        bl_label = "Isolate Collection Layer %d Operator" % layer_id

        def execute(self, context):
            isolate_collection_layer(context, layer_id)
            return {'FINISHED'}

    return IsolateCollectionLayerOperator_

operators = [IsolateCollectionLayerOperator(layer_num) for layer_num in range(1, 10)]

# store keymaps here to access after registration
addon_keys = []

############# Register/Unregister Hooks ##############

def register():
    bpy.utils.register_class(IsolateCollectionsPanel)
    for operator in operators:
        bpy.utils.register_class(operator)

    bpy.types.Collection.isolation_layer = bpy.props.IntProperty(name="isolation layer", min=-1, max=9, default=0)

    # register global keys in keymap
    wm = bpy.context.window_manager
    active_keyconfig = wm.keyconfigs.active
    addon_keyconfig = wm.keyconfigs.addon

    kc = addon_keyconfig
    if not kc:
        print('no keyconfig path found, skipped (we must be in batch mode)')
        return

    km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
    for operator, key_name in zip(operators, ('ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE')):
        kmi = km.keymap_items.new(operator.bl_idname, key_name, 'PRESS', ctrl=False, shift=False)
        addon_keys.append((km, kmi))

def unregister():
    bpy.utils.unregister_class(IsolateCollectionsPanel)
    for operator in operators:
        bpy.utils.unregister_class(operator)

    del bpy.types.Collection.isolation_layer

    # remove the keys from the keymap
    for km, kmi in addon_keys:
        km.keymap_items.remove(kmi)

    addon_keys.clear()


if __name__ == "__main__":
    register()
