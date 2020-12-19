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

import sys
import site

import time  # pylint: disable=unused-import

import bmesh
import bpy
import numpy as np
from mathutils import Vector

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

sys.path.append(site.getusersitepackages())

try:
    import xxhash
except:
    import subprocess

    pybin = bpy.app.binary_path_python

    try:
        # upgrade pip
        subprocess.call([pybin, "-m", "ensurepip"])
        subprocess.call([pybin, "-m", "pip", "install", "--upgrade", "pip"])
    except:
        pass

    # install required packages
    subprocess.call([pybin, "-m", "pip", "install", "--user", "xxhash"])

    import xxhash


############# Generic Python Utility Functions ##############

def safe_divide(a, b):
    if b != 0:
        return a / b
    return 1


def flatten(t):
    return [item for sublist in t for item in sublist]


############ Generic Blender Utility Functions / Classes #############


class SelectedElementsRep:
    """Representation of the selected elements in the bmesh
       without actually keeping a (potentially stale
       reference to a python wrapped C object)"""

    def __init__(self, bme):
        self.len = len(bme.select_history)
        self.mode = frozenset(bme.select_mode)
        active = bme.select_history.active
        self.active_element_type = active.__class__ if active else None
        self.active_element_index = active.index if active else None

    def __hash__(self):
        return hash((self.len, self.mode, self.active_element_type, self.active_element_index))

    def __eq__(self, other):
        return (
            other and (self.len, self.mode, self.active_element_type, self.active_element_index) ==
            (other.len, other.mode, other.active_element_type, other.active_element_index)
        )


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


def calc_bounds_verts(selected_verts, matrix):
    v_coords = list(map(lambda v: Vector(matrix @ v.co), selected_verts))

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


def calc_bounds(ob):
    """Calculates the bounding box for selected vertices. Requires applied scale to work correctly. """
    # for some reason we must change into object mode for the calculations
    mode = ob.mode
    bpy.ops.object.mode_set(mode='OBJECT')

    mesh = bpy.context.object.data

    bme = bmesh.new()
    bme.from_mesh(mesh)

    verts = [v for v in bme.verts if v.select]

    bounds = calc_bounds_verts(verts, ob.matrix_world)

    bme.free()

    bpy.ops.object.mode_set(mode=mode)

    return bounds


def calc_matrix(ob, bme):
    matrix = None

    def normal_get(e):
        return e.normal if hasattr(e, 'normal') else (e.verts[0].co - e.verts[1].co).normalized()

    def filter_selected_normals(seq):
        selected = [normal_get(e) for e in seq if e.select]
        return selected if len(selected) > 0 else None

    selected_faces_normals = filter_selected_normals(bme.faces)
    selected_edges_normals = filter_selected_normals(bme.edges) if not selected_faces_normals else None
    selected_verts_normals = filter_selected_normals(bme.verts) if not (
        selected_faces_normals or selected_edges_normals) else None

    normal_vector = None

    if selected_faces_normals:
        normal_vector = Vector(sum(selected_faces_normals, Vector())).normalized()
    elif selected_edges_normals:
        normal_vector = Vector(sum(selected_edges_normals, Vector())).normalized()
    elif selected_verts_normals:
        normal_vector = Vector(sum(selected_verts_normals, Vector())).normalized()

    if normal_vector:
        matrix = normal_vector.to_track_quat('Z', 'Y').to_matrix().to_4x4().inverted()
    else:
        matrix = ob.matrix_world

    return matrix


############ CAD Mesh Dimensions Blender Utility Functions #############


CAD_MESH_DIMENSIONS_MAX_VERTS = 10000


def cad_mesh_dimensions_is_enabled(ob):
    return ob and ob.mode == 'EDIT' and len(ob.data.vertices) < CAD_MESH_DIMENSIONS_MAX_VERTS


LENGTH = 0
WIDTH = 1
HEIGHT = 2

hash_prev = 0
transform_orientation_prev = None
selected_elements_rep_prev = None
lwh_012_mapping = None
lwh_xyz_mapping = None


def lwh_mapping_ensure(bme, bounds=None):
    global selected_elements_rep_prev, lwh_012_mapping, lwh_xyz_mapping

    selected_elements_rep_cur = SelectedElementsRep(bme)

    if selected_elements_rep_cur != selected_elements_rep_prev:
        selected_elements_rep_prev = selected_elements_rep_cur

        tuples_sorted = sorted([(0, 'x', bounds['x']), (1, 'y', bounds['y']), (2, 'z', bounds['z'])],
                               reverse=True, key=lambda tup: tup[2])
        lwh_012_mapping = (tuples_sorted[0][0], tuples_sorted[1][0], tuples_sorted[2][0])
        lwh_xyz_mapping = (tuples_sorted[0][1], tuples_sorted[1][1], tuples_sorted[2][1])

    return lwh_xyz_mapping


