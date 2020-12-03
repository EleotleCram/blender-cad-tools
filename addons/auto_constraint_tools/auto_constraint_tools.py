# ##### BEGIN GPL LICENSE BLOCK #####
#
#  Boolean Constraint Tools - Manage (child-of) constraints of boolean modifier objects
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
    "name": "Boolean Constraint Tools",
    "author": "Marcel Toele",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D",
    "description": "Manage (child-of) constraints of boolean modifier objects",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
}

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector, Matrix

############# Generic Python Utility Functions ##############

def index_of(list, search):
    for i, element in enumerate(list):
        if element == search:
            return i
    return -1

############ Generic Blender Utility Functions #############

def get_all_boolean_modifiers(obj):
    return [m for m in obj.modifiers if m.type == 'BOOLEAN' and m.object != None]

def get_all_childof_constraints(obj):
    return [c for c in obj.constraints if c.type == 'CHILD_OF' and c.target != None]

def get_all_boolean_modifiers_with_active_childof_constraints(obj):
    all_boolean_modifiers = get_all_boolean_modifiers(obj)

    all_boolean_modifiers_with_active_childof_constraints = [
        m for m in all_boolean_modifiers
            if any(map(lambda c: c.target == obj, get_all_childof_constraints(m.object)))
    ]

    print("all_boolean_modifiers_with_active_childof_constraints", all_boolean_modifiers_with_active_childof_constraints)

    return all_boolean_modifiers_with_active_childof_constraints

def get_boolean_childof_constraint(obj, modifier):
    childof_constraints = get_all_childof_constraints(modifier.object)
    # print("childof_constraints", childof_constraints)
    return next((c for c in childof_constraints if c.target == obj), None)

def remove_boolean_childof_constraint(obj, modifier):
    constraint = get_boolean_childof_constraint(obj, modifier)
    if constraint:
        matrix_world = modifier.object.matrix_world.copy()
        modifier.object.constraints.remove(constraint)
        modifier.object.matrix_world = matrix_world

def calc_matrix_world(obj):
    if obj.parent is None:
        matrix_world = obj.matrix_basis

    else:
        matrix_world = obj.parent.matrix_world * \
                           obj.matrix_parent_inverse * \
                           obj.matrix_basis

    return matrix_world

def add_boolean_childof_constraint(obj, modifier):
    if get_boolean_childof_constraint(obj, modifier) == None:
        constraint = modifier.object.constraints.new(type='CHILD_OF')
        if obj.bct.ignore_scale:
            constraint.use_scale_x = False
            constraint.use_scale_y = False
            constraint.use_scale_z = False
            orig_scale = obj.scale.copy()
            obj.scale = Vector((1,1,1))
            constraint.target = obj
            constraint.inverse_matrix = calc_matrix_world(obj).inverted()
            obj.scale = orig_scale
        else:
            constraint.target = obj
            constraint.inverse_matrix = obj.matrix_world.inverted()

def set_boolean_childof_constraint(obj, modifier, value):
    if(value):
        add_boolean_childof_constraint(obj, modifier)
    else:
        remove_boolean_childof_constraint(obj, modifier)

def set_all_boolean_childof_constraints(obj, value):
    for modifier in get_all_boolean_modifiers(obj):
        set_boolean_childof_constraint(obj, modifier, value)

############# Blender Event Handlers ##############

internal_update = False
def on_bool_childof_constraint_prop_updated(self, context):
    if not internal_update:
        obj = context.active_object
        obj.bct.auto_constraint = False
        i = index_of(obj.bct.constraint_children, self)
        all_boolean_modifiers = get_all_boolean_modifiers(obj)
        modifier = all_boolean_modifiers[i]
        set_boolean_childof_constraint(obj, modifier, self.value)

def on_toggle_all_bool_childof_constraint_prop_updated(self, context):
    if not internal_update:
        bct = self
        bct.auto_constraint = False
        obj = context.active_object
        set_all_boolean_childof_constraints(obj, bct.is_childof_constraints_all)

def on_auto_constraint_prop_updated(self, context):
    bct = self
    obj = context.active_object
    if bct.auto_constraint:
        set_all_boolean_childof_constraints(obj, True)

