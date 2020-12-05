# ##### BEGIN GPL LICENSE BLOCK #####
#
#  CAD Outline - Overlay objects with CAD-like outline
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

import struct
import time
import numpy as np
from functools import reduce
from mathutils import Vector, Matrix
from math import pi, acos
import bmesh
from bpy.app.handlers import persistent
import bpy


bl_info = {
    "name": "CAD Outline",
    "author": "Marcel Toele",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D",
    "description": "Overlay objects with CAD-like outline",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
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


def flatten(t):
    return [item for sublist in t for item in sublist]


DEBUG = False

if DEBUG:
    def dprint(*args):
        print(*args)
else:
    def dprint(*args):
        pass

############ Generic Blender Utility Functions #############


int_to_four_bytes = struct.Struct('<I').pack

############
#
# Standard DJB2 Hash function.
#
# arg(s: string) - input string to be hashed
#


def hash_djb2_string(s):
    return reduce(lambda h, c: ord(c) + ((h << 5) + h), s, 5381) & 0xFFFFFFFF

############
#
# DJB2 Hash increment function.
#
# arg(__hash: int32) - current hash state
# arg(i: int32) - input quad bytes for next increment
#
# Note: Users should initialize the first call themselves
#       with `__hash = 5381` for best experience
#
# Non-standard naming for avoid collision with builtin function:


def hash_djb2_inc(__hash, i):
    for x in int_to_four_bytes(i & 0xFFFFFFFF):
        __hash = ((__hash << 5) + __hash) + x

    return __hash & 0xFFFFFFFF


def vertices_hash(vertices):
    start_time = time.time()

    count = len(vertices)
    verts = np.empty(count*3, dtype=np.float64)
    vertices.foreach_get('co', verts)

    h = xxhash.xxh32(seed=20141025)
    h.update(verts)
    __hash = h.intdigest()

    elapsed_time = time.time() - start_time
    dprint("elapsed_time", elapsed_time * 1000)

    # The - 0x7fffffff is because Blender appears to
    # insist on a signed value, and this function
    # does not care, as long as the value is consistent.
    return __hash - 0x7fffffff


def childof_constraints_get(ob):
    return [c for c in ob.constraints if c.type == 'CHILD_OF' and c.target != None]


def childof_constraints_clear(ob):
    for c in childof_constraints_get(ob):
        ob.constraints.remove(c)


def childof_constraint_get(ob_parent, ob_child):
    childof_constraints = childof_constraints_get(ob_child)
    # Must check name equality, pointers are different (probably python rna ptr wrap issue):
    return next((c for c in childof_constraints if c.target.name == ob_parent.name), None)


def childof_constraint_ensure(ob_parent, ob_child):
    if childof_constraint_get(ob_parent, ob_child) == None:
        constraint = ob_child.constraints.new(type='CHILD_OF')
        constraint.target = ob_parent
        constraint.inverse_matrix = Matrix.Scale(1.0, 4)


TOLERANCE = 5
TOLERANCE_EXP = 10**TOLERANCE


def face_angle_deg_get(face1, face2):
    dp = face1.normal.dot(face2.normal)
    # 2x faster than round and good enough for us:
    dp = int(dp * TOLERANCE_EXP + 0.5)/TOLERANCE_EXP
    angle_deg = acos(dp) * 180 / pi

    return angle_deg


def depsgraph_update_objects_find(update):
    objects = []

    if isinstance(update.id.original, bpy.types.Object):
        objects = [update.id.original]
    elif isinstance(update.id.original, bpy.types.Mesh):
        objects = [o for o in bpy.data.objects if o.data == update.id.original]

    return objects

############ CAD Outline Blender Utility Functions #############


def mesh_cache_refresh():
    global mesh_cache_out_of_date

    if mesh_cache_out_of_date:
        mesh_cache.clear()

        for ob_outline in cad_outline_collection_ensure().objects:
            if len(ob_outline.data.vertices) > 0:
                dprint("mesh_cache update:  mesh_cache[%d] = " %
                       ob_outline.cad_outline.evaluated_mesh_hash, ob_outline.data)
                mesh_cache[ob_outline.cad_outline.evaluated_mesh_hash] = ob_outline.data.name

        mesh_cache_out_of_date = False


def mesh_cache_save_delete(evaluated_mesh_hash):
    if evaluated_mesh_hash in mesh_cache:
        del mesh_cache[evaluated_mesh_hash]


def cad_outline_mesh_and_options_hash_get(ob):
    __hash = ob.cad_outline.evaluated_mesh_hash + 0x7fffffff

    # Add mode
    __hash = hash_djb2_inc(
        __hash,
        # CAVEAT REFACTOR: `hash(ob.cad_outline.evaluated_mesh_hash)`
        #                  is not consistent across restarts!
        hash_djb2_string(ob.cad_outline.mode)
    )

    # Add sharp angle
    __hash = hash_djb2_inc(
        __hash,
        hash(ob.cad_outline.sharp_angle)
    )

    return __hash - 0x7fffffff


def cad_outline_collections_get():
    return [c for c in bpy.data.collections if "CAD Outline Objects" in c.name]


def cad_outline_collection_ensure(col_parent=None):
    col_outline = None

    if col_parent == None:
        if not "CAD Outline Objects" in bpy.data.collections:
            collection = bpy.data.collections.new("CAD Outline Objects")
            bpy.context.scene.collection.children.link(collection)

        col_outline = bpy.data.collections["CAD Outline Objects"]
    else:
        col_outline = next(
            (c for c in col_parent.children if c.name.startswith(
                "CAD Outline Objects.node")),
            None
        )

        if not col_outline:
            col_outline = bpy.data.collections.new("CAD Outline Objects.node")
            col_parent.children.link(col_outline)

    return col_outline


def cad_outline_object_hide_set(ob, should_be_hidden):
    if ob.cad_outline.is_enabled:
        ob_outline = cad_outline_object_ensure(ob)
        if not ob.cad_outline.debug:
            ob_outline.hide_set(should_be_hidden)
        ob_outline.hide_viewport = should_be_hidden


def cad_outline_object_name_get(ob):
    return "%s.ol" % ob.name[0:58]


def cad_outline_object_ensure(ob):
    if ob.cad_outline.is_enabled:
        ob_outline_name = cad_outline_object_name_get(ob)

        if not ob_outline_name in bpy.data.objects:
            dprint("outline object does not exist, creating...")
            col_outline = cad_outline_collection_ensure()
            me = bpy.data.meshes.new('%s.ol' % ob.data.name)
            ob_outline = bpy.data.objects.new(ob_outline_name, me)
            col_outline.objects.link(ob_outline)
            ob.cad_outline.evaluated_mesh_hash = 0
            bpy.context.view_layer.update()

        ob_outline = bpy.data.objects[ob_outline_name]
        ob_outline.hide_select = not ob.cad_outline.debug
        childof_constraints_clear(ob_outline)
        childof_constraint_ensure(ob, ob_outline)

        return ob_outline
    else:
        return None


def cad_outline_object_get(ob):
    ob_outline_name = cad_outline_object_name_get(ob)
    ob_outline = None

    if ob_outline_name in bpy.data.objects:
        ob_outline = bpy.data.objects[ob_outline_name]

    return ob_outline


mesh_cache = {}
mesh_cache_out_of_date = True


def cad_outline_mesh_update(ob, ob_evaluated):

    if ob.cad_outline.is_enabled:

        ob_outline = cad_outline_object_ensure(ob)
        ob_outline.location = (0, 0, 0)
        ob_outline.display_type = 'WIRE'
        ob_outline_prev_evaluated_mesh_hash = ob_outline.cad_outline.evaluated_mesh_hash
        ob_outline.cad_outline.evaluated_mesh_hash = cad_outline_mesh_and_options_hash_get(
            ob)

        dprint("mesh_cache_out_of_date", mesh_cache_out_of_date)
        if mesh_cache_out_of_date:
            mesh_cache_refresh()
        dprint("mesh_cache", list(mesh_cache.items()))

        # Check cache
        if ob_outline.cad_outline.evaluated_mesh_hash in mesh_cache:
            me_name = mesh_cache[ob_outline.cad_outline.evaluated_mesh_hash]
            me_cached = bpy.data.meshes[me_name]

            dprint("FOUND IN CACHE!",
                   ob_outline.cad_outline.evaluated_mesh_hash, me_cached)
            me_old = ob_outline.data
            ob_outline.data = me_cached
            if me_old.users == 0:
                mesh_cache_save_delete(ob_outline_prev_evaluated_mesh_hash)
                bpy.data.meshes.remove(me_old, do_unlink=True)
        # Cache miss, recompute
        else:
            dprint("NOT FOUND IN CACHE :(", ob_outline.cad_outline.evaluated_mesh_hash,
                   ob_outline_prev_evaluated_mesh_hash, ob_outline.data.users)
            if ob_outline.data.users > 1:
                ob_outline.data = ob_outline.data.copy()
            elif ob_outline_prev_evaluated_mesh_hash in mesh_cache:
                mesh_cache_save_delete(ob_outline_prev_evaluated_mesh_hash)

            bme = bmesh.new()
            bme.from_mesh(ob_evaluated.data)

            bme.edges.ensure_lookup_table()
            bme.faces.ensure_lookup_table()

            edge_to_faces = {}

            for face in bme.faces:
                for edge in face.edges:
                    if not edge in edge_to_faces:
                        edge_to_faces[edge] = set()

                    edge_to_faces[edge].add(face)

            edges_to_delete = set()
            face_edges = [e for e in bme.edges if e in edge_to_faces]

            # Functions to determine if a face is one of the three cartesian planes:
            def component_len(face, x):
                return reduce(lambda res, e: res + (1 if abs(e-x) < 0.0001 else 0), face.normal, 0)

            def is_cart(face):
                return component_len(face, 1) == 1 and component_len(face, 0) == 2

            # Select faces to delete:
            for edge in face_edges:
                edge_faces = edge_to_faces[edge]
                if len(edge_faces) == 2:
                    f1, f2 = edge_faces
                    face_angle_deg = face_angle_deg_get(*edge_faces)

                    if ob.cad_outline.mode == 'SHARP_CART':
                        is_cart_f1 = is_cart(f1)
                        is_cart_f2 = is_cart(f2)

                        is_cart_edge = (is_cart_f1 or is_cart_f2) and (
                            is_cart_f1 != is_cart_f2) and (abs(face_angle_deg) >= 1)
                    else:
                        is_cart_edge = False

                    if not is_cart_edge and face_angle_deg < ob.cad_outline.sharp_angle:
                        edges_to_delete.add(edge)

            if ob.cad_outline.mode in ('SHARP', 'SHARP_CART'):
                bmesh.ops.delete(bme, geom=list(
                    edges_to_delete), context='EDGES')
            bmesh.ops.delete(bme, geom=bme.faces, context='FACES_ONLY')

            bme.to_mesh(ob_outline.data)
            bme.free()

            # Cache the value
            mesh_cache[ob_outline.cad_outline.evaluated_mesh_hash] = ob_outline.data.name

############# Blender Event Handlers ##############


def on_scene_cad_outline_is_enabled_prop_updated(self, context):
    scene = self

    for col_outline in cad_outline_collections_get():
        col_outline.hide_viewport = not scene.is_cad_outline_enabled
        for ob_outline in col_outline.objects:
            ob_outline.hide_viewport = not scene.is_cad_outline_enabled


def on_object_cad_outline_is_enabled_prop_updated(self, context):
    cad_outline = self
    ob = context.active_object

    if cad_outline.is_enabled:
        bpy.context.scene.is_cad_outline_enabled = True
        ob_evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        cad_outline_mesh_update(ob, ob_evaluated)
    else:
        ob_outline = cad_outline_object_get(ob)
        if ob_outline != None:
            if ob_outline.data.users == 1:
                mesh_cache_save_delete(
                    ob_outline.cad_outline.evaluated_mesh_hash)
                bpy.data.meshes.remove(ob_outline.data, do_unlink=True)
            else:
                bpy.data.objects.remove(ob_outline, do_unlink=True)


def on_anything_that_triggers_outline_mesh_update(self, context):
    cad_outline = self
    ob = context.active_object

    if cad_outline.is_enabled:
        ob_evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        cad_outline_mesh_update(ob, ob_evaluated)


on_cad_outline_sharp_angle_prop_updated = on_anything_that_triggers_outline_mesh_update
on_cad_outline_mode_prop_updated = on_anything_that_triggers_outline_mesh_update
on_cad_outline_debug_prop_updated = on_anything_that_triggers_outline_mesh_update


@persistent
def on_load_handler(_):
    global mesh_cache_out_of_date
    mesh_cache_out_of_date = True

# @TODO move to top of file


def collection_objects_get(col):
    obs = set()
    obs.update(col.objects)

    for c in col.children:
        obs.update(collection_objects_get(c))

    return obs


@persistent
def on_scene_updated(scene, depsgraph):

    if not scene.is_cad_outline_enabled:
        return

    # start_time = time.time()

    # Update outline meshes
    # dprint("on_scene_updated")
    obs_updated = set()
    obs_updated.update(flatten(
        [depsgraph_update_objects_find(update) for update in depsgraph.updates]))
    # dprint("  `--> obs_updated", obs_updated)

    # Keeping references to python wrappers is unsafe and leads to quick Blender terminations (AKA crashes):
    obs_updated_names = [ob.name for ob in obs_updated]

    for ob_name in obs_updated_names:

        if ob_name not in bpy.data.objects:
            continue
        else:
            ob = bpy.data.objects[ob_name]

        if ob and ob.cad_outline.is_enabled and ob.mode != 'EDIT':
            ob_evaluated = ob.evaluated_get(depsgraph)
            prev_hash = ob.cad_outline.evaluated_mesh_hash
            new_hash = vertices_hash(ob_evaluated.data.vertices)
            dprint("  `--> new_hash: ", new_hash, "prev_hash: ", prev_hash)

            if new_hash != prev_hash:
                ob.cad_outline.evaluated_mesh_hash = new_hash
                dprint("           `--> Mesh changed!")
                cad_outline_mesh_update(ob, ob_evaluated)

    # Sync visibility
    for ob in bpy.data.objects:
        if ob.cad_outline.is_enabled and ob.mode != 'EDIT':
            should_be_hidden = not ob.visible_get()
            cad_outline_object_hide_set(ob, should_be_hidden)

    # Sync local_view
    local_view_space = next(
        (area.spaces[0] for area in bpy.context.screen.areas
            if area.type == 'VIEW_3D' and area.spaces[0].local_view),
        None
    )
    if local_view_space is not None:
        for ob in bpy.context.selected_objects:
            if ob.cad_outline.is_enabled:
                # @TODO Use ob.local_view_get(local_view_space) to test
                #       which objects are actually in the local_view
                # (function currently broken in Blender; always returns False :/ )
                ob_outline = cad_outline_object_ensure(ob)
                ob_outline.local_view_set(local_view_space, True)

    # Sync instances
    cols_instanced = set()
    cols_instanced.update(
        [ob.instance_collection for ob in bpy.data.objects if ob.instance_collection != None])
    for col_instanced in cols_instanced:
        obs = collection_objects_get(col_instanced)
        # dprint("Collection: ", col_instanced, "obs: ", obs)
        col_outline_node = cad_outline_collection_ensure(col_instanced)
        for ob in obs:
            # dprint("ob", ob, "ob.cad_outline.is_enabled", ob.cad_outline.is_enabled)
            if ob.cad_outline.is_enabled:
                ob_outline = cad_outline_object_ensure(ob)
                if not ob_outline.name in col_outline_node.objects:
                    col_outline_node.objects.link(ob_outline)

    # Clean up stale outline objects (for instance after rename or delete of original object):
    col_outline = cad_outline_collection_ensure()
    for ob_outline in col_outline.objects:
        ob_name = ob_outline.name[0:-3]  # <-- This just strips off the ".ol"
        if ob_name not in bpy.data.objects:
            dprint("cleanup ob_outline", ob_outline.name)
            bpy.data.objects.remove(ob_outline, do_unlink=True)
        else:
            dprint("original ob (%s) for ob_outline (%s) still exists, not cleaning up" % (
                ob_name, ob_outline.name))

    # elapsed_time = time.time() - start_time
    # dprint("on_scene_updated.elapsed_time", elapsed_time * 1000)


def on_object_mode_changed():
    ob = bpy.context.active_object

    if ob.cad_outline.is_enabled:
        # dprint("on_object_mode_changed", ob, ob.mode)
        if(ob.mode == 'EDIT'):
            cad_outline_object_hide_set(ob, True)
        else:
            cad_outline_object_hide_set(ob, False)

            ob_evaluated = ob.evaluated_get(
                bpy.context.evaluated_depsgraph_get())
            cad_outline_mesh_update(ob, ob_evaluated)


######
# Note: Not supported yet in Blender 2.82:
#
# def on_local_view_changed():
#     dprint("on_local_view_changed", bpy.context.space_data.local_view)

############# Blender Extension Classes ##############

#(identifier, name, description, icon, number)
CAD_OUTLINE_MODE_ENUM = [
    ('SHARP_CART', "Sharp+Cartesian",
     'Outline based on sharp+cartesian edges (Most accurate)'),
    ('SHARP', "Sharp Edges Only",
     'Outline based on sharp edges only (Medium accurate and a little faster)'),
    ('WIREFRAME', "All Edges", 'Outline based on all edges (Less accurate but very fast)'),
]


class CAD_Outline_ObjectProperties(bpy.types.PropertyGroup):
    is_enabled: bpy.props.BoolProperty(
        default=False,
        name="Enable Outline",
        description="Adds a CAD Outline to Enhance Object Appearance in 3D Viewport",
        update=on_object_cad_outline_is_enabled_prop_updated
    )
    show_advanced: bpy.props.BoolProperty(
        default=False,
        name="Show Advanced Options"
    )
    sharp_angle: bpy.props.FloatProperty(
        default=30,
        name="Sharp Angle",
        description="Angle Used to Keep as Sharp Edge",
        precision=2,
        step=10,
        update=on_cad_outline_sharp_angle_prop_updated
    )
    mode: bpy.props.EnumProperty(
        name="Outline Mode",
        items=CAD_OUTLINE_MODE_ENUM,
        default='SHARP_CART',
        update=on_cad_outline_mode_prop_updated
    )
    debug: bpy.props.BoolProperty(
        default=False,
        name="Debug",
        description="Turns On Debugging of CAD Outline Addon (Internal only)",
        update=on_cad_outline_debug_prop_updated
    )
    evaluated_mesh_hash: bpy.props.IntProperty(
        default=0,
        subtype='UNSIGNED',
        description="CAD Outline Source Object Evaluated Mesh Hash"
    )


class CAD_Outline_ObjectPanel(bpy.types.Panel):
    """Creates the CAD Outline Panel in the Object properties window"""
    bl_label = "CAD Outline"
    bl_idname = "OBJECT_PT_CAD_OUTLINE"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout

        ob = context.active_object

        layout.row().prop(ob.cad_outline, "is_enabled")
        row = layout.row()
        row.alignment = 'RIGHT'
        row.label(text="Advanced Options")
        row.prop(ob.cad_outline, "show_advanced", text='')

        if ob.cad_outline.show_advanced:
            layout.row().prop(ob.cad_outline, "sharp_angle")
            split = layout.split(factor=0.3)
            split.column().label(text="Outline Mode")
            split.column().prop(ob.cad_outline, "mode", text="")
            layout.row().prop(ob.cad_outline, "debug", text="Turn on CAD Outline Debugging")


class CAD_Outline_ScenePanel(bpy.types.Panel):
    """Creates the CAD Outline Panel in the Scene properties window"""
    bl_label = "CAD Outline"
    bl_idname = "SCENE_PT_CAD_OUTLINE"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        row = layout.row()

        scene = context.scene

        row.prop(scene, "is_cad_outline_enabled")


classes = [
    CAD_Outline_ObjectProperties,
    CAD_Outline_ObjectPanel,
    CAD_Outline_ScenePanel,
]

############# Register/Unregister Hooks ##############

cad_outline_msgbus_owner = object()


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.is_cad_outline_enabled = bpy.props.BoolProperty(
        default=False,
        name="Enable CAD Outline for this Scene",
        description="Enable CAD Outlines For This Scene to Enhance Object Appearance in 3D Viewport",
        update=on_scene_cad_outline_is_enabled_prop_updated
    )
    bpy.types.Object.cad_outline = bpy.props.PointerProperty(
        name="CAD Outline Object Properties", type=CAD_Outline_ObjectProperties)

    bpy.app.handlers.depsgraph_update_post.append(on_scene_updated)
    bpy.app.handlers.load_post.append(on_load_handler)

    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=cad_outline_msgbus_owner,
        args=(),
        notify=on_object_mode_changed,
    )

    ######
    # Note: Not supported yet in Blender 2.82:
    #
    # bpy.msgbus.subscribe_rna(
    #     key=(bpy.types.SpaceView3D, "local_view"),
    #     owner=cad_outline_msgbus_owner,
    #     args=(),
    #     notify=on_local_view_changed,
    # )


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    del bpy.types.Scene.is_cad_outline_enabled
    del bpy.types.Object.cad_outline

    bpy.app.handlers.depsgraph_update_post.remove(on_scene_updated)
    bpy.app.handlers.load_post.remove(on_load_handler)

    bpy.msgbus.clear_by_owner(cad_outline_msgbus_owner)


if __name__ == "__main__":
    register()
