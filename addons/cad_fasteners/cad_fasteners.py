# ##### BEGIN GPL LICENSE BLOCK #####
#
#  CAD Fasteners - Quickly add fasteners to your CAD assemblies
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
    "name": "CAD Fasteners",
    "author": "Marcel Toele",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D",
    "description": "Quickly add fasteners to your CAD assemblies",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
}

import bpy
import bmesh

from mathutils import Vector, Matrix

############# Generic Python Utility Functions ##############

def flatten(t):
    return [item for sublist in t for item in sublist]

############ Generic Blender Utility Functions #############

def depsgraph_update_objects_find(update):
    objects = []

    if isinstance(update.id.original, bpy.types.Object):
        objects = [update.id.original]
    elif isinstance(update.id.original, bpy.types.Mesh):
        objects = [o for o in bpy.data.objects if o.data == update.id.original]

    return objects

def object_transform_apply(ob):
    # Transform the mesh using the matrix world
    ob.matrix_world = Matrix.Diagonal(Vector((*ob.scale, 1.0)))
    ob.data.transform(ob.matrix_world)
    # Reset matrix to identity
    ob.matrix_world = Matrix()

############ CAD Fasteners Blender Utility Functions #############

from os import path
CAD_FASTENERS_BLEND_FILEPATH = path.join(path.dirname(__file__), "cad_fasteners.blend")

def cad_fast_template_collection_ensure():
    if not "CAD Fastener Templates" in bpy.data.collections:
        with bpy.data.libraries.load(CAD_FASTENERS_BLEND_FILEPATH, link=False) as (data_from, data_to):
            data_to.collections = [c for c in data_from.collections if c == "CAD Fastener Templates"]

        # link collection to scene collection
        for col in data_to.collections:
            if col is not None:
                bpy.context.scene.collection.children.link(col)

def cad_fast_object_template_ensure(ob=None):

    def to_size_designator(diam):
        return ('M%.1f' % diam).replace('.0', '')

    cad_fast_template_collection_ensure()

    if ob != None:
        standard = ob.cad_fast.standard
        size_designator = ob.cad_fast.size_designator
        length = float(ob.cad_fast.length)
    else:
        standard = 'ISO_7380-1'
        size_designator = 'M3'
        length = 5

    diam = float(size_designator[1:])

    standard_info = CAD_FAST_STD_DB[standard]
    drive_type = standard_info['drive_type'] if 'drive_type' in standard_info else 'Torx'
    head_type = standard_info['head_type'] if 'head_type' in standard_info else 'Button Head'
    master_template = standard_info['master_template'] if 'master_template' in standard_info else 'M5 Screw Template'

    ob_fastener_name = 'M%dX%d %s %s Screw' % (diam, length, drive_type, head_type)
    ob_fastener_tpl_name = '%s.tpl' % (ob_fastener_name)

    if not ob_fastener_tpl_name in bpy.data.objects:
        ob_fastener_tpl =  bpy.data.objects[master_template].copy()
        ob_fastener_tpl.name = ob_fastener_tpl_name
        ob_fastener_tpl.data = ob_fastener_tpl.data.copy()
        ob_fastener_tpl.dimensions = Vector((5, 5, (5 / diam) * length))
        object_transform_apply(ob_fastener_tpl)
        ob_fastener_tpl.hide_viewport = False
        col_fasteners = bpy.data.collections["CAD Fastener Templates"]
        col_fasteners.objects.link(ob_fastener_tpl)

        ob_fastener_tpl.modifiers["Head Type"].object = bpy.data.objects[head_type]
        ob_fastener_tpl.modifiers["Drive Type"].object = bpy.data.objects[drive_type]

        bme = bmesh.new()
        ob_evaluated = ob_fastener_tpl.evaluated_get(bpy.context.evaluated_depsgraph_get())
        bme.from_mesh(ob_evaluated.data)
        ob_fastener_tpl.modifiers.clear()
        bme.to_mesh(ob_fastener_tpl.data)
        bme.free()

        ob_fastener_tpl.scale = (diam/5, diam/5, diam/5)
        object_transform_apply(ob_fastener_tpl)

        ob_fastener_tpl.hide_viewport = True

        # Update cad_fast props:
        cad_fast_prop_set(ob_fastener_tpl, 'is_fastener', True)
        cad_fast_prop_set(ob_fastener_tpl, 'standard', standard)
        cad_fast_prop_set(ob_fastener_tpl, 'size_designator', size_designator)
        cad_fast_prop_set(ob_fastener_tpl, 'length', str(int(length)))

    return bpy.data.objects[ob_fastener_tpl_name]

