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

import re
from os import path
from string import Template
from mathutils import Vector, Matrix
import bmesh
import bpy


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


############# Generic Python Utility Functions ##############


def flatten(t):
    return [item for sublist in t for item in sublist]


def all_vars(cls):
    """"Get all non-callable vars, including inherited vars"""
    def all_members(cls):
        # Try getting all relevant classes in method-resolution order
        mro = list(cls.__mro__)
        mro.reverse()
        members = {}
        for someClass in mro:
            members.update(vars(someClass))
        return members

    return dict(filter(lambda e: not (e[0].startswith("__") or callable(
        getattr(cls, e[0]))), all_members(cls).items()))


############ Generic Blender Utility Functions #############


def collection_delete(col):
    for ob in col.objects:
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in col.children:
        collection_delete(c)
    bpy.data.collections.remove(col, do_unlink=True)


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


def property_group_as_dict_get(pg):
    return dict(map(lambda e: (e, getattr(pg, e)), dict(pg).keys()))


############ CAD Fasteners Blender Utility Functions #############


CAD_FASTENERS_BLEND_FILENAME = "cad_fasteners.blend"
CAD_FASTENERS_BLEND_FILEPATH = path.join(
    path.dirname(__file__), CAD_FASTENERS_BLEND_FILENAME)


def cad_fast_collection_import(col_parent, col_name):
    # load collection from templates file
    with bpy.data.libraries.load(CAD_FASTENERS_BLEND_FILEPATH, link=False) as (data_from, data_to):
        data_to.collections = [col_name]

    # link collection to parent collection
    col_parent.children.link(data_to.collections[0])


def cad_fast_template_collection_ensure():
    if bpy.data.filepath.endswith(CAD_FASTENERS_BLEND_FILENAME):
        return

    if not "CAD Fastener Templates" in bpy.data.collections:
        cad_fast_collection_import(
            bpy.context.scene.collection, "CAD Fastener Templates")
    elif "CAD Fastener Master Templates" in bpy.data.collections:
        col_master = bpy.data.collections["CAD Fastener Master Templates"]
        collection_delete(col_master)

        cad_fast_collection_import(
            bpy.data.collections["CAD Fastener Templates"], "CAD Fastener Master Templates")


def cad_fast_object_template_ensure(ob=None):

    cad_fast_type = CAD_FAST_STD_TYPES[ob.cad_fast.standard] if ob is not None else CAD_FAST_STD_TYPES['ISO_7380-1']

    return cad_fast_type.template_ensure(ob)


def cad_fast_object_update(ob_fastener, ob_fastener_tpl):
    ob_fastener.name = ob_fastener_tpl.name[:-4]
    me_old = ob_fastener.data
    ob_fastener.data = ob_fastener_tpl.data

    # For existing objects, we set the scaling to 1:
    ob_fastener.scale = (1, 1, 1)
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
        obs_tpl_stale = [ob_tpl for ob_tpl in obs_tpl if ob_tpl.name.endswith(
            ".tpl") and ob_tpl.data.users == 1]
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


# Better than int(x), because:
#   x   |   int(x)   |   without_trailing_zero(x)
#  1.0  |     1      |            1
#  2.5  |     2      |           2.5
def without_trailing_zero(x):
    return ('%.1f' % x).replace('.0', '')