def transform_orientation_get(ob):
    scene = bpy.context.scene

    return (scene.transform_orientation_slots[0].type
            if ob.cad_mesh_dimensions.orientation == 'TOOL_SETTINGS'
            else ob.cad_mesh_dimensions.orientation)


def update_dimensions(ob, bme, selected_verts):

    if transform_orientation_get(ob) == 'NORMAL':
        matrix = calc_matrix(ob, bme)
    else:
        matrix = ob.matrix_world

    bounds = calc_bounds_verts(selected_verts, matrix)

    global internal_update
    wm = bpy.context.window_manager

    internal_update = True
    if transform_orientation_get(ob) == 'NORMAL':
        lwh_mapping_ensure(bme, bounds)
        wm.cad_mesh_dimensions.x = bounds[lwh_xyz_mapping[WIDTH]]
        wm.cad_mesh_dimensions.y = bounds[lwh_xyz_mapping[LENGTH]]
        wm.cad_mesh_dimensions.z = bounds[lwh_xyz_mapping[HEIGHT]]
    else:
        wm.cad_mesh_dimensions.x = bounds['x']
        wm.cad_mesh_dimensions.y = bounds['y']
        wm.cad_mesh_dimensions.z = bounds['z']
    internal_update = False


def update_dimensions_if_changed(ob):
    global hash_prev, transform_orientation_prev

    # start_time = time.time()

    me = ob.data
    bme = bmesh.from_edit_mesh(me)
    selected_verts = [v for v in bme.verts if v.select]
    hash_cur = vertices_hash(selected_verts)

    transform_orientation_cur = transform_orientation_get(ob)

    selected_elements_rep_cur = SelectedElementsRep(bme)

    if (hash_prev != hash_cur
            or transform_orientation_prev != transform_orientation_cur
            or selected_elements_rep_cur != selected_elements_rep_prev):
        hash_prev = hash_cur
        transform_orientation_prev = transform_orientation_cur
        # CAVEAT REFACTOR: Do not update 'selected_elements_rep_prev'
        # 'lwh_mapping_ensure' will take care of that when needed.

        update_dimensions(ob, bme, selected_verts)

    # elapsed_time = time.time() - start_time
    # print("elapsed_time", elapsed_time * 1000)


def edit_dimensions(new_x, new_y, new_z):
    ob = bpy.context.object
    bounds = calc_bounds(ob)
    if ob.mode != 'EDIT':
        ob.mode_set(mode='EDIT')
    x = safe_divide(new_x, bounds["x"])
    y = safe_divide(new_y, bounds["y"])
    z = safe_divide(new_z, bounds["z"])

    # Save the transform_pivot_point
    orig_transform_pivot_point = bpy.context.tool_settings.transform_pivot_point
    # Save the 3D cursor location
    orig_cursor_location = bpy.context.scene.cursor.location.copy()

    if ob.cad_mesh_dimensions.anchor in ['CURSOR', 'MEDIAN_POINT', 'ACTIVE_ELEMENT']:
        bpy.context.tool_settings.transform_pivot_point = ob.cad_mesh_dimensions.anchor
    elif ob.cad_mesh_dimensions.anchor == 'OBJECT_ORIGIN':
        bpy.context.scene.cursor.location = ob.location.copy()
        bpy.context.tool_settings.transform_pivot_point = 'CURSOR'
    elif ob.cad_mesh_dimensions.anchor == 'TOOL_SETTINGS':
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
        ob = context.object

        if transform_orientation_get(ob) == 'NORMAL':
            bme = bmesh.from_edit_mesh(ob.data)
            matrix = calc_matrix(ob, bme)
            mapped_cad_mesh_dimensions = Vector()
            # pylint: disable=unsupported-assignment-operation
            mapped_cad_mesh_dimensions[lwh_012_mapping[LENGTH]] = self.cad_mesh_dimensions.y
            mapped_cad_mesh_dimensions[lwh_012_mapping[WIDTH]] = self.cad_mesh_dimensions.x
            mapped_cad_mesh_dimensions[lwh_012_mapping[HEIGHT]] = self.cad_mesh_dimensions.z
            dimensions = ob.matrix_world @ matrix.inverted() @ mapped_cad_mesh_dimensions
        else:
            dimensions = self.cad_mesh_dimensions

        edit_dimensions(abs(dimensions.x),
                        abs(dimensions.y),
                        abs(dimensions.z))


