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
import pathlib
from string import Template
from mathutils import Vector, Matrix
from math import pi
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


def clamp(lo, val, hi):
    return max(lo, min(val, hi))


def flatten(t):
    return [item for sublist in t for item in sublist]


def all_members(cls):
    # Try getting all relevant classes in method-resolution order
    mro = list(cls.__mro__)
    mro.reverse()
    members = {}
    for someClass in mro:
        members.update(vars(someClass))
    return members


def all_vars(cls):
    """"Get all non-callable vars, including inherited vars"""

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


class BMeshFromEvaluated(object):
    def __init__(self, ob_src, ob_tgt = None):
        self.ob_src = ob_src
        self.ob_tgt = ob_tgt if ob_tgt is not None else ob_src
        self.bme = bmesh.new()
    def __enter__(self):
        ob_evaluated = self.ob_src.evaluated_get(bpy.context.evaluated_depsgraph_get())
        self.bme.from_mesh(ob_evaluated.data)
        return self.bme
    def __exit__(self, type, value, traceback):
        self.bme.to_mesh(self.ob_tgt.data)
        self.bme.free()


def object_modifiers_apply(ob):
    with BMeshFromEvaluated(ob) as bme:
        ob.modifiers.clear()


def object_transform_apply(ob):
    # Transform the mesh using the matrix world
    ob.matrix_world = Matrix.Diagonal(Vector((*ob.scale, 1.0)))
    ob.data.transform(ob.matrix_world)
    # Reset matrix to identity
    ob.matrix_world = Matrix()


def object_dimensions_from_width_and_height_set(ob, width, height):
    scale = Vector()

    # Collect X-Y scale
    ob.dimensions.x = width
    scale.x = ob.scale.x
    scale.y = scale.x

    # Collect Z scale
    ob.dimensions.z = height
    scale.z = ob.scale.z

    # Apply scale
    ob.scale = scale
    object_transform_apply(ob)


def property_group_as_dict_get(pg):
    return dict(map(lambda e: (e, getattr(pg, e)), dict(pg).keys()))


############ CAD Fasteners Blender Utility Functions #############


CAD_FASTENERS_BLEND_FILENAME = "cad_fasteners.blend"
CAD_FASTENERS_BLEND_FILEPATH = path.join(
    path.dirname(__file__), CAD_FASTENERS_BLEND_FILENAME)

def cad_fast_template_file_timestamp_get():
    return int(pathlib.Path(CAD_FASTENERS_BLEND_FILEPATH).stat().st_mtime)


def cad_fast_collection_import(col_parent, col_name):
    # load collection from templates file
    with bpy.data.libraries.load(CAD_FASTENERS_BLEND_FILEPATH, link=False) as (data_from, data_to):
        data_to.collections = [col_name]

    # link collection to parent collection
    col_parent.children.link(data_to.collections[0])


