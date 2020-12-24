# Cad Outline

## Changelog

### 1.0.3

   * Fixed bug in instance handling due to faulty linter fix; == (original) ---> 'is not' (faulty linter fix) ---> 'is' (correct linter fix)

### 1.0.2

   * `#cad_outline_object_ensure`: Now only clear childof constraints when no matching childof constraints for given ob and `ob_outline` exists. (The clear just makes sure we do not have childof constraints to stale objects)
   * Now ensures that an `ob_outline` exists before calculating hashes (Fixes missing initial `ob_outline` when duplicating objects which have `cad_outline` already enabled)
   * Added more dprint statements at strategic points
   * Prevent unnecessary `mesh_cache` update
   * Added dedicated timing report printing setup
   * Fixed linter error '!= None' -> 'is not None'
   * Added throttling to some of the less essential `cad_outline` update/cleanup calls
   * Improved performance of `sync_visibility`; reduced time spent by 70%
   * Added detailed timing report printing
   * `#clean_up_stale_outlines`: Now also cleans up accidental outlines of objects that are linked instead of local

### 1.0.1

   * Fixed issue when dealing with linked objects
   * Now uses usersite for packages to prevent a rights issue in Blender's installation path
   * `cad_outline_object_hide_set()` now only updates visibility of `ob_outline` iff it exists
   * `collection_objects_get`: Moved to top
   * Objects in EDIT mode now reset their `evaluated_mesh_hash` to 0 and invalidate their `mesh_cache` entry to ensure a fresh outline is calculated after leaving EDIT mode
   * Objects in EDIT mode are now skipped when initializing `mesh_cache`
   * Now updates `mesh_cache` as soon as possible
   * pep8 auto format (updated rules)
   * Minor formatting change
   * Streamlined handling of edit mode. Moved all code to `on_scene_updated`. (Also more reliable as msgbus subscriptions from python turn out to be unreliable at best)
   * pip8 auto formatter, initial run.
   * Added dprint
   * Removed more long-kept python wrapper ob references in favour of name strings to prevent early/quick Blender terminations (AKA crashes)
   * `cad_outline_object_ensure` Now removes any existing childof constraints prior to ensuring the new one (prevents stale childof constraints to old parents)

