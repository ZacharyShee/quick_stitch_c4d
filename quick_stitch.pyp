"""
Quick Stitch Pro V1.0
Author: Zachary Shee
Based on Quick Stitch for C4D — Copyright (c) 2020 Nishiki

Released under the MIT license
https://opensource.org/licenses/mit-license.php
"""

import importlib.util
import os

import c4d


PLUGIN_ID = 1054816
CLONER_OBJECT = 1018544

# Load the adjacent engine explicitly; C4D does not always add plugin folders
# to sys.path. Re-executing the entry also reloads the engine during development.
_engine_path = os.path.join(os.path.dirname(__file__), "quick_stitch_patterns.py")
_engine_spec = importlib.util.spec_from_file_location("quick_stitch_patterns", _engine_path)
patterns = importlib.util.module_from_spec(_engine_spec)
with open(_engine_path, encoding="utf-8-sig") as _engine_file:
    exec(compile(_engine_file.read(), _engine_path, "exec"), patterns.__dict__)


def find_spline_child(node):
    """Find the first direct spline child, skipping unrelated objects."""
    child = node.GetDown()
    while child:
        if child.GetInfo() & c4d.OBJECT_ISSPLINE:
            return child
        child = child.GetNext()
    return None


def create_spline_from_splinedata(sp_data, arc, width, height):
    if sp_data is None:
        return False
    knots = sp_data.GetKnots()
    if len(knots) < 2:
        return False
    if not arc.ResizeObject(len(knots)):
        raise MemoryError("Could not allocate the stitch curve.")

    for index, knot in enumerate(knots):
        # Keep the shape editor data independent from the generated geometry.
        pos = c4d.Vector(knot["vPos"])
        tan_r = c4d.Vector(knot["vTangentRight"])
        tan_l = c4d.Vector(knot["vTangentLeft"])
        pos.x = (pos.x - 0.5) * width
        pos.y *= height
        for tangent in (tan_l, tan_r):
            tangent.x *= width
            tangent.y *= height
        arc.SetPoint(index, pos)
        arc.SetTangent(index, tan_l, tan_r)

    arc[c4d.ID_BASEOBJECT_REL_ROTATION, c4d.VECTOR_X] = c4d.utils.DegToRad(-90)
    arc[c4d.ID_BASEOBJECT_REL_ROTATION, c4d.VECTOR_Y] = c4d.utils.DegToRad(90)
    arc[c4d.SPLINEOBJECT_ANGLE] = c4d.utils.DegToRad(15)
    arc.Message(c4d.MSG_UPDATE)
    return True


def create_spline_from_obj(node, obj):
    """Replace the path from selected mesh edges in one undoable operation."""
    if obj is None or not obj.CheckType(c4d.Opolygon):
        raise ValueError("Link an editable polygon object in the Object field.")
    if obj.GetEdgeS().GetCount() == 0:
        raise ValueError("Select at least one edge on the linked object.")
    document = node.GetDocument()
    if document is None:
        raise ValueError("The Quick Stitch object must belong to a document.")

    source = obj.GetClone(c4d.COPYFLAGS_NO_HIERARCHY)
    if source is None:
        raise MemoryError("Could not copy the source mesh.")
    # Model on a disposable copy, with points in the source mesh's local space.
    temporary_document = c4d.documents.BaseDocument()
    temporary_document.InsertObject(source)
    source.SetMl(c4d.Matrix())
    result = c4d.utils.SendModelingCommand(
        command=c4d.MCOMMAND_EDGE_TO_SPLINE,
        list=[source],
        mode=c4d.MODELINGCOMMANDMODE_EDGESELECTION,
        bc=c4d.BaseContainer(),
        doc=temporary_document,
    )
    generated = find_spline_child(source)
    if not result or generated is None:
        raise RuntimeError("Could not create a spline from the selected edges.")
    spline = generated.GetClone(c4d.COPYFLAGS_NO_HIERARCHY)
    if spline is None:
        raise MemoryError("Could not copy the generated path.")
    spline[c4d.SPLINEOBJECT_INTERPOLATION] = c4d.SPLINEOBJECT_INTERPOLATION_UNIFORM
    world_matrix = obj.GetMg() * generated.GetMl()
    previous_path = find_spline_child(node)

    # Finish conversion before touching the existing document or its undo stack.
    c4d.StopAllThreads()
    document.StartUndo()
    try:
        spline.InsertUnder(node)
        # Parent first: SetMg must compensate for the generator's transform.
        spline.SetMg(world_matrix)
        document.AddUndo(c4d.UNDOTYPE_NEWOBJ, spline)
        if previous_path is not None:
            document.AddUndo(c4d.UNDOTYPE_DELETEOBJ, previous_path)
            previous_path.Remove()
        node.SetDirty(c4d.DIRTYFLAGS_DATA)
    finally:
        document.EndUndo()
    return spline


