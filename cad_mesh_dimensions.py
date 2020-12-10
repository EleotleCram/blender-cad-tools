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

from threading import Timer
import numpy as np
import time
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


########### Automatic PIP Dependency Installation ###########

try:
    import xxhash
except:
    import subprocess

    pybin = bpy.app.binary_path_python

    # upgrade pip
    subprocess.call([pybin, "-m", "ensurepip"])
    subprocess.call([pybin, "-m", "pip", "install", "--upgrade", "pip"])

    # install required packages
    subprocess.call([pybin, "-m", "pip", "install", "xxhash"])

    import xxhash


############# Generic Python Utility Functions ##############

def safe_divide(a, b):
    if b != 0:
        return a / b
    return 1


def flatten(t):
    return [item for sublist in t for item in sublist]


def get_current_time_millis():
    return int(round(time.time() * 1000))


def throttled(timeout):
    def decorator_func(callback):
        timer = None
        millis_prev = 0

        def throttled_func(*args):
            nonlocal timer, millis_prev

            def do_callback(*args):
                nonlocal timer
                timer = None
                callback(*args)

            millis_cur = get_current_time_millis()
            if millis_cur - millis_prev > timeout:
                millis_prev = millis_cur
                do_callback(*args)
            else:
                if timer is not None:
                    timer.cancel()

                timer = Timer(timeout / 1000, do_callback, args)
                timer.start()

        return throttled_func

    return decorator_func

############ Generic Blender Utility Functions #############


def vertices_hash(vertices):
    # start_time = time.time()

    if hasattr(vertices, 'foreach_get'):
        count = len(vertices)
        verts = np.empty(count * 3, dtype=np.float64)
        vertices.foreach_get('co', verts)
    else:
        verts = np.array(flatten([
            (v.co.x, v.co.y, v.co.z) for v in vertices
        ]), dtype=np.float64)

    h = xxhash.xxh32(seed=20141025)
    h.update(verts)
    __hash = h.intdigest()

    # elapsed_time = time.time() - start_time
    # print("elapsed_time", elapsed_time * 1000)

    # The - 0x7fffffff is because Blender appears to
    # insist on a signed value, and this function
    # does not care, as long as the value is consistent.
    return __hash - 0x7fffffff


def calc_bounds_verts(ob, selected_verts):
    matrix_world = ob.matrix_world
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

    bounds = calc_bounds_verts(bpy.context.object, verts)

    bme.free()

    bpy.ops.object.mode_set(mode=mode)

    return bounds


def edit_dimensions(new_x, new_y, new_z):
    ob = bpy.context.object
    bounds = calc_bounds()
    if ob.mode != 'EDIT':
        ob.mode_set(mode='EDIT')
    x = safe_divide(new_x, bounds["x"])
    y = safe_divide(new_y, bounds["y"])
    z = safe_divide(new_z, bounds["z"])

    # Save the transform_pivot_point
    orig_transform_pivot_point = bpy.context.tool_settings.transform_pivot_point
    # Save the 3D cursor location
    orig_cursor_location = bpy.context.scene.cursor.location.copy()

    wm = bpy.context.window_manager

    if ob.cad_mesh_dimensions_anchor in ['CURSOR', 'MEDIAN_POINT', 'ACTIVE_ELEMENT']:
        bpy.context.tool_settings.transform_pivot_point = ob.cad_mesh_dimensions_anchor
    elif ob.cad_mesh_dimensions_anchor == 'OBJECT_ORIGIN':
        bpy.context.scene.cursor.location = ob.location.copy()
        bpy.context.tool_settings.transform_pivot_point = 'CURSOR'
    elif ob.cad_mesh_dimensions_anchor == 'TOOL_SETTINGS':
        pass

    bpy.ops.transform.resize(value=(x, y, z))

    # Restore the original transform_pivot_point
    bpy.context.tool_settings.transform_pivot_point = orig_transform_pivot_point
    # Restore the 3D cursor location
    bpy.context.scene.cursor.location = orig_cursor_location