def cad_fast_template_collection_ensure():
    if bpy.data.filepath.endswith(CAD_FASTENERS_BLEND_FILENAME):
        return

    if cad_fast_template_file_timestamp_get() <= bpy.context.scene.cad_fasteners_blend_timestamp:
        return

    if not "CAD Fastener Templates" in bpy.data.collections:
        cad_fast_collection_import(
            bpy.context.scene.collection, "CAD Fastener Templates")
    elif "CAD Fastener Master Templates" in bpy.data.collections:
        col_master = bpy.data.collections["CAD Fastener Master Templates"]
        collection_delete(col_master)

        cad_fast_collection_import(
            bpy.data.collections["CAD Fastener Templates"], "CAD Fastener Master Templates")

    # After successful import, update the stored timestamp:
    bpy.context.scene.cad_fasteners_blend_timestamp = cad_fast_template_file_timestamp_get()


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
    def unset_display_props(ob):
        ob.data.property_unset("auto_smooth_angle")

        # 'Satisfier' compromise:
        if 'cad_outline' in ob:
            ob.cad_outline.property_unset("sharp_angle")

    if internal_update:
        return

    cad_fast_props = self

    ob = context.active_object

    if ob != None and ob.cad_fast.is_fastener:
        unset_display_props(ob)
        ob_fastener = ob
        ob_fastener_tpl = cad_fast_object_template_ensure(ob)
        cad_fast_object_update(ob_fastener, ob_fastener_tpl)

        # Clean up stale fastener template objects:
        obs_tpl = bpy.data.collections['CAD Fastener Templates'].objects
        obs_tpl_stale = [ob_tpl for ob_tpl in obs_tpl if ob_tpl.name.endswith(
            ".tpl") and ob_tpl.data.users <= 1]
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
        elif re.match('M[0-9]+ Nut.*', ob.name):
            cad_fast_prop_set(ob, 'standard', 'DIN_934-1')
            size_designator = re.sub('M([0-9]+) Nut.*', r'M\1', ob.name)
            length = '10'
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
    def func(cls, name):
        members = all_members(cls)
        return name in members and callable(getattr(cls, name))

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

            if cls.func('construct'):
                cls.construct(ob_fastener_tpl, ob)

            ob_fastener_tpl.hide_viewport = False
            col_fasteners = bpy.data.collections["CAD Fastener Templates"]
            col_fasteners.objects.link(ob_fastener_tpl)

            with BMeshFromEvaluated(ob_fastener_tpl) as bme:
                if cls.func('cleanup'):
                    cls.cleanup(ob_fastener_tpl, ob)

            ob_fastener_tpl.hide_viewport = True

            # Update cad_fast props:
            cad_fast_prop_set(ob_fastener_tpl, 'is_fastener', True)
            cad_fast_prop_set(ob_fastener_tpl, 'standard', cls.standard)
            cad_fast_prop_set(
                ob_fastener_tpl, 'size_designator', cls.attr(ob, "size_designator"))
            if cls.has_length:
                cad_fast_prop_set(ob_fastener_tpl, 'length',
                                  str(cls.attr(ob, "length")))

        ob_fastener_tpl = bpy.data.objects[ob_fastener_tpl_name]

        # CAVEAT REFACTOR: This must happen always, so existing objects can be finetuned:
        if cls.func('update'):
            cls.update(ob_fastener_tpl, ob)

        return bpy.data.objects[ob_fastener_tpl_name]


class Metric:
    # default size_designator
    size_designator = 'M3'

    @classmethod
    def diameter_get(cls, size_designator):
        return float(size_designator[1:])


class Screw(Fastener):
    name_template = '${size_designator}X${length} ${drive_type} ${head_type} Screw'
    head_type = None
    drive_type = None
    drive_offset = 0
    has_length = True
    # default length
    length = 8

    @classmethod
    def screw_head_construct(cls, size_designator):
        ob_head = bpy.data.objects[cls.head_type]
        ob_head.hide_viewport = False

        ob_head_tmp = bpy.data.objects.new('temp-screw-head', ob_head.data.copy())

        # BMeshFromEvaluated reads evaluated mesh from ob_head and writes to ob_head_tmp.
        with BMeshFromEvaluated(ob_head, ob_head_tmp) as bme:
            pass

        ob_head.hide_viewport = True

        width, height = cls.head_dim_get(size_designator)
        object_dimensions_from_width_and_height_set(ob_head_tmp, width, height)

        # Heads should be at origin, but this allows for absolute (AKA non-scaled)
        # fine-tuned offsets to avoid Boolean mess ups:
        ob_head_tmp.matrix_world = Matrix.Translation(ob_head.location.copy())

        return ob_head_tmp

    @classmethod
    def screw_drive_cutter_construct(cls, size_designator):
        diam = cls.diameter_get(size_designator)
        scale_factor = diam / 5

        ob_drive_cutter = bpy.data.objects[cls.drive_type]
        ob_drive_cutter.hide_viewport = False

        ob_drive_cutter_tmp = bpy.data.objects.new('temp-drive-cutter', ob_drive_cutter.data.copy())

        ob_drive_cutter_tmp.scale = (scale_factor, scale_factor, scale_factor)
        object_transform_apply(ob_drive_cutter_tmp)

        # S for Socket or Slot (depending on drive type)
        s_width = cls.s_dim_get(size_designator)
        object_dimensions_from_width_and_height_set(ob_drive_cutter_tmp, s_width, ob_drive_cutter_tmp.dimensions.z)

        if cls.drive_offset != 0:
            if cls.head_type is not None:
                _, head_height = cls.head_dim_get(size_designator)
                ob_drive_cutter_tmp.location.z = head_height
            else:
                ob_drive_cutter_tmp.location.z = cls.drive_offset * scale_factor

        ob_drive_cutter.hide_viewport = True

        return ob_drive_cutter_tmp

    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        size_designator = cls.attr(ob, "size_designator")
        diam = cls.diameter_get(size_designator)
        length = float(cls.attr(ob, "length"))

        ob_fastener_tpl.dimensions = Vector((diam, diam, length))
        object_transform_apply(ob_fastener_tpl)
        scale_factor = diam / 5
        ob_fastener_tpl.modifiers["Bottom Bevel"].width = 0.9 * scale_factor
        ob_fastener_tpl.modifiers["Top Bevel"].width = 0.2 * scale_factor

        if cls.head_type is not None:
            ob_head = cls.screw_head_construct(size_designator)
            mod_head = ob_fastener_tpl.modifiers.new("Head", type='BOOLEAN')
            mod_head.operation = 'UNION'
            mod_head.object = ob_head

        if cls.drive_type is not None:
            mod_drive = ob_fastener_tpl.modifiers.new("Drive", type='BOOLEAN')
            mod_drive.operation = 'DIFFERENCE'
            mod_drive.object = cls.screw_drive_cutter_construct(size_designator)

    @classmethod
    def cleanup(cls, ob_fastener_tpl, ob):
        for mod in ob_fastener_tpl.modifiers:
            if mod.type == 'BOOLEAN' and mod.object is not None:
                bpy.data.objects.remove(mod.object, do_unlink=True)

        ob_fastener_tpl.modifiers.clear()


