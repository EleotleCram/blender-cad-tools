# Cad Mesh Dimensions

## Changelog

### 1.1.1

   * Now only forcing `update_dimensions` if `selected_elements` change `_and_` `transform_orientation` is 'NORMAL' (otherwise we incur an endless loop)
   * Added `fast_truncate` to avoid lots of blinking float representation errors (0.000001, 0.000002, 0.000003, ...) (Now also for transform orientation 'GLOBAL')

### 1.1

   * Removed unused class
   * Added `fast_truncate` to avoid lots of blinking float representation errors (0.000001, 0.000002, 0.000003, ...)
   * Added support for transform orientation 'NORMAL'
   * Moved global handle variable to Reg/Unreg Hooks section
   * Removed unused reference
   * Moved bpy.types.Object.`cad_mesh_dimensions_anchor` to bpy.types.Object.`cad_mesh_dimensions`.anchor (PointerProperty)
   * Now uses usersite for packages to prevent a rights issue in Blender's installation path
   * Cleaned up imports
   * Removed throttling code; in the end also too unstable. Limiting CAD Mesh Dimensions Addon to meshes with sub-10k verts should be good enough for now
   * Disabled debug timing code
   * def `vertices_hash`: moved to correct section in file
   * Now CAD Mesh Dimensions is only enabled for meshes with less than 10k verts (CAD designs with > 10k verts are called sculpts, this addon is not suitable for sculpts)
   * Improved robustness; no longer keeping long lived references to python C wrappers (keeping those leads to quick Blender exits (AKA crashes))
   * autopep8 format (updated rules)
   * default value for `cad_mesh_dimensions_anchor` is now `OBJECT_ORIGIN` rather than `ACTIVE_ELEMENT` (default now behaves exactly as it does when editing dimensions in OBJECT mode (except that in EDIT mode these are applied on the mesh directly of course and do not affect the scale))
   * renamed `edit_dimensions_anchor` -> `cad_mesh_dimensions_anchor` + is now a per object property (and stored in blend file)
   * bpy.types.WindowManager.`edit_dimensions` -> bpy.types.WindowManager.`cad_mesh_dimensions`
   * Now resets `hash_prev` when going out of EDIT mode
   * Increased precision of display dimension values to 4 digits
   * Improved robustness of code responding to selection/mesh changes; Added live update of dimension values