def cad_fast_object_update(ob_fastener, ob_fastener_tpl):
    ob_fastener.name = ob_fastener_tpl.name[:-4]
    me_old = ob_fastener.data
    ob_fastener.data = ob_fastener_tpl.data

    # For existing objects, we set the scaling to 1:
    ob_fastener.scale = (1,1,1)
    # And clear all modifiers:
    ob_fastener.modifiers.clear()

    if me_old.users == 0:
        bpy.data.meshes.remove(me_old, do_unlink=True)

internal_update = False
def cad_fast_prop_set(ob_fastener, prop_name, prop_value):
    global internal_update

    internal_update = True
    setattr(ob_fastener.cad_fast, prop_name, prop_value)
    # ob_fastener.cad_fast[prop_name] = prop_value
    internal_update = False

############# Blender Event Handlers ##############

import re

def on_object_cad_fast_prop_updated(self, context):
    if internal_update:
        return

    cad_fast_props = self

    ob = context.active_object

    if ob != None and ob.cad_fast.is_fastener:
        ob_fastener = ob
        ob_fastener_tpl = cad_fast_object_template_ensure(ob)
        cad_fast_object_update(ob_fastener, ob_fastener_tpl)

        # Clean up stale fastener template objects:
        obs_tpl = bpy.data.collections['CAD Fastener Templates'].objects
        obs_tpl_stale = [ob_tpl for ob_tpl in obs_tpl if ob_tpl.name.endswith(".tpl") and ob_tpl.data.users == 1]
        for ob_tpl_stale in obs_tpl_stale:
            bpy.data.objects.remove(ob_tpl_stale, do_unlink=True)

def on_object_cad_fast_is_fastener_prop_updated(self, context):
    if internal_update:
        return

    cad_fast_props = self

    ob = context.active_object

    if ob != None and ob.cad_fast.is_fastener:
        if re.match('M[^X]*X[^ \s]*.*', ob.name):
            size_designator = re.sub('M([^X]*)X.*', r'M\1', ob.name)
            length = re.sub('M[^X]*X([^ \s]*).*', r'\1', ob.name)
        else:
            size_designator = 'M5'
            length = '10'

        cad_fast_prop_set(ob, 'size_designator', size_designator)
        cad_fast_prop_set(ob, 'length', str(int(length)))

        on_object_cad_fast_prop_updated(self, context)

############# Blender Extension Classes ##############

# (identifier, name, description, icon, number)
CAD_FAST_STD_ENUM = [
    ('ISO_7380-1', "ISO 7380-1 (Hex Button Head)", 'A Metric screw with a Button head and a Hex Socket drive'),
    ('ISO_7380-TX', "ISO 7380-TX (Torx Button Head)", 'A Metric screw with a Button head and a Torx drive'),
]

CAD_FAST_HEAD_TYPES = (
    'Button Head',
)

CAD_FAST_DRIVE_TYPES = (
    'Hex Socket',
    'Torx',
)

CAD_FAST_THREAD_TYPES = (
    'METRIC',
    'UNC',
    'UNF',
    'BSW',
)

CAD_FAST_STD_DB = {
    'ISO_7380-1': {'head_type': 'Button Head', 'drive_type': 'Hex Socket', 'thread_type': 'METRIC', 'has_length': True, 'master_template': 'M5 Screw Template'},
    'ISO_7380-TX': {'head_type': 'Button Head', 'drive_type': 'Torx', 'thread_type': 'METRIC', 'has_length': True, 'master_template': 'M5 Screw Template'},
    'DIN_125A': {'has_length': False}
}

CAD_FAST_METRIC_SIZES_IN = [
    ('M2',   (3,4,5,6,7,8,10,12,14,16,18,20,25,30)),
    ('M2.5', (3,4,5,6,7,8,10,12,14,16,18,20,25,30)),
    ('M3',   (4,5,6,7,8,10,12,14,16,18,20,25,30,35,40,45,50)),
    ('M4',   (5,6,8,10,12,14,16,18,20,25,30,35,40,45,50,55,60)),
    ('M5',   (6,8,10,12,14,16,18,20,25,30,35,40,45,50,55,60,65,70,75,80)),
    ('M6',   (8,10,12,14,16,18,20,25,30,35,40,45,50,55,60,65,70,75,80,90,100,120)),
    ('M8',   (12,14,16,18,20,25,30,35,40,45,50,55,60,65,70,75,80,90,100,120)),
    ('M10',  (16,18,20,25,30,35,40,45,50,55,60,65,70,75,80,90,100,120)),
    ('M12',  (20,25,30,35,40,45,50,55,60,65,70,75,80,90,100,120)),
    ('M14',  (20,25,30,35,40,45,50,55,60,65,70,75,80,90,100,120)),
    ('M16',  (20,25,30,35,40,45,50,55,60,65,70,75,80,90,100,120)),
]