############# Blender Extension Classes ##############


# (identifier, name, description, icon, number)
CAD_DIM_TRANSFORM_ANCHOR_POINT_ENUM = [
    ('CURSOR', "3D Cursor", 'Transform from the 3D cursor', 'PIVOT_CURSOR', 0),
    ('MEDIAN_POINT', 'Median Point', 'Transform from the median point of the selected geometry', 'PIVOT_MEDIAN', 1),
    ('ACTIVE_ELEMENT', 'Active Element', 'Transform from the active element', 'PIVOT_ACTIVE', 2),
    ('OBJECT_ORIGIN', 'Object Origin', 'Transform from the object\'s origin', 'OBJECT_ORIGIN', 3),
    ('TOOL_SETTINGS', 'Blender Tool Settings',
        'Transform from whatever is currently configured as the Transform Pivot Point in the Tool Settings', 'BLENDER', 4)
]

# (identifier, name, description, icon, number)
CAD_DIM_TRANSFORM_ORIENTATION_ENUM = [
    ('GLOBAL', "Global", 'Align the transformation axes to world space', 'ORIENTATION_GLOBAL', 0),
    ('NORMAL', 'Normal', 'Align the transformation axes to average normal of selected element', 'ORIENTATION_NORMAL', 1),
    ('TOOL_SETTINGS', 'Blender Tool Settings',
        'Align the orientation to whatever is currently configured as the Transformation Orientation in the Tool Settings', 'BLENDER', 2)
]


class CAD_DIM_ObjectProperties(bpy.types.PropertyGroup):
    anchor: bpy.props.EnumProperty(
        name="Transform Anchor Point",
        description="Anchor Point for CAD Mesh Dimensions Transformations",
        items=CAD_DIM_TRANSFORM_ANCHOR_POINT_ENUM,
        default='OBJECT_ORIGIN'
    )
    orientation: bpy.props.EnumProperty(
        name="Transformation Orientation",
        description="Orientation for CAD Mesh Dimensions Transformations",
        items=CAD_DIM_TRANSFORM_ORIENTATION_ENUM,
        default='TOOL_SETTINGS'
    )


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
        row.prop(ob.cad_mesh_dimensions, 'anchor', icon_only=True)
        row = box.row()
        row.label(text="Transform Orientation:")
        row.prop(ob.cad_mesh_dimensions, 'orientation', icon_only=True)

        orientation = transform_orientation_get(ob)
        if orientation not in ['GLOBAL', 'NORMAL']:
            box.row().label(text="The orientation mode '%s'" % orientation.capitalize(), icon='ERROR')
            box.row().label(text="in the Blender tool settings is not")
            box.row().label(text="supported, defaulting to 'Global'.")


class CAD_DIM_EditDimensionProperties(bpy.types.PropertyGroup):
    length: bpy.props.FloatProperty(name="Length", min=0, default=1, unit='LENGTH')
    width: bpy.props.FloatProperty(name="Width", min=0, default=1, unit='LENGTH')
    height: bpy.props.FloatProperty(name="Height", min=0, default=1, unit='LENGTH')


classes = [
    CAD_DIM_ObjectProperties,
    CAD_DIM_EditDimensionProperties,
    CAD_DIM_PT_MeshTools,
]


############# SpaceView3D Draw Handler ##############


def spaceview3d_draw_handler():
    global hash_prev, transform_orientation_prev, selected_elements_rep_prev, lwh_012_mapping, lwh_xyz_mapping

    context = bpy.context
    ob = context.active_object

    if cad_mesh_dimensions_is_enabled(ob):
        if context.mode == 'EDIT_MESH':
            update_dimensions_if_changed(ob)
        else:
            hash_prev = 0
            transform_orientation_prev = None
            selected_elements_rep_prev = None
            lwh_012_mapping = None
            lwh_xyz_mapping = None


############# Register/Unregister Hooks ##############


handle = None


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

    bpy.types.Object.cad_mesh_dimensions = bpy.props.PointerProperty(
        name="CAD Mesh Dimensions Object Properties", type=CAD_DIM_ObjectProperties)

    global handle
    handle = bpy.types.SpaceView3D.draw_handler_add(
        spaceview3d_draw_handler, (),
        'WINDOW', 'POST_PIXEL')


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    del bpy.types.WindowManager.cad_mesh_dimensions
    del bpy.types.Object.cad_mesh_dimensions

    global handle
    bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')


if __name__ == "__main__":
    register()