class MetricScrew(Screw, Metric):
    master_template = 'M5 Screw Template'


class RoundScrewHead:
    @classmethod
    def head_dim_get(cls, size_designator):
        dim = cls.dimensions[size_designator]
        return (dim['dk'], dim['k'])


class ButtonHead(RoundScrewHead):
    head_type = 'Button Head'
    drive_offset = -2.8


class CountersunkHead(RoundScrewHead):
    head_type = 'Countersunk Head'
    drive_offset = 0

    @classmethod
    def update(cls, ob_fastener_tpl, ob):
        sharp_angle = 15

        ob_fastener_tpl.data.auto_smooth_angle = sharp_angle * (pi / 180)
        if ob:  # Also update existing object
            ob.data.auto_smooth_angle = sharp_angle * (pi / 180)

        # 'Satisfier' compromise:
        if 'cad_outline' in ob_fastener_tpl:
            ob_fastener_tpl.cad_outline.sharp_angle = sharp_angle
            if ob:  # Also update existing object
                ob.cad_outline.sharp_angle = sharp_angle


class SocketDrive:
    @classmethod
    def s_dim_get(cls, size_designator):
        dim = cls.dimensions[size_designator]
        return dim['s']


class HexHead:
    head_type = 'Hex Head'
    drive_offset = -2

    @classmethod
    def head_dim_get(cls, size_designator):
        dim = cls.dimensions[size_designator]
        return (dim['s'], dim['k'])


class ISO_7380(ButtonHead, MetricScrew, SocketDrive):
    dimensions = {
        # autopep8: off
        'M2':   {'dk': 3.5,  'k': 1.3,  's': 1.3},
        'M2.5': {'dk': 4.7,  'k': 1.5,  's': 1.5},
        'M3':   {'dk': 5.7,  'k': 1.65, 's': 2},
        'M4':   {'dk': 7.6,  'k': 2.2,  's': 2.5},
        'M5':   {'dk': 9.5,  'k': 2.75, 's': 3},
        'M6':   {'dk': 10.5, 'k': 3.3,  's': 4},
        'M8':   {'dk': 14,   'k': 4.4,  's': 5},
        'M10':  {'dk': 17.5, 'k': 5.5,  's': 6},
        'M12':  {'dk': 21,   'k': 6.6,  's': 8},
        'M16':  {'dk': 28,   'k': 8.8,  's': 10},
        # autopep8: on
    }


class ISO_7380_1(ISO_7380):
    standard = 'ISO_7380-1'
    drive_type = 'Hex Socket'


class ISO_7380_TX(ISO_7380):
    standard = 'ISO_7380-TX'
    drive_type = 'Torx'