def on_ignore_scale_prop_updated(self, context):
    bct = self
    obj = context.active_object
    all_boolean_modifiers_with_active_childof_constraints = get_all_boolean_modifiers_with_active_childof_constraints(obj)

    for modifier in all_boolean_modifiers_with_active_childof_constraints:
        remove_boolean_childof_constraint(obj, modifier)
        add_boolean_childof_constraint(obj, modifier)


cached_active_object = None

@persistent
def on_scene_updated( scene, depsgraph ):
    # print("Updated", "ctx", dir(bpy.context))

    obj = bpy.context.active_object
    if not obj:
        return

    all_boolean_modifiers = get_all_boolean_modifiers(obj)

    # Make sure there are exactly as many constraint_children as
    # there are objects referenced by the boolean modifiers
    while len(obj.bct.constraint_children) > len(all_boolean_modifiers):
        obj.bct.constraint_children.remove(0)

    while len(obj.bct.constraint_children) < len(all_boolean_modifiers):
        obj.bct.constraint_children.add()

    global cached_active_object
    if cached_active_object != bpy.context.active_object:
        cached_active_object = bpy.context.active_object
        # Active object updated, so apply auto-constraint (if applicable):
        if(obj.bct.auto_constraint):
            set_all_boolean_childof_constraints(obj, True)

    global internal_update
    ######################
    internal_update = True
    ######################
    # Sync the values
    for modifier, constraint_child in zip(all_boolean_modifiers, obj.bct.constraint_children):
        is_boolean_object_constraint_by_obj = get_boolean_childof_constraint(obj, modifier) != None
        # print("is_boolean_object_constraint_by_obj", is_boolean_object_constraint_by_obj)
        constraint_child.value = is_boolean_object_constraint_by_obj

    obj.bct.is_childof_constraints_all = all(map(lambda e: e.value, obj.bct.constraint_children))
    ######################
    internal_update = False
    ######################

############# Blender Extension Classes ##############

class BCT_BooleanChildOfConstraintProperty(bpy.types.PropertyGroup):
    value: bpy.props.BoolProperty(description="Add a child-of constraint to the target object which is parented to the active object", update=on_bool_childof_constraint_prop_updated)

class BCT_BooleanChildOfConstraintObjectProperties(bpy.types.PropertyGroup):
    constraint_children: bpy.props.CollectionProperty(type=BCT_BooleanChildOfConstraintProperty)
    is_childof_constraints_all: bpy.props.BoolProperty(default=True, description="Remove or add all child-of constraints at once", update=on_toggle_all_bool_childof_constraint_prop_updated)
    auto_constraint: bpy.props.BoolProperty(default=True, description="Automatically constraint all booleans upon selecting object", update=on_auto_constraint_prop_updated)
    ignore_scale: bpy.props.BoolProperty(default=False, description="Ignore scale when adding constraints", update=on_ignore_scale_prop_updated)

class BCT_PT_BooleanConstraintToolsPanel(bpy.types.Panel):
    """Creates the Boolean Contraint Tools Panel in the Object properties window"""
    bl_label = "Boolean Constraint Tools"
    bl_idname = "OBJECT_PT_BCT_CONSTRAINT"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "constraint"

    def draw(self, context):
        layout = self.layout

        obj = context.object

        if len(obj.bct.constraint_children):
            row = layout.row()
            row.alignment = 'CENTER'
            row.label(text="Boolean Modifier Objects")

            all_boolean_modifiers = get_all_boolean_modifiers(obj)

            for modifier, constraint_child in zip(all_boolean_modifiers, obj.bct.constraint_children):
                row = layout.row()
                row.label(text=modifier.object.name)
                row.prop(constraint_child, 'value', text="")

            row = layout.row()
            row.alignment = 'RIGHT'
            row.label(text="Toggle All")
            row.prop(obj.bct, 'is_childof_constraints_all', text="")

        else:
            row = layout.row()
            row.alignment = 'CENTER'
            row.label(text="Active Object has no Boolean Modifier Objects.")

        layout.row().separator()

        row = layout.row()
        row.label(text="Options:")
        layout = layout.box()
        row = layout.row()
        row.label(text="Auto-Constraint")
        row.prop(obj.bct, 'auto_constraint', text="")
        row = layout.row()
        row.label(text="Ignore Scale")
        row.prop(obj.bct, 'ignore_scale', text="")