CAD_FAST_METRIC_SIZES = dict(list(map(lambda e: (e[0], list(map(lambda l: (str(l), str(l), ''), e[1]))), CAD_FAST_METRIC_SIZES_IN)))
CAD_FAST_METRIC_D_ENUM = list(map(lambda e: (e[0], e[0], ''), CAD_FAST_METRIC_SIZES_IN))

def cad_fast_d_items_get(self, context):
    cad_fast_props = self

    return CAD_FAST_METRIC_D_ENUM

def cad_fast_l_items_get(self, context):
    cad_fast_props = self

    return CAD_FAST_METRIC_SIZES[cad_fast_props.size_designator]

class CAD_FAST_ObjectProperties(bpy.types.PropertyGroup):
    is_fastener: bpy.props.BoolProperty(
        default=False,
        name="Mark As Fastener",
        description="Mark this object as a screw",
        update=on_object_cad_fast_is_fastener_prop_updated
    )
    standard: bpy.props.EnumProperty(
        name="Standard",
        items=CAD_FAST_STD_ENUM,
        default='ISO_7380-1',
        update=on_object_cad_fast_prop_updated
    )
    size_designator: bpy.props.EnumProperty(
        name="D",
        items=cad_fast_d_items_get,
        update=on_object_cad_fast_prop_updated
    )
    length: bpy.props.EnumProperty(
        name="L",
        items=cad_fast_l_items_get,
        update=on_object_cad_fast_prop_updated
    )

class CAD_FAST_OT_AddNew(bpy.types.Operator):
    bl_idname = "fastener.add"
    bl_label = "Add Fastener"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = """Add a fastener to the scene
"""

    @classmethod
    def poll(cls, context):
        obs_selected = context.selected_objects
        if all(ob.type == "MESH" for ob in obs_selected):
            return True

    def execute(self, context):

        # Create Template and "Linked Duplicate" Object
        ob_fastener_tpl = cad_fast_object_template_ensure()
        ob_fastener = ob_fastener_tpl.copy()
        cad_fast_object_update(ob_fastener, ob_fastener_tpl)

        # Link the new object to the scene:
        col_target = bpy.context.scene.collection
        try:
            active_layer_collection = bpy.context.view_layer.active_layer_collection
            col_target = bpy.data.collections[active_layer_collection.name]
        except:
            pass
        col_target.objects.link(ob_fastener)

        # Move new fastener to 3d cursor, unhide, select and make active:
        ob_fastener.location = bpy.context.scene.cursor.location.copy()
        ob_fastener.hide_viewport = False
        ob_fastener.select_set(True)
        context.view_layer.objects.active = ob_fastener

        return {'FINISHED'}

class CAD_FAST_PT_ObjectPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_label = "CAD Fastener"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0 and all(map(lambda ob: ob.mode != 'EDIT', context.selected_objects))

    def draw(self, context):
        layout = self.layout

        ob = next((o for o in context.selected_objects), None)

        if ob:
            layout.row().prop(ob.cad_fast, 'is_fastener')
            if ob.cad_fast.is_fastener:
                box = layout.row().box()
                box.row().label(text="Type and Dimensions:")
                box.row().prop(ob.cad_fast, 'standard', text="")
                row = box.row()
                row.column().prop(ob.cad_fast, 'size_designator', text='')
                row.column().label(text=' x ')
                row.column().prop(ob.cad_fast, 'length', text='')

classes = [
    CAD_FAST_ObjectProperties,
    CAD_FAST_OT_AddNew,
    CAD_FAST_PT_ObjectPanel
]

############# Register/Unregister Hooks ##############

# Per 2.90 Operators have to be in a menu to be searchable
def menu_func(self, context):
    self.layout.operator(CAD_FAST_OT_AddNew.bl_idname, text="Fastener", icon='PROP_CON')

def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

    bpy.types.Object.cad_fast = bpy.props.PointerProperty(name="CAD Fasteners Object Properties", type=CAD_FAST_ObjectProperties)

def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

    del bpy.types.Object.cad_fast


if __name__ == "__main__":
    register()