class DIN_933_1(HexHead, MetricScrew):
    name_template = '${size_designator}X${length} ${head_type} Cap Screw'
    standard = 'DIN_933-1'
    dimensions = {
        # autopep8: off
        'M2':   {'s': 4,   'k': 1.4},
        'M2.5': {'s': 5,   'k': 1.7},
        'M3':   {'s': 5.5, 'k': 2},
        'M4':   {'s': 7,   'k': 2.8},
        'M5':   {'s': 8,   'k': 3.5},
        'M6':   {'s': 10,  'k': 4},
        'M8':   {'s': 13,  'k': 5.3},
        'M10':  {'s': 17,  'k': 6.4},
        'M12':  {'s': 19,  'k': 7.5},
        'M14':  {'s': 22,  'k': 8.8},
        'M16':  {'s': 24,  'k': 10},
        # autopep8: on
    }


class ISO_10642(CountersunkHead, MetricScrew, SocketDrive):
    dimensions = {
        # autopep8: off
        'M2':   {'dk': 4,  'k': 1.2, 's': 1.25},
        'M2.5': {'dk': 5,  'k': 1.5, 's': 1.5},
        'M3':   {'dk': 6,  'k': 1.7, 's': 2},
        'M4':   {'dk': 8,  'k': 2.3, 's': 2.5},
        'M5':   {'dk': 10, 'k': 2.8, 's': 3},
        'M6':   {'dk': 12, 'k': 3.3, 's': 4},
        'M8':   {'dk': 16, 'k': 4.4, 's': 5},
        'M10':  {'dk': 20, 'k': 5.5, 's': 6},
        'M12':  {'dk': 24, 'k': 6.5, 's': 8},
        'M14':  {'dk': 27, 'k': 7,   's': 10},
        'M16':  {'dk': 30, 'k': 7.5, 's': 10},
        # autopep8: on
    }


class ISO_10642_HX(ISO_10642):
    standard = 'ISO_10642'
    drive_type = 'Hex Socket'


class ISO_10642_TX(ISO_10642):
    standard = 'ISO_10642-TX'
    drive_type = 'Torx'


class ISO_4026(MetricScrew, SocketDrive):
    name_template = '${size_designator}X${length} Set Screw'
    standard = 'ISO_4026'
    drive_type = 'Hex Socket'
    dimensions = {
        # autopep8: off
        'M2':   {'s': 0.9},
        'M2.5': {'s': 1.3},
        'M3':   {'s': 1.5},
        'M4':   {'s': 2},
        'M5':   {'s': 2.5},
        'M6':   {'s': 3},
        'M8':   {'s': 4},
        'M10':  {'s': 5},
        'M12':  {'s': 6},
        'M14':  {'s': 6},
        'M16':  {'s': 8},
        # autopep8: on
    }


class Washer(Fastener):
    name_template = '${size_designator} Washer'
    has_length = False

    @classmethod
    def dim_get(cls, size_designator):
        dim = cls.dimensions[size_designator]
        return (dim['D'], dim['d'], dim['h'])

    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        size_designator = cls.attr(ob, "size_designator")
        D, d, h = cls.dim_get(size_designator)
        ob_fastener_tpl.dimensions = Vector((D, D, h))
        object_transform_apply(ob_fastener_tpl)
        ob_fastener_tpl.modifiers['Solidify'].thickness = (D - d) / 2


class MetricWasher(Washer, Metric):
    master_template = 'M5 Washer (DIN 125A)'


class DIN_125A(MetricWasher):
    standard = 'DIN_125A'
    dimensions = {
        # autopep8: off
        'M2':   {'D': 5,  'd': 2.2,  'h': 0.3},
        'M2.5': {'D': 6,  'd': 2.7,  'h': 0.5},
        'M3':   {'D': 7,  'd': 3.2,  'h': 0.5},
        'M4':   {'D': 9,  'd': 4.3,  'h': 0.8},
        'M5':   {'D': 10, 'd': 5.3,  'h': 1},
        'M6':   {'D': 12, 'd': 6.4,  'h': 1.6},
        'M8':   {'D': 16, 'd': 8.4,  'h': 1.6},
        'M10':  {'D': 20, 'd': 10.5, 'h': 2},
        'M12':  {'D': 24, 'd': 13,   'h': 2.5},
        'M14':  {'D': 28, 'd': 15,   'h': 2.5},
        'M16':  {'D': 30, 'd': 17,   'h': 3},
        # autopep8: on
    }