####
# This is operator extends the original object.origin_set
# by adding the following improvements:
#
# * It takes child-of constraints into account and does the
#   sensible thing of visually not moving these child objects
#   when setting the new origin location.
# * It adds the Bottom Center type (what everyone wants anyway).
####
class BCT_OT_object_origin_set(bpy.types.Operator):
    bl_idname = 'bct.origin_set'
    bl_label = 'Improved set origin'
    bl_options = {"REGISTER", "UNDO"}

    type: bpy.props.StringProperty(default='')

    def execute(self, context):
        obj = context.object
        all_boolean_modifiers_with_active_childof_constraints = get_all_boolean_modifiers_with_active_childof_constraints(obj)

        for modifier in all_boolean_modifiers_with_active_childof_constraints:
            remove_boolean_childof_constraint(obj, modifier)

        if self.type == 'ORIGIN_TO_0Z':
            self.origin_to_bottom(obj, keep_location=True)
        else:
            bpy.ops.object.origin_set(type=self.type)

        for modifier in all_boolean_modifiers_with_active_childof_constraints:
            add_boolean_childof_constraint(obj, modifier)

        return {'FINISHED'}

    # Source: https://blender.stackexchange.com/questions/182063/how-to-add-a-submenu-to-object-set-origin-in-blender-2-83#answer-182082
    def origin_to_bottom(self, obj, keep_location=True, matrix=Matrix()):
        local_verts = [matrix @ Vector(v[:]) for v in obj.bound_box]
        origin = sum(local_verts, Vector()) / 8
        origin.z = min(v.z for v in local_verts)
        origin = matrix.inverted() @ origin

        mesh_data = obj.data
        mesh_data.transform(Matrix.Translation(-origin))

        if keep_location:
            matrix_world = obj.matrix_world
            matrix_world.translation = matrix_world @ origin

class BCT_MT_object_origin_set(bpy.types.Menu):
    bl_label = "Set Origin (Parent Only)"
    bl_idname = "BCT_MT_object_origin_set"

    def draw(self, context):
        layout = self.layout
        layout.operator(BCT_OT_object_origin_set.bl_idname, text='Geometry to Origin').type = 'GEOMETRY_ORIGIN'
        layout.operator(BCT_OT_object_origin_set.bl_idname, text='Origin to Geometry').type = 'ORIGIN_GEOMETRY'
        layout.operator(BCT_OT_object_origin_set.bl_idname, text='Origin to 3D Cursor').type = 'ORIGIN_CURSOR'
        layout.operator(BCT_OT_object_origin_set.bl_idname, text='Origin to Center of Mass (Surface)').type = 'ORIGIN_CENTER_OF_MASS'
        layout.operator(BCT_OT_object_origin_set.bl_idname, text='Origin to Center of Mass (Volume)').type = 'ORIGIN_CENTER_OF_VOLUME'
        layout.operator(BCT_OT_object_origin_set.bl_idname, text='Origin to Bottom Center').type = 'ORIGIN_TO_0Z'

def draw_bct_set_origin_menu(self, context):
    self.layout.menu(BCT_MT_object_origin_set.bl_idname)
    self.layout.separator()

classes = [
    BCT_BooleanChildOfConstraintProperty,
    BCT_BooleanChildOfConstraintObjectProperties,
    BCT_PT_BooleanConstraintToolsPanel,
    BCT_OT_object_origin_set,
    BCT_MT_object_origin_set,
]

############# Register/Unregister Hooks ##############

def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Object.bct = bpy.props.PointerProperty(name="Boolean Constraint Tools Object Properties", type=BCT_BooleanChildOfConstraintObjectProperties)

    bpy.app.handlers.depsgraph_update_post.append( on_scene_updated )

    bpy.types.VIEW3D_MT_object_context_menu.prepend(draw_bct_set_origin_menu)
    bpy.types.VIEW3D_MT_object.prepend(draw_bct_set_origin_menu)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)

    del bpy.types.Object.bct

    bpy.app.handlers.depsgraph_update_post.remove( on_scene_updated )

    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_bct_set_origin_menu)
    bpy.types.VIEW3D_MT_object.remove(draw_bct_set_origin_menu)


if __name__ == "__main__":
    register()