############ CAD Mesh Dimensions Blender Utility Functions #############


CAD_MESH_DIMENSIONS_MAX_VERTS = 10000


def cad_mesh_dimensions_is_enabled(ob):
    return ob and ob.mode == 'EDIT' and len(ob.data.vertices) < CAD_MESH_DIMENSIONS_MAX_VERTS


############# Blender Event Handlers ##############


internal_update = False


def on_edit_dimensions_prop_changed(self, context):
    if not internal_update:
        bpy.ops.ed.undo_push()
        edit_dimensions(self.cad_mesh_dimensions.x,
                        self.cad_mesh_dimensions.y,
                        self.cad_mesh_dimensions.z)


############# Blender Extension Classes ##############


class CAD_DIM_PT_MeshTools(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_label = "CAD Mesh Dimensions"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return cad_mesh_dimensions_is_enabled(context.object)

    def draw(self, context):
        layout = self.layout

        ob = context.object
        wm = context.window_manager

        box = layout.box()
        box.prop(wm, 'cad_mesh_dimensions')
        row = box.row()
        row.label(text="Transform Anchor Point:")
        row.prop(ob, 'cad_mesh_dimensions_anchor', icon_only=True)


class CAD_DIM_EditDimensionProperties(bpy.types.PropertyGroup):
    length: bpy.props.FloatProperty(name="Length", min=0, default=1, unit='LENGTH')
    width: bpy.props.FloatProperty(name="Width", min=0, default=1, unit='LENGTH')
    height: bpy.props.FloatProperty(name="Height", min=0, default=1, unit='LENGTH')


classes = [
    CAD_DIM_EditDimensionProperties,
    CAD_DIM_PT_MeshTools,
]

############# SpaceView3D Draw Handler ##############


hash_prev = 0
handle = None


def update_dimensions(ob, selected_verts):
    bounds = calc_bounds_verts(ob, selected_verts)

    global internal_update
    context = bpy.context
    wm = context.window_manager

    internal_update = True
    wm.cad_mesh_dimensions[0] = bounds["x"]
    wm.cad_mesh_dimensions[1] = bounds["y"]
    wm.cad_mesh_dimensions[2] = bounds["z"]
    internal_update = False


@throttled(100)
def update_dimensions_if_changed(ob_name):
    global hash_prev

    # start_time = time.time()

    if ob_name in bpy.data.objects:
        ob = bpy.data.objects[ob_name]
        me = ob.data

        bme = bmesh.from_edit_mesh(me)

        selected_verts = [v for v in bme.verts if v.select]

        hash_cur = vertices_hash(selected_verts)

        if hash_prev != hash_cur:
            hash_prev = hash_cur

            update_dimensions(ob, selected_verts)

    # elapsed_time = time.time() - start_time
    # print("elapsed_time", elapsed_time * 1000)


def spaceview3d_draw_handler():
    global hash_prev

    context = bpy.context
    ob = context.active_object

    if cad_mesh_dimensions_is_enabled(ob):
        if context.mode == 'EDIT_MESH':
            update_dimensions_if_changed(ob.name)
        else:
            hash_prev = 0


############# Register/Unregister Hooks ##############


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.WindowManager.cad_mesh_dimensions = bpy.props.FloatVectorProperty(
        name="Dimensions:",
        min=0,
        default=(0, 0, 0),
        subtype='XYZ',
        unit='LENGTH',
        precision=4,
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

    bpy.types.Object.cad_mesh_dimensions_anchor = bpy.props.EnumProperty(
        name="Transform Anchor Point",
        description="Anchor Point for Edit Dimension Transformations",
        items=transform_anchor_point_enum,
        default='OBJECT_ORIGIN'
    )

    global handle
    handle = bpy.types.SpaceView3D.draw_handler_add(
        spaceview3d_draw_handler, (),
        'WINDOW', 'POST_PIXEL')


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    del bpy.types.WindowManager.cad_mesh_dimensions
    del bpy.types.Object.cad_mesh_dimensions_anchor

    global handle
    bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')


if __name__ == "__main__":
    register()
