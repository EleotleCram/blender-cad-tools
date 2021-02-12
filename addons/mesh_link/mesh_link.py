# ##### BEGIN GPL LICENSE BLOCK #####
#
#  Mesh Link - Link an evaluated mesh from another object as a base mesh
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

import time
import numpy as np
from bpy.app.handlers import persistent
import bpy


bl_info = {
    "name": "Mesh Link",
    "author": "Marcel Toele",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "Object",
    "description": "Link an evaluated mesh from another object as a base mesh",
    "warning": "",
    "wiki_url": "",
    "category": "Object",
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


DEBUG = False

if DEBUG:
    def dprint(*args):
        print(*args)
else:
    def dprint(*args):
        pass


TIMING_REPORTS = False

if TIMING_REPORTS:
    def tprint(*args):
        print(*args)
else:
    def tprint(*args):
        pass


############ Generic Blender Utility Functions #############


def vertices_hash(vertices):
    start_time = time.time()

    count = len(vertices)
    verts = np.empty(count * 3, dtype=np.float64)
    vertices.foreach_get('co', verts)

    h = xxhash.xxh32(seed=20141025)
    h.update(verts)
    __hash = h.intdigest()

    elapsed_time = time.time() - start_time
    tprint("elapsed_time(vertices_hash)", elapsed_time * 1000)

    # The - 0x7fffffff is because Blender appears to
    # insist on a signed value, and this function
    # does not care, as long as the value is consistent.
    return __hash - 0x7fffffff


############# Blender Event Handlers ##############


def on_object_linked_mesh_prop_updated(self, context):
    # pass
    # cad_outline = self
    ob = context.active_object
    ob_source = ob.mesh_link.source
    ob_source_evaluated = ob_source.evaluated_get(context.evaluated_depsgraph_get())
    # print("Bla:", )

    ob.data = ob_source_evaluated.data.copy()


@persistent
def on_scene_updated(_scene, depsgraph):

    # if not scene.is_cad_outline_enabled:
    #     return

    dprint("mshlnk on_scene_updated")

    def update_linked_meshes():
        for ob in bpy.data.objects:
            # Skip linked objects
            if ob.library is not None:
                continue

            if ob.mesh_link.source is not None and ob.mesh_link.source.visible_get():
                ob_source = ob.mesh_link.source
                ob_source_evaluated = ob_source.evaluated_get(depsgraph)

                cur_hash = vertices_hash(ob.data.vertices)
                new_hash = vertices_hash(ob_source_evaluated.data.vertices)

                if cur_hash != new_hash:
                    ob.data = ob_source_evaluated.data.copy()
                    bpy.context.view_layer.update()

    update_linked_meshes()


############# Blender Extension Classes ##############


class MSHL_ObjectProperties(bpy.types.PropertyGroup):
    source: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Source",
        description="The Source Object that Provides the Base Mesh",
        update=on_object_linked_mesh_prop_updated,
    )


class MSHL_ObjectPanel(bpy.types.Panel):
    """Creates the Mesh Link Panel in the Object properties window"""
    bl_label = "Mesh Link"
    bl_idname = "OBJECT_PT_MESH_LINK"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout

        ob = context.active_object

        row = layout.row()
        row.prop(ob.mesh_link, "source")


classes = [
    MSHL_ObjectProperties,
    MSHL_ObjectPanel,
]


############# Register/Unregister Hooks ##############


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Object.mesh_link = bpy.props.PointerProperty(
        name="Mesh Link Object Properties", type=MSHL_ObjectProperties)

    bpy.app.handlers.depsgraph_update_post.append(on_scene_updated)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    del bpy.types.Object.mesh_link

    bpy.app.handlers.depsgraph_update_post.remove(on_scene_updated)


if __name__ == "__main__":
    register()