class Fastener:
    name_template = 'Fastener'
    has_length = False

    @classmethod
    def template_name_get(cls, ob=None):
        all_cls_vars = all_vars(cls)
        all_ob_vars = property_group_as_dict_get(
            ob.cad_fast) if ob is not None else {}
        all_tpl_vars = {}
        all_tpl_vars.update(all_cls_vars)
        all_tpl_vars.update(all_ob_vars)
        return '%s.tpl' % Template(cls.name_template).substitute(**all_tpl_vars)

    @classmethod
    def attr(cls, ob, name):
        return getattr(ob.cad_fast, name) if ob is not None and name in ob.cad_fast else all_vars(cls)[name]

    @classmethod
    def template_ensure(cls, ob=None):

        cad_fast_template_collection_ensure()

        ob_fastener_tpl_name = cls.template_name_get(ob)

        # print("template_ensure", ob_fastener_tpl_name)

        if not ob_fastener_tpl_name in bpy.data.objects:
            # print("  `--> does not exist: Creating...")
            ob_fastener_tpl = bpy.data.objects[cls.master_template].copy()
            ob_fastener_tpl.name = ob_fastener_tpl_name
            ob_fastener_tpl.data = ob_fastener_tpl.data.copy()

            cls.construct(ob_fastener_tpl, ob)

            ob_fastener_tpl.hide_viewport = False
            col_fasteners = bpy.data.collections["CAD Fastener Templates"]
            col_fasteners.objects.link(ob_fastener_tpl)

            bme = bmesh.new()
            ob_evaluated = ob_fastener_tpl.evaluated_get(
                bpy.context.evaluated_depsgraph_get())
            bme.from_mesh(ob_evaluated.data)
            ob_fastener_tpl.modifiers.clear()
            bme.to_mesh(ob_fastener_tpl.data)
            bme.free()

            cls.scale(ob_fastener_tpl, ob)

            ob_fastener_tpl.hide_viewport = True

            # Update cad_fast props:
            cad_fast_prop_set(ob_fastener_tpl, 'is_fastener', True)
            cad_fast_prop_set(ob_fastener_tpl, 'standard', cls.standard)
            cad_fast_prop_set(
                ob_fastener_tpl, 'size_designator', cls.attr(ob, "size_designator"))
            if cls.has_length:
                cad_fast_prop_set(ob_fastener_tpl, 'length',
                                  str(cls.attr(ob, "length")))

        return bpy.data.objects[ob_fastener_tpl_name]


class Metric:
    # default size_designator
    size_designator = 'M3'

    @classmethod
    def diameter_get(cls, ob):
        return float(cls.attr(ob, "size_designator")[1:])


class Screw(Fastener):
    name_template = '${size_designator}X${length} ${drive_type} ${head_type} Screw'
    has_length = True
    # default length
    length = 8

    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        diam = cls.diameter_get(ob)
        length = float(cls.attr(ob, "length"))

        # if has_length:
        ob_fastener_tpl.dimensions = Vector(
            (5, 5, (5 / diam) * length))
        object_transform_apply(ob_fastener_tpl)
        # if head_type != None:
        ob_fastener_tpl.modifiers["Head Type"].object = bpy.data.objects[cls.head_type]
        # if drive_type != None:
        ob_fastener_tpl.modifiers["Drive Type"].object = bpy.data.objects[cls.drive_type]
        bpy.data.objects[cls.drive_type].location.z = cls.drive_offset

    @classmethod
    def scale(cls, ob_fastener_tpl, ob):
        diam = cls.diameter_get(ob)
        ob_fastener_tpl.scale = (diam / 5, diam / 5, diam / 5)
        object_transform_apply(ob_fastener_tpl)


class MetricScrew(Screw, Metric):
    master_template = 'M5 Screw Template'


class ButtonHead:
    head_type = 'Button Head'
    drive_offset = 0


class CountersunkHead:
    head_type = 'Countersunk Head'
    drive_offset = -2.8


class ISO_7380_1(MetricScrew, ButtonHead):
    standard = 'ISO_7380-1'
    drive_type = 'Hex Socket'


class ISO_7380_TX(MetricScrew, ButtonHead):
    standard = 'ISO_7380-TX'
    drive_type = 'Torx'


class ISO_10642(MetricScrew, CountersunkHead):
    standard = 'ISO_10642'
    drive_type = 'Hex Socket'


class ISO_10642_TX(MetricScrew, CountersunkHead):
    standard = 'ISO_10642-TX'
    drive_type = 'Torx'


class Washer(Fastener):
    name_template = '${size_designator} Washer'
    has_length = False

    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        pass

    @classmethod
    def scale(cls, ob_fastener_tpl, ob):
        diam = cls.diameter_get(ob)
        ob_fastener_tpl.scale = (diam / 5, diam / 5, diam / 5)
        object_transform_apply(ob_fastener_tpl)


class MetricWasher(Washer, Metric):
    master_template = 'M5 Washer (DIN 125A)'


class DIN_125A(MetricWasher):
    standard = 'DIN_125A'


class Nut(Fastener):
    name_template = '${size_designator} Nut'
    has_length = False

    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        pass

    @classmethod
    def scale(cls, ob_fastener_tpl, ob):
        size_designator = cls.attr(ob, "size_designator")
        dimensions = cls.dimensions[size_designator]
        scale = Vector()

        # Collect X-Y scale
        ob_fastener_tpl.dimensions.x = dimensions['s']
        scale.x = ob_fastener_tpl.scale.x
        scale.y = scale.x

        # Collect Z scale
        ob_fastener_tpl.dimensions.z = dimensions['m']
        scale.z = ob_fastener_tpl.scale.z

        # Apply scale
        ob_fastener_tpl.scale = scale
        object_transform_apply(ob_fastener_tpl)


