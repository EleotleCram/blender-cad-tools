# ##### BEGIN GPL LICENSE BLOCK #####
#
#  CAD Mesh Dimensions - Quickly view and edit dimensions of selected elements in a mesh
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

from bpy.app.handlers import persistent
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, PointerProperty
from bpy.utils import register_class, unregister_class
from bpy.types import Panel, Operator, PropertyGroup, Scene
import bmesh
import bpy


bl_info = {
    "name": "CAD Mesh Dimensions",
    "author": "Marcel Toele",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D",
    "description": "Quickly view and edit dimensions of selected elements in a mesh",
    "category": "3D View"
}


############# Generic Python Utility Functions ##############

def safe_divide(a, b):
    if b != 0:
        return a / b
    return 1

############ Generic Blender Utility Functions #############


def calc_bounds_verts(selected_verts):
    matrix_world = bpy.context.object.matrix_world
    v_coords = list(map(lambda v: Vector(matrix_world @ v.co), selected_verts))

    # @TODO What to do with this?
    # bme.verts.ensure_lookup_table()

    if len(v_coords) > 0:
        # [+x, -x, +y, -y, +z, -z]
        v_co = v_coords[0]
        bounds = {0: v_co.x, 1: v_co.x, 2: v_co.y, 3: v_co.y, 4: v_co.z, 5: v_co.z}

        for v_co in v_coords:
            if bounds[0] < v_co.x:
                bounds[0] = v_co.x
            if bounds[1] > v_co.x:
                bounds[1] = v_co.x
            if bounds[2] < v_co.y:
                bounds[2] = v_co.y
            if bounds[3] > v_co.y:
                bounds[3] = v_co.y
            if bounds[4] < v_co.z:
                bounds[4] = v_co.z
            if bounds[5] > v_co.z:
                bounds[5] = v_co.z
    else:
        bounds = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    bounds["x"] = bounds[0] - bounds[1]
    bounds["y"] = bounds[2] - bounds[3]
    bounds["z"] = bounds[4] - bounds[5]

    return bounds


def calc_bounds():
    """Calculates the bounding box for selected vertices. Requires applied scale to work correctly. """
    # for some reason we must change into object mode for the calculations
    mode = bpy.context.object.mode
    bpy.ops.object.mode_set(mode='OBJECT')

    mesh = bpy.context.object.data

    bme = bmesh.new()
    bme.from_mesh(mesh)

    verts = [v for v in bme.verts if v.select]

    bounds = calc_bounds_verts(verts)

    bme.free()

    bpy.ops.object.mode_set(mode=mode)

    return bounds


def edit_dimensions(new_x, new_y, new_z):
    bounds = calc_bounds()
    if bpy.context.object.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    x = safe_divide(new_x, bounds["x"])
    y = safe_divide(new_y, bounds["y"])
    z = safe_divide(new_z, bounds["z"])

    # We are going to let some bpy.ops do their thing,
    # so the bmeshes_from_edit_mesh will become invalid
    bmeshes_from_edit_mesh.clear()

    # Save the transform_pivot_point
    orig_transform_pivot_point = bpy.context.tool_settings.transform_pivot_point
    # Save the 3D cursor location
    orig_cursor_location = bpy.context.scene.cursor.location.copy()

    wm = bpy.context.window_manager

    if wm.edit_dimensions_anchor in ['CURSOR', 'MEDIAN_POINT', 'ACTIVE_ELEMENT']:
        bpy.context.tool_settings.transform_pivot_point = wm.edit_dimensions_anchor
    elif wm.edit_dimensions_anchor == 'OBJECT_ORIGIN':
        bpy.context.scene.cursor.location = bpy.context.object.location.copy()
        bpy.context.tool_settings.transform_pivot_point = 'CURSOR'
    elif wm.edit_dimensions_anchor == 'TOOL_SETTINGS':
        pass

    bpy.ops.transform.resize(value=(x, y, z))

    # Restore the original transform_pivot_point
    bpy.context.tool_settings.transform_pivot_point = orig_transform_pivot_point
    # Restore the 3D cursor location
    bpy.context.scene.cursor.location = orig_cursor_location

############# Blender Event Handlers ##############


internal_update = False


def on_edit_dimensions_prop_changed(self, context):
    if not internal_update:
        bpy.ops.ed.undo_push()
        edit_dimensions(self.edit_dimensions.x,
                        self.edit_dimensions.y,
                        self.edit_dimensions.z)


@persistent
def on_undo_redo(self, context):
    # Upon undo/redo the edit meshes become invalid.
    bmeshes_from_edit_mesh.clear()

############# Blender Extension Classes ##############