class QuickStitch(c4d.plugins.ObjectData):
    def __init__(self, *args):
        # Child geometry and transforms must participate in cache invalidation.
        self.SetOptimizeCache(False)

    def Init(self, op, isCloneInit=False):
        if op is None or op.GetDataInstance() is None:
            return False
        if isCloneInit:
            return True
        saved_language = patterns.load_global_language()

        self.InitAttr(op, c4d.BaseList2D, c4d.QUICK_STITCH_SOURCE)
        self.InitAttr(op, int, c4d.QUICK_STITCH_COUNT)
        self.InitAttr(op, float, c4d.QUICK_STITCH_WIDTH)
        self.InitAttr(op, float, c4d.QUICK_STITCH_HEIGHT)
        self.InitAttr(op, float, c4d.QUICK_STITCH_THICKNESS)
        self.InitAttr(op, float, c4d.QUICK_STITCH_OFFSET)
        self.InitAttr(op, float, c4d.QUICK_STITCH_ROTATION_H)
        self.InitAttr(op, float, c4d.QUICK_STITCH_ROTATION_B)
        self.InitAttr(op, float, c4d.QUICK_STITCH_ROTATION_P)
        self.InitAttr(op, c4d.SplineData, c4d.QUICK_STITCH_SHAPE)

        op[c4d.QUICK_STITCH_COUNT] = 100
        op[c4d.QUICK_STITCH_WIDTH] = 6.0
        op[c4d.QUICK_STITCH_HEIGHT] = 3.0
        op[c4d.QUICK_STITCH_THICKNESS] = 0.5
        op[c4d.QUICK_STITCH_OFFSET] = -1.0
        op[c4d.QUICK_STITCH_ROTATION_H] = 0.0
        op[c4d.QUICK_STITCH_ROTATION_B] = 0.0
        op[c4d.QUICK_STITCH_ROTATION_P] = 0.0

        op[c4d.QUICK_STITCH_SHAPE] = patterns.default_shape()
        for identifier, datatype, default in patterns.PARAMETERS.values():
            if identifier == 1132:
                # Initialization must not enter the preference-saving setter.
                op.GetDataInstance()[identifier] = saved_language
                continue
            self.InitAttr(op, datatype, identifier)
            if isinstance(default, tuple):
                default = c4d.Vector(*default)
            if default is not None:
                op[identifier] = default
        op.GetDataInstance()[1128] = patterns.editable_shape()
        op.GetDataInstance()[1130] = 0
        return True

    def SetDParameter(self, node, identifier, data, flags):
        field = identifier[0].id
        if field not in (1128, 1130, 1132):
            return False
        container = node.GetDataInstance()
        if field == 1132:
            lang = int(data)
            if lang not in (patterns.LANG_AUTO, patterns.LANG_EN, patterns.LANG_ZH):
                return False
            container[1132] = lang
            if flags & c4d.DESCFLAGS_SET_USERINTERACTION:
                patterns.save_global_language(lang)
            node.SetDirty(getattr(c4d, "DIRTYFLAGS_DESCRIPTION", c4d.DIRTYFLAGS_DATA))
            return True, flags | c4d.DESCFLAGS_SET_PARAM_SET
        if field == 1130:
            preset = int(data)
            if not 0 <= preset <= patterns.CUSTOM_PROFILE:
                return False
            # Store both values inside C4D's parameter/undo transaction. Raw
            # container writes avoid recursively marking this preset as Custom.
            if preset != patterns.CUSTOM_PROFILE:
                container[1128] = patterns.editable_shape(preset=preset)
            container[1130] = preset
        else:
            if not isinstance(data, c4d.SplineData):
                return False
            container[1128] = patterns.editable_shape(data)
            # Selecting a knot also writes spline data; it is not a shape edit.
            if not patterns.matches_profile_preset(container[1128], container[1130]):
                container[1130] = patterns.CUSTOM_PROFILE
        node.SetDirty(c4d.DIRTYFLAGS_DATA)
        return True, flags | c4d.DESCFLAGS_SET_PARAM_SET

    def Message(self, node, message_type, data):
        if message_type in (c4d.MSG_MENUPREPARE, c4d.MSG_MULTI_DOCUMENTIMPORTED):
            container = node.GetDataInstance()
            shape = container[1128]
            limits = shape.GetRange() if isinstance(shape, c4d.SplineData) else None
            if shape is None or (isinstance(shape, c4d.SplineData) and (
                    limits is None or limits["xmin"] != 0 or limits["xmax"] != 1 or
                    limits["ymin"] != 0 or limits["ymax"] != 1)):
                container[1128] = patterns.editable_shape(shape)
            for field, default in ((1130, 0), (1132, patterns.load_global_language())):
                if container[field] is None:
                    container[field] = default
            if (container[1130] != patterns.CUSTOM_PROFILE and
                    not patterns.matches_profile_preset(container[1128], container[1130])):
                container[1130] = patterns.CUSTOM_PROFILE
            return True
        if message_type != c4d.MSG_DESCRIPTION_COMMAND or not data:
            return True
        command = data.get("id")
        if command is None:
            return True
        if command[0].id != c4d.QUICK_STITCH_BUTTON:
            return True

        try:
            create_spline_from_obj(node, node[c4d.QUICK_STITCH_SOURCE])
        except Exception as error:
            print(patterns.format_error(error, node, for_console=True))
            c4d.StatusSetText(patterns.format_error(error, node, for_console=False))
            return True
        c4d.EventAdd()
        return True

    def _remember_geometry(self, op, config, root):
        # Keep immutable parameter values only, never references to native caches.
        self._geometry_state = patterns.geometry_signature(op, config)
        self._cache_language = config["language"]
        return root

    def GetVirtualObjects(self, op, hierarchyhelp):
        path = find_spline_child(op)
        config = patterns.settings(op)
        surface = None
        surface_error = None
        if config["style"] != patterns.LEGACY:
            try:
                surface = patterns.resolved_surface(op, config)
            except ValueError as error:
                surface_error = str(error)
        surface_state = patterns.dependency_signature(surface, op)
        surface_changed = surface_state != getattr(self, "_surface_state", None)
        self._surface_state = surface_state
        op.NewDependenceList()
        if path is not None:
            pending = [path]
            while pending:
                child = pending.pop()
                op.AddDependence(child, c4d.DIRTYFLAGS_DATA |
                                 c4d.DIRTYFLAGS_MATRIX | c4d.DIRTYFLAGS_CACHE)
                pending.extend(child.GetChildren())
        inputs_changed = not op.CompareDependenceList()
        dirty = op.CheckCache(hierarchyhelp) or op.IsDirty(c4d.DIRTYFLAGS_DATA)
        op.TouchDependenceList()
        cache = op.GetCache()
        if not inputs_changed and not surface_changed and cache is not None:
            if not dirty:
                if getattr(self, "_geometry_state", None) is None:
                    return self._remember_geometry(op, config, cache)
                self._cache_language = config["language"]
                return cache
            # SetParameter can also dirty the native cache for a UI-only edit.
            # Bypass that invalidation only for a language change whose complete
            # geometry inputs still match the cache; keep all other dirty checks.
            if (config["language"] != getattr(self, "_cache_language", None) and
                    patterns.geometry_signature(op, config) ==
                    getattr(self, "_geometry_state", None)):
                self._cache_language = config["language"]
                return cache

        root = c4d.BaseObject(c4d.Onull)
        if root is None:
            return None
        if path is None:
            return self._remember_geometry(op, config, root)
        if isinstance(path, c4d.SplineObject) and path.GetPointCount() < 2:
            return self._remember_geometry(op, config, root)
        if config["style"] != patterns.LEGACY:
            try:
                if surface_error is not None:
                    raise ValueError(surface_error)
                if not 1 <= config["style"] < len(patterns.STYLE_NAMES):
                    raise ValueError("Unknown stitch style.")
                return self._remember_geometry(op, config, patterns.build(op, path, config, surface))
            except Exception as error:
                print(patterns.format_error(error, op, for_console=True))
                return self._remember_geometry(op, config, root)
        count = op[c4d.QUICK_STITCH_COUNT]
        thickness = op[c4d.QUICK_STITCH_THICKNESS]
        if count <= 0 or thickness <= 0:
            return self._remember_geometry(op, config, root)

        arc = c4d.SplineObject(2, c4d.SPLINETYPE_BEZIER)
        if arc is None:
            return None
        if not create_spline_from_splinedata(
            op[c4d.QUICK_STITCH_SHAPE], arc,
            op[c4d.QUICK_STITCH_WIDTH], op[c4d.QUICK_STITCH_HEIGHT],
        ):
            return self._remember_geometry(op, config, root)

        sweep = c4d.BaseObject(c4d.Osweep)
        circle = c4d.BaseObject(c4d.Osplinecircle)
        cloner = c4d.BaseObject(CLONER_OBJECT)
        path_clone = path.GetClone()
        if any(item is None for item in (sweep, circle, cloner, path_clone)):
            return None

        # The cache owns its path and all generated objects. Native hierarchy
        # copying handles duplicates; no NodeData object references need copying.
        path_clone.InsertUnder(root)
        path_clone.SetEditorMode(c4d.MODE_OFF)
        path_clone.SetRenderMode(c4d.MODE_OFF)
        arc.InsertUnder(sweep)
        circle.InsertUnder(sweep)
        sweep.InsertUnder(cloner)
        cloner.InsertUnder(root)

        sweep.SetPhong(True, True, c4d.utils.DegToRad(50))
        circle[c4d.PRIM_CIRCLE_RADIUS] = thickness
        circle[c4d.SPLINEOBJECT_SUB] = 1
        cloner[c4d.ID_MG_MOTIONGENERATOR_MODE] = 0  # Object mode.
        cloner[c4d.MG_SPLINE_MODE] = 0  # Count mode.
        cloner[c4d.MG_SPLINE_COUNT] = count
        cloner[c4d.ID_MG_TRANSFORM_POSITION, c4d.VECTOR_X] = -op[c4d.QUICK_STITCH_OFFSET]
        cloner[c4d.ID_MG_TRANSFORM_ROTATE, c4d.VECTOR_X] = op[c4d.QUICK_STITCH_ROTATION_H]
        cloner[c4d.ID_MG_TRANSFORM_ROTATE, c4d.VECTOR_Y] = op[c4d.QUICK_STITCH_ROTATION_P]
        cloner[c4d.ID_MG_TRANSFORM_ROTATE, c4d.VECTOR_Z] = op[c4d.QUICK_STITCH_ROTATION_B]
        cloner[c4d.MG_OBJECT_LINK] = path_clone
        return self._remember_geometry(op, config, root)


    def GetDDescription(self, node, description, flags):
        if not description.LoadDescription(node.GetType()):
            return False
        for field, (minimum, maximum) in patterns.PERCENT_RANGES.items():
            identifier = c4d.DescID(c4d.DescLevel(field, c4d.DTYPE_REAL, 0))
            parameter = description.GetParameterI(identifier, None)
            if parameter is None:
                continue
            # Resource UNIT PERCENT limits are in display units (0..100);
            # the live descriptor uses normalized values (0..1).
            parameter[c4d.DESC_MIN] = minimum
            parameter[c4d.DESC_MAX] = maximum
            parameter[c4d.DESC_MINSLIDER] = minimum
            parameter[c4d.DESC_MAXSLIDER] = maximum
            parameter[c4d.DESC_STEP] = 0.01
        patterns.localize_description(description, patterns.effective_language(node))
        return True, flags | c4d.DESCFLAGS_DESC_LOADED

    def GetDEnabling(self, node, identifier, data, flags, itemdesc):
        field = identifier[0].id
        style = patterns.value(node, 1100, patterns.LEGACY)
        legacy = style == patterns.LEGACY
        spacing = patterns.value(node, 1101, 1)
        if field in (1003, 1004, 1006, 1007):
            return legacy
        if field in (1123, 1124, 1129, 1131):  # Retired controls.
            return False
        if field == 1002:
            return legacy or spacing == 0
        if field in (1100, 1000, 1008, 1005, 1009, 1010, 1011):
            return True
        if 1101 <= field <= 1131:
            if legacy:
                return False
            if field == 1102:
                return spacing == 1
            if field == 1103:
                return style != patterns.RUNNING
            if field == 1104:
                return style in (patterns.RUNNING, patterns.DOUBLE, patterns.SLANT,
                                 patterns.CHEVRON, patterns.CROSS)
            if field == 1108:
                return style != patterns.RUNNING
            if field in (1109, 1112, 1126):
                return bool(patterns.value(node, 1110, False))
            if field == 1106:
                return style == patterns.CROSS
            if field in (1116, 1119):
                return style in (patterns.DOUBLE, patterns.CROSS, patterns.DIAMOND, patterns.BRAID)
            if field in (1117, 1120):
                return style == patterns.BRAID
            if field == 1125:
                return style in (patterns.SLANT, patterns.CHEVRON, patterns.DIAMOND, patterns.BRAID)
            return True
        return True


def load_icon(filename):
    bitmap = c4d.bitmaps.BaseBitmap()
    if bitmap is not None:
        result = bitmap.InitWith(filename)
        result_code = result[0] if isinstance(result, (tuple, list)) else result
        if result_code == c4d.IMAGERESULT_OK:
            return bitmap
        print("Quick Stitch: could not load icon {} (result {}).".format(
            filename, result_code))
    else:
        print("Quick Stitch: could not allocate the plugin icon.")
    return None


if __name__ == "__main__":
    directory = os.path.dirname(__file__)
    icon = load_icon(os.path.join(directory, "res", "qiuckstitch.tif"))
    if not c4d.plugins.RegisterObjectPlugin(
        id=PLUGIN_ID,
        str=patterns.PLUGIN_NAME,
        g=QuickStitch,
        description="quick_stitch",
        icon=icon,
        info=c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT,
    ):
        print("Quick Stitch Pro: registration failed; check for another plugin using ID {}.".format(PLUGIN_ID))
    else:
        print("{} {} loaded — Author: {}".format(
            patterns.PLUGIN_NAME, patterns.PLUGIN_VERSION, patterns.PLUGIN_AUTHOR))