class MetricNut(Nut, Metric):
    master_template = 'M5 Nut (DIN 934)'


class DIN_934_1(MetricNut):
    # Link: https://drive.google.com/file/d/1G7Et-bce98nLzvAG2R9oFskMq9HqILlK/view?usp=sharing
    standard = 'DIN_934-1'
    dimensions = {
        # autopep8: off
        'M2':   {'s': 4,   'm': 1.6},
        'M2.5': {'s': 5,   'm': 2},
        'M3':   {'s': 5.5, 'm': 2.4},
        'M4':   {'s': 7,   'm': 3.2},
        'M5':   {'s': 8,   'm': 4},
        'M6':   {'s': 10,  'm': 5},
        'M8':   {'s': 13,  'm': 6.5},
        'M10':  {'s': 17,  'm': 8},
        'M12':  {'s': 19,  'm': 10},
        'M14':  {'s': 22,  'm': 11},
        'M16':  {'s': 24,  'm': 13},
        # autopep8: on
    }


# (identifier, name, description, icon, number)
CAD_FAST_STD_ENUM = [
    ('ISO_7380-1', "Hex Button Head (ISO 7380-1)",
     'A Metric screw with a Button head and a Hex Socket drive'),
    ('ISO_10642', "Hex Countersunk (ISO 10642)",
     'A Metric screw with a Countersunk head and a Hex drive'),
    ('ISO_7380-TX', "Torx Button Head (ISO 7380-TX)",
     'A Metric screw with a Button head and a Torx drive'),
    ('ISO_10642-TX', "Torx Countersunk (ISO 10642-TX)",
     'A Metric screw with a Countersunk head and a Torx drive'),
    ('DIN_125A', "Washer (DIN 125A)", 'A Metric washer'),
    ('DIN_934-1', "Nut (DIN 934-1)", 'A Metric nut'),
]

CAD_FAST_STD_TYPES = {
    'ISO_7380-1': ISO_7380_1,
    'ISO_7380-TX': ISO_7380_TX,
    'ISO_10642': ISO_10642,
    'ISO_10642-TX': ISO_10642_TX,
    'DIN_125A': DIN_125A,
    'DIN_934-1': DIN_934_1,
}

CAD_FAST_METRIC_SIZES_IN = [
    ('M2', (3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 30)),
    ('M2.5', (3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 30)),
    ('M3', (4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50)),
    ('M4', (5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60)),
    ('M5', (6, 8, 10, 12, 14, 16, 18, 20, 25,
            30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80)),
    ('M6', (8, 10, 12, 14, 16, 18, 20, 25, 30, 35,
            40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120)),
    ('M8', (12, 14, 16, 18, 20, 25, 30, 35, 40,
            45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120)),
    ('M10', (16, 18, 20, 25, 30, 35, 40, 45,
             50, 55, 60, 65, 70, 75, 80, 90, 100, 120)),
    ('M12', (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120)),
    ('M14', (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120)),
    ('M16', (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120)),
]

CAD_FAST_METRIC_SIZES = dict(list(map(lambda e: (e[0], list(
    map(lambda l: (str(l), str(l), ''), e[1]))), CAD_FAST_METRIC_SIZES_IN)))
CAD_FAST_METRIC_D_ENUM = list(
    map(lambda e: (e[0], e[0], ''), CAD_FAST_METRIC_SIZES_IN))


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

                if CAD_FAST_STD_TYPES[ob.cad_fast.standard].has_length:
                    row.column().prop(ob.cad_fast, 'size_designator', text='')
                    row.column().label(text=' x ')
                    row.column().prop(ob.cad_fast, 'length', text='')
                else:
                    row.column().prop(ob.cad_fast, 'size_designator', text='Size')


classes = [
    CAD_FAST_ObjectProperties,
    CAD_FAST_OT_AddNew,
    CAD_FAST_PT_ObjectPanel
]


############# Register/Unregister Hooks ##############


# Per 2.90 Operators have to be in a menu to be searchable
def menu_func(self, context):
    self.layout.operator(CAD_FAST_OT_AddNew.bl_idname,
                         text="Fastener", icon='PROP_CON')


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

    bpy.types.Object.cad_fast = bpy.props.PointerProperty(
        name="CAD Fasteners Object Properties", type=CAD_FAST_ObjectProperties)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

    del bpy.types.Object.cad_fast


if __name__ == "__main__":
    register()