class CAD_DIM_PT_MeshTools(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_label = "CAD Mesh Dimensions"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.object != None and context.object.mode == 'EDIT'

    def draw(self, context):
        layout = self.layout

        wm = context.window_manager

        box = layout.box()
        box.prop(wm, 'edit_dimensions')
        row = box.row()
        row.label(text="Transform Anchor Point:")
        row.prop(wm, 'edit_dimensions_anchor', icon_only=True)


class CAD_DIM_EditDimensionProperties(bpy.types.PropertyGroup):
    length: bpy.props.FloatProperty(name="Length", min=0, default=1, unit='LENGTH')
    width: bpy.props.FloatProperty(name="Width", min=0, default=1, unit='LENGTH')
    height: bpy.props.FloatProperty(name="Height", min=0, default=1, unit='LENGTH')


classes = [
    CAD_DIM_EditDimensionProperties,
    CAD_DIM_PT_MeshTools,
]

############# SpaceView3D Draw Handler ##############

bmeshes_from_edit_mesh = {}
prev_select_history_len = 0
prev_select_history_active = None
handle = None


def spaceview3d_draw_handler():
    global prev_select_history_len, prev_select_history_active
    should_refresh = False
    context = bpy.context
    obj = context.active_object
    meshes = set(o.data for o in ([obj] + context.selected_objects) if o != None and o.mode == 'EDIT')
    if context.mode == 'EDIT_MESH':
        for m in meshes:
            if not m.name in bmeshes_from_edit_mesh:
                bmeshes_from_edit_mesh[m.name] = bmesh.from_edit_mesh(m)
                should_refresh = True
            # else:
            #     del bmeshes_from_edit_mesh[m.name]

            # # print("update edit mesh for", m.name)
            # bmeshes_from_edit_mesh.setdefault(m.name, bmesh.from_edit_mesh(m))
    else:
        bmeshes_from_edit_mesh.clear()
        prev_select_history_active = None
        return

    mesh = obj.data

    if mesh.name in bmeshes_from_edit_mesh:
        # print("edit_mesh: Update")
        bme = bmeshes_from_edit_mesh[mesh.name]
        select_history = bme.select_history

        # @TODO if select mode is not vertex, efficiently get verts from selected items
        # if len(select_history):
        #     selected_verts = [v for v in select_history]
        # else:
        #     selected_verts = [v for v in bme.verts if v.select]
        # So for now:
        selected_verts = [v for v in bme.verts if v.select]

        cur_select_history_len = len(selected_verts)

        if (should_refresh or
                prev_select_history_active != select_history.active or
                prev_select_history_len != cur_select_history_len):

            prev_select_history_active = select_history.active
            prev_select_history_len = cur_select_history_len
            bounds = calc_bounds_verts(selected_verts)

            global internal_update
            wm = context.window_manager

            internal_update = True
            wm.edit_dimensions[0] = bounds["x"]
            wm.edit_dimensions[1] = bounds["y"]
            wm.edit_dimensions[2] = bounds["z"]
            internal_update = False
    else:
        print("edit_mesh: No update")

############# Register/Unregister Hooks ##############


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.WindowManager.edit_dimensions = bpy.props.FloatVectorProperty(
        name="Dimensions:",
        min=0,
        default=(0, 0, 0),
        subtype='XYZ',
        unit='LENGTH',
        update=on_edit_dimensions_prop_changed
    )

    #(identifier, name, description, icon, number)
    transform_anchor_point_enum = [
        ('CURSOR', "3D Cursor", 'Transform from the 3D cursor', 'PIVOT_CURSOR', 0),
        ('MEDIAN_POINT', 'Median Point', 'Transform from the median point of the selected geometry', 'PIVOT_MEDIAN', 1),
        ('ACTIVE_ELEMENT', 'Active Element', 'Transform from the active element', 'PIVOT_ACTIVE', 2),
        ('OBJECT_ORIGIN', 'Object Origin', 'Transform from the object\'s origin', 'OBJECT_ORIGIN', 3),
        ('TOOL_SETTINGS', 'Blender Tool Settings',
         'Transform from whatever is currently configured as the Transform Pivot Point in the Tool Settings', 'BLENDER', 4)
    ]

    bpy.types.WindowManager.edit_dimensions_anchor = bpy.props.EnumProperty(
        name="Transform Anchor Point",
        description="Anchor Point for Edit Dimension Transformations",
        items=transform_anchor_point_enum,
        default='ACTIVE_ELEMENT'
    )

    bpy.app.handlers.undo_post.append(on_undo_redo)
    bpy.app.handlers.redo_post.append(on_undo_redo)

    global handle
    handle = bpy.types.SpaceView3D.draw_handler_add(
        spaceview3d_draw_handler, (),
        'WINDOW', 'POST_PIXEL')


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    del bpy.types.WindowManager.edit_dimensions
    del bpy.types.WindowManager.edit_dimensions_anchor

    bpy.app.handlers.undo_post.remove(on_undo_redo)
    bpy.app.handlers.redo_post.remove(on_undo_redo)

    global handle
    bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')


if __name__ == "__main__":
    register()