class Nut(Fastener):
    name_template = '${size_designator} Nut'
    has_length = False

    @classmethod
    def dim_get(cls, size_designator):
        dim = cls.dimensions[size_designator]
        return (dim['s'], dim['h'])

    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        size_designator = cls.attr(ob, "size_designator")
        width, height = cls.dim_get(size_designator)
        object_dimensions_from_width_and_height_set(ob_fastener_tpl, width, height)


class MetricNut(Nut, Metric):
    master_template = 'M5 Nut (DIN 934)'


class DIN_934_1(MetricNut):
    # Link: https://drive.google.com/file/d/1G7Et-bce98nLzvAG2R9oFskMq9HqILlK/view?usp=sharing
    standard = 'DIN_934-1'
    dimensions = {
        # autopep8: off
        'M2':   {'s': 4,   'h': 1.6},
        'M2.5': {'s': 5,   'h': 2},
        'M3':   {'s': 5.5, 'h': 2.4},
        'M4':   {'s': 7,   'h': 3.2},
        'M5':   {'s': 8,   'h': 4},
        'M6':   {'s': 10,  'h': 5},
        'M8':   {'s': 13,  'h': 6.5},
        'M10':  {'s': 17,  'h': 8},
        'M12':  {'s': 19,  'h': 10},
        'M14':  {'s': 22,  'h': 11},
        'M16':  {'s': 24,  'h': 13},
        # autopep8: on
    }


class T_NUT(MetricNut):
    @classmethod
    def construct(cls, ob_fastener_tpl, ob):
        size_designator = cls.attr(ob, "size_designator")
        diam = 0.9 * cls.diameter_get(size_designator) # 0.9 -> minor thread approximation

        ob_bore = bpy.data.collections['CAD Fastener Bool Tools'].objects['Bore']
        ob_bore.dimensions = (diam, diam, 10)
        object_transform_apply(ob_bore)


class DROP_IN_T_NUT_2020(T_NUT):
    name_template = '2020 ${size_designator} Drop In T-Nut'
    master_template = '2020 Drop In T-Nut'
    standard = 'DROP_IN_T_NUT_2020'
    dimensions = {
        # autopep8: off
        'M3':   {'s': 5.5, 'h': 2.4},
        'M4':   {'s': 7,   'h': 3.2},
        'M5':   {'s': 8,   'h': 4},
        # autopep8: on
    }


class SLIDING_T_NUT_2020(T_NUT):
    name_template = '2020 ${size_designator} Sliding T-Nut'
    master_template = '2020 Sliding T-Nut'
    standard = 'SLIDING_T_NUT_2020'
    dimensions = {
        # autopep8: off
        'M3':   {'s': 9.8, 'h': 4.5},
        'M4':   {'s': 9.8, 'h': 4.5},
        'M5':   {'s': 9.8, 'h': 4.5},
        'M6':   {'s': 9.8, 'h': 4.5},
        # autopep8: on
    }


# (identifier, name, description, icon, number)
CAD_FAST_STD_ENUM = [
    ('ISO_7380-1', "Hex Button Head (ISO 7380-1)",
     'A Metric screw with a Button head and a Hex Socket drive'),
    ('ISO_10642', "Hex Countersunk (ISO 10642)",
     'A Metric screw with a Countersunk head and a Hex drive'),
    ('DIN_933-1', "Hex Cap Screw (DIN 933-1)",
     'A Metric hex cap screw with external hex drive'),
    ('ISO_7380-TX', "Torx Button Head (ISO 7380-TX)",
     'A Metric screw with a Button head and a Torx drive'),
    ('ISO_10642-TX', "Torx Countersunk (ISO 10642-TX)",
     'A Metric screw with a Countersunk head and a Torx drive'),
    ('DIN_125A', "Washer (DIN 125A)", 'A Metric washer'),
    ('DIN_934-1', "Nut (DIN 934-1)", 'A Metric nut'),
    ('ISO_4026', "Set Screw (ISO 4026)", 'A Metric set screw'),
    ('DROP_IN_T_NUT_2020', "Drop In T-Nut (2020)", 'A Drop In T-Nut for a 2020 extrusion'),
    ('SLIDING_T_NUT_2020', "Sliding T-Nut (2020)", 'A Sliding T-Nut for a 2020 extrusion'),
]

