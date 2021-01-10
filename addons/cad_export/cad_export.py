# ##### BEGIN GPL LICENSE BLOCK #####
#
#  CAD Export - Enhanced exporter for CAD designs
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

# from bpy.types import Operator
# from bpy.props import StringProperty, BoolProperty, EnumProperty
# from bpy_extras.io_utils import ExportHelper
import bpy
import bpy_extras


bl_info = {
    "name": "CAD Export",
    "author": "Marcel Toele",
    "version": (1, 0, 2),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "Enhanced exporter for CAD designs",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}


############# Blender Extension Classes ##############


def toggle_supports(supports_to_enable, show_viewport):
    for ob_name, mod_names in supports_to_enable:
        ob = bpy.data.objects[ob_name]
        mods = [ob.modifiers[mod_name] for mod_name in mod_names]

        for mod in mods:
            mod.show_viewport = show_viewport


def obs_bed_orientation_apply(obs):
    obs_with_custom_bed_orientation = [ob for ob in obs if next(
        (c for c in ob.constraints if c.name == "Bed Orientation"), None)]
    saved_matrices = [(ob.name, ob.matrix_world.copy()) for ob in obs_with_custom_bed_orientation]
    for ob in obs_with_custom_bed_orientation:
        ob.matrix_world = ob.matrix_world @ ob.constraints['Bed Orientation'].target.matrix_world.normalized().inverted()

    return saved_matrices


def obs_orig_orientation_restore(saved_matrices):
    for ob_name, ob_matrix_world_orig in saved_matrices:
        bpy.data.objects[ob_name].matrix_world = ob_matrix_world_orig


# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
# pylint: disable=undefined-variable
class CADEX_OT_ExportSTL(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """Blender Operator class that exports STL files (optimized for CAD designs)"""
    bl_idname = "cad_export.stl"
    bl_label = "CAD Export STL (.stl)"

    # ExportHelper mixin class uses this
    filename_ext = ".stl"

    def execute(self, context):
        supports_to_enable = [(ob.name, [mod.name for mod in ob.modifiers if mod.name.startswith(
            "Supports") and not mod.show_viewport]) for ob in context.selected_objects]

        toggle_supports(supports_to_enable, True)

        saved_matrices = obs_bed_orientation_apply(context.selected_objects)

        bpy.ops.export_mesh.stl(use_selection=True, filepath=self.filepath)

        obs_orig_orientation_restore(saved_matrices)

        toggle_supports(supports_to_enable, False)

        return {'FINISHED'}


classes = [
    CADEX_OT_ExportSTL,


]


############# Register/Unregister Hooks ##############


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(CADEX_OT_ExportSTL.bl_idname, text="CAD Export STL (.stl)")


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
