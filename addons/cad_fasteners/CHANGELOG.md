# Cad Fasteners

## Changelog

   * Moved Screw.`screw_drive_cutter_construct` down to class SocketDrive and Screw.`screw_head_construct` to class ScrewHead
   * Moved all "Head" classes together
   * Switched to autopep8 1.5.8pre

### 1.0.1

   * 'Mark as fastener' now retains the exact Object name, if it already matches the required Template name (e.g. it matches, but has a dup postfix like .001, .002 etc.)
   * 'Mark as fastener' now also enabled `cad_outline` if available and scene has `cad_outline` enabled
   * 'Mark as fastener' now also detects Nuts
   * Now stores a timestamp of the included fasteners templates, only re-importing the templates from `cad_fasteners`.blend if the local copies are out of date
   * Now only showing the `CAD_FAST_PT_ItemNPanel` when the object is a fastener
   * Moved `is_fastener` prop to Object properties window
   * Renamed Panel class: `CAD_FAST_PT_ObjectPanel` -> `CAD_FAST_PT_ItemNPanel`
   * Sphere -> Button Head Dome Sphere
   * Clean up of stale fastener template objects now takes unlinked templates into account
   * Now checks for available sizes per standard instead of allowing every size regarding the standard
   * `CAD_FAST_METRIC_SIZES` -> `CAD_FAST_METRIC_AVAILABLE_LENGTHS` + More pythonic list comprehensions rather than nested map calls.
   * Fastener.`template_ensure`: Removed call to the now obsolete cls.scale
   * Nut now uses 'construct' instead of 'scale' for exact construction
   * Washers (DIN125A, ...) now also use exact dimensions
   * Added `ISO_4026` (DIN 931) Set Screw
   * Fixed name template for DIN 933 (Hex Head Cap Screw)
   * Fixed Inheritance tree, Head type is now used for main ancestry line, so Head types can override defaults for `head_type`, `drive_type`, `drive_offset` properly
   * Now always lets a template class update an existing object (and not only when the template object gets constructed)
   * When updating an existing object, now unsets selected display props
   * CountersunkHead now tweaks the sharp angle to 15 degrees
   * Added 'update' hook to update template and object to allow for some last-minute fine-tuning
   * `CAD_FAST_OT_AddNew` operator now deselects all objects prior to adding a new fastener to the scene
   * Now produces correctly sized Metric Nuts according to DIN 934
   * Removed debug print
   * Rewrite to class-based approach, as this better supports reuse and type differentation

