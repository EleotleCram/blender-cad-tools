# ##### BEGIN GPL LICENSE BLOCK #####
#
#  ObRef Toggle Hide - Toggle visibility of referenced modifier objects
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

import bpy


bl_info = {
    "name": "ObRef Toggle Hide",
    "author": "Marcel Toele",
    "version": (1, 0, 1),
    "blender": (2, 80, 0),
    "location": "View3D",
    "description": "Toggle visibility of referenced modifier objects",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
}


############# Blender Extension Classes ##############


class ORTH_OT_ToggleHide(bpy.types.Operator):
    bl_idname = "orth.toggle_hide"
    bl_label = "(un)Hide Modifier Objects"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = """Toggles the visibility
of all the referenced modifier objects
"""

    @classmethod
    def poll(cls, context):
        if hasattr(context, 'selected_objects'):
            selected = context.selected_objects
            if all(obj.type == "MESH" for obj in selected):
                return True

        return False

    def execute(self, context):
        selected = context.selected_objects
        all_modifiers_of_selected_objects = [m for obj in selected for m in obj.modifiers]
        all_boolean_modifiers = [m for m in all_modifiers_of_selected_objects if m.type == 'BOOLEAN']

        space_data = context.space_data
        from_local_view = space_data.local_view is not None

        # By default we assume booleans were hidden, so this operator will unhide them.
        is_hidden = True

        if len(all_boolean_modifiers) >= 1:
            is_hidden = all_boolean_modifiers[0].object.hide_get() or all_boolean_modifiers[0].object.hide_viewport

        # Toggle the current state.
        should_be_hidden = not is_hidden

        for modifier in all_boolean_modifiers:
            if modifier.show_viewport:
                modifier.object.hide_set(should_be_hidden)
                modifier.object.hide_viewport = should_be_hidden

                if from_local_view:
                    modifier.object.local_view_set(space_data, not should_be_hidden)

        return {'FINISHED'}


class ORTH_PT_BoolToggleHide(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_label = "Toggle Hide"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0 and context.object.mode != 'EDIT'

    def draw(self, context):
        layout = self.layout

        layout.operator('orth.toggle_hide')


classes = [
    ORTH_OT_ToggleHide,
    ORTH_PT_BoolToggleHide,
]


############# Register/Unregister Hooks ##############


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