CAD_FAST_STD_TYPES = {
    'ISO_7380-1': ISO_7380_1,
    'ISO_7380-TX': ISO_7380_TX,
    'ISO_10642': ISO_10642_HX,
    'ISO_10642-TX': ISO_10642_TX,
    'DIN_125A': DIN_125A,
    'DIN_934-1': DIN_934_1,
    'DIN_933-1': DIN_933_1,
    'ISO_4026': ISO_4026,
    'DROP_IN_T_NUT_2020': DROP_IN_T_NUT_2020,
    'SLIDING_T_NUT_2020': SLIDING_T_NUT_2020,
}

CAD_FAST_METRIC_AVAILABLE_LENGTHS_IN = {
    'M2': (3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 30),
    'M2.5': (3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 30),
    'M3': (4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50),
    'M4': (5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60),
    'M5': (6, 8, 10, 12, 14, 16, 18, 20, 25,
            30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80),
    'M6': (8, 10, 12, 14, 16, 18, 20, 25, 30, 35,
            40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120),
    'M8': (12, 14, 16, 18, 20, 25, 30, 35, 40,
            45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120),
    'M10': (16, 18, 20, 25, 30, 35, 40, 45,
             50, 55, 60, 65, 70, 75, 80, 90, 100, 120),
    'M12': (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120),
    'M14': (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120),
    'M16': (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 120),
}

# autopep8: off
CAD_FAST_METRIC_AVAILABLE_LENGTHS = dict([
    # sd for size_designator, l for length
    (sd, [(str(l), str(l), '') for l in lengths])
        for sd, lengths in CAD_FAST_METRIC_AVAILABLE_LENGTHS_IN.items() 
])
# autopep8: on

CAD_FAST_METRIC_D_ENUM = list(
    map(lambda e: (e[0], e[0], ''), CAD_FAST_METRIC_AVAILABLE_LENGTHS_IN))

# autopep8: off
CAD_FAST_METRIC_AVAILABLE_SIZES = dict([
    # sd for size_designator
    (std_name, [(sd, sd, '') for sd in std_cls.dimensions.keys()])
        for std_name, std_cls in CAD_FAST_STD_TYPES.items()
])
# autopep8: on

def cad_fast_size_designator_get(self):
    return clamp(0, self['size_designator'], len(CAD_FAST_METRIC_AVAILABLE_SIZES[self.standard]) - 1)

def cad_fast_size_designator_set(self, value):
    self['size_designator'] = value

def cad_fast_d_items_get(self, context):
    cad_fast_props = self

    return CAD_FAST_METRIC_AVAILABLE_SIZES[cad_fast_props.standard]


def cad_fast_l_items_get(self, context):
    cad_fast_props = self

    return CAD_FAST_METRIC_AVAILABLE_LENGTHS[cad_fast_props.size_designator]


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
        get=cad_fast_size_designator_get,
        set=cad_fast_size_designator_set,
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

        bpy.ops.object.select_all(action='DESELECT')

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


class CAD_FAST_PT_ItemNPanel(bpy.types.Panel):
    """Creates the CAD Fasteners Panel in the Item Tab in the N-Panel of the 3D View"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_label = "CAD Fastener"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ob = next((o for o in context.selected_objects), None)

        return ob and ob.cad_fast.is_fastener and ob.mode != 'EDIT'

    def draw(self, context):
        layout = self.layout

        ob = next((o for o in context.selected_objects), None)

        if ob:
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


class CAD_FAST_PT_PropertiesWindowPanel(bpy.types.Panel):
    """Creates the CAD Fasteners Panel in the Object properties window"""
    bl_label = "CAD Fasteners"
    bl_idname = "OBJECT_PT_CAD_FAST"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout

        ob = context.active_object

        if ob:
            layout.row().prop(ob.cad_fast, 'is_fastener')


classes = [
    CAD_FAST_ObjectProperties,
    CAD_FAST_OT_AddNew,
    CAD_FAST_PT_ItemNPanel,
    CAD_FAST_PT_PropertiesWindowPanel,
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

    bpy.types.Scene.cad_fasteners_blend_timestamp = bpy.props.IntProperty(
        name="cad_fasteners_blend_timestamp",
        description="Time stamp of the included cad_fasteners.blend file objects",
        default=0
    )


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

    del bpy.types.Object.cad_fast
    del bpy.types.Scene.cad_fasteners_blend_timestamp

if __name__ == "__main__":
    register()
