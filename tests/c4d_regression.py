"""Regression checks for the workspace source, run inside Cinema 4D.

All scene objects belong to detached temporary documents. No plugin registration
or active-document changes are performed.
"""

import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import c4d
from c4d.modules import mograph


class ResourceSymbols:
    """Resolve this project's resource IDs without loading/registering a plugin."""

    def __init__(self, symbols):
        self.symbols = symbols
        self.events = []
        self.messages = []

    def __getattr__(self, name):
        if name in self.symbols:
            return self.symbols[name]
        if name == "EventAdd":
            return lambda: self.events.append(True)
        if name == "StatusSetText":
            return self.messages.append
        return getattr(c4d, name)


class DirectCallHost:
    """A direct call has no native hierarchy-help capsule for CheckCache."""

    def __init__(self, node):
        self.node = node

    def __getattr__(self, name):
        return getattr(self.node, name)

    def __getitem__(self, key):
        return self.node[key]

    def CheckCache(self, hierarchyhelp):
        return True


def load_workspace(root):
    path = root / "quick_stitch.pyp"
    namespace = {"__name__": "quick_stitch_under_test", "__file__": str(path)}
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), namespace)
    header = (root / "res/description/quick_stitch.h").read_text(encoding="utf-8-sig")
    symbols = {name: int(value) for name, value in re.findall(
        r"(QUICK_STITCH_\w+)\s*=\s*(\d+)", header)}
    namespace["c4d"] = ResourceSymbols(symbols)
    return namespace


def vectors(points):
    return sorted(tuple(round(value, 5) for value in (p.x, p.y, p.z))
                  for p in points)


def world_points(spline):
    return vectors(spline.GetMg() * point for point in spline.GetAllPoints())


def polygon_count(node):
    result = 0
    while node:
        if isinstance(node, c4d.PolygonObject):
            result += node.GetPolygonCount()
        cache = node.GetCache()
        if cache is not None:
            result += polygon_count(cache)
        child = node.GetDown()
        if child is not None:
            result += polygon_count(child)
        node = node.GetNext()
    return result


class QuickStitchRegression(unittest.TestCase):
    namespace = None

    def setUp(self):
        # Run against isolated preferences, never the user's real C4D settings.
        engine = self.namespace["patterns"]
        self.language_preferences = {"language": engine.LANG_EN}
        load_patch = patch.object(
            engine, "load_global_language",
            side_effect=lambda: self.language_preferences["language"])
        self.language_load = load_patch.start()
        self.addCleanup(load_patch.stop)
        save_patch = patch.object(
            engine, "save_global_language",
            side_effect=lambda lang: self.language_preferences.__setitem__("language", lang))
        self.language_save = save_patch.start()
        self.addCleanup(save_patch.stop)
        self.api = self.namespace["c4d"]
        self.api.events.clear()
        self.api.messages.clear()
        self.document = c4d.documents.BaseDocument()
        # Its parameter IDs do not collide with the Quick Stitch IDs.
        self.owner = c4d.BaseObject(c4d.Opython)
        self.owner.SetDeformMode(False)
        self.document.InsertObject(self.owner)
        self.subject = self.namespace["QuickStitch"]()
        self.assertTrue(self.subject.Init(self.owner))

    def make_mesh(self, x=200.0):
        mesh = c4d.PolygonObject(4, 1)
        mesh.SetAllPoints([
            c4d.Vector(0, 0, 0), c4d.Vector(100, 0, 0),
            c4d.Vector(100, 100, 0), c4d.Vector(0, 100, 0),
        ])
        mesh.SetPolygon(0, c4d.CPolygon(0, 1, 2, 3))
        mesh.GetEdgeS().Select(0)
        mesh.Message(c4d.MSG_UPDATE)
        self.document.InsertObject(mesh)
        mesh.SetAbsPos(c4d.Vector(x, 0, 0))
        return mesh

    def extract(self, mesh):
        return self.namespace["create_spline_from_obj"](self.owner, mesh)

    def path(self, owner=None):
        return self.namespace["find_spline_child"](
            self.owner if owner is None else owner)

    def build(self, owner=None):
        return self.subject.GetVirtualObjects(
            DirectCallHost(self.owner if owner is None else owner), None)

    def click(self):
        return self.subject.Message(
            self.owner, c4d.MSG_DESCRIPTION_COMMAND,
            {"id": c4d.DescID(c4d.DescLevel(self.api.QUICK_STITCH_BUTTON))})

    def test_initialization_accepts_legacy_and_clone_calls(self):
        mesh = self.make_mesh()
        self.owner[self.api.QUICK_STITCH_COUNT] = 17
        self.owner[self.api.QUICK_STITCH_SOURCE] = mesh
        self.assertTrue(self.subject.Init(self.owner, True))
        self.assertEqual(self.owner[self.api.QUICK_STITCH_COUNT], 17)
        self.assertEqual(self.owner[self.api.QUICK_STITCH_SOURCE], mesh)
        self.assertTrue(self.subject.Init(self.owner, False))
        self.assertEqual(self.owner[self.api.QUICK_STITCH_COUNT], 100)

    def test_world_coordinates_with_translated_generator(self):
        mesh = self.make_mesh()
        self.owner.SetAbsPos(c4d.Vector(100, 0, 0))
        spline = self.extract(mesh)
        self.assertEqual(spline.GetMg().off, mesh.GetMg().off)
        self.assertEqual(world_points(spline), vectors(
            mesh.GetMg() * mesh.GetPoint(index) for index in (0, 1)))

    def test_world_coordinates_with_transformed_parents(self):
        mesh = self.make_mesh()
        for child, offset, rotation, scale in (
            (mesh, c4d.Vector(30, 20, -10), c4d.Vector(0.3, 0.4, 0.2), 2),
            (self.owner, c4d.Vector(-40, 5, 70), c4d.Vector(-0.2, 0.1, 0.5), 0.5),
        ):
            parent = c4d.BaseObject(c4d.Onull)
            self.document.InsertObject(parent)
            parent.SetRelPos(offset)
            parent.SetRelRot(rotation)
            parent.SetRelScale(c4d.Vector(scale))
            child.InsertUnder(parent)
        spline = self.extract(mesh)
        self.assertEqual(world_points(spline), vectors(
            mesh.GetMg() * mesh.GetPoint(index) for index in (0, 1)))

    def test_conversion_preserves_source_and_unrelated_children(self):
        mesh = self.make_mesh()
        marker = c4d.BaseObject(c4d.Onull)
        marker.InsertUnder(mesh)
        sibling = c4d.BaseObject(c4d.Ocube)
        sibling.InsertUnder(self.owner)
        original_points = vectors(mesh.GetAllPoints())
        first = self.extract(mesh)
        # Force a non-spline to be the first child before replacement.
        sibling.Remove()
        sibling.InsertUnder(self.owner)
        second = self.extract(mesh)
        self.assertEqual(vectors(mesh.GetAllPoints()), original_points)
        self.assertTrue(mesh.GetEdgeS().IsSelected(0))
        self.assertEqual(mesh.GetDown(), marker)
        self.assertEqual(sibling.GetUp(), self.owner)
        self.assertEqual(self.path(), second)
        self.assertIsNone(first.GetUp())
        self.assertEqual(len(self.owner.GetChildren()), 2)

    def test_create_replace_undo_redo(self):
        mesh = self.make_mesh()
        first_points = world_points(self.extract(mesh))
        mesh.GetEdgeS().DeselectAll()
        mesh.GetEdgeS().Select(1)
        second_points = world_points(self.extract(mesh))
        self.assertNotEqual(first_points, second_points)
        self.assertTrue(self.document.DoUndo())
        self.assertEqual(world_points(self.path()), first_points)
        self.assertTrue(self.document.DoUndo())
        self.assertIsNone(self.path())
        self.assertTrue(self.document.DoRedo())
        self.assertEqual(world_points(self.path()), first_points)
        self.assertTrue(self.document.DoRedo())
        self.assertEqual(world_points(self.path()), second_points)

    def test_invalid_input_preserves_path_and_undo_history(self):
        mesh = self.make_mesh()
        previous = world_points(self.extract(mesh))
        mesh.GetEdgeS().DeselectAll()
        for invalid in (None, c4d.BaseObject(c4d.Ocube), mesh):
            with self.assertRaises(ValueError):
                self.extract(invalid)
            self.assertEqual(world_points(self.path()), previous)
        self.assertTrue(self.document.DoUndo())
        self.assertIsNone(self.path())

    def test_button_uses_current_link_before_any_generation(self):
        first = self.make_mesh(200)
        second = self.make_mesh(-300)
        self.owner[self.api.QUICK_STITCH_SOURCE] = first
        self.assertTrue(self.click())
        self.assertEqual(self.path().GetMg().off.x, 200)
        self.owner[self.api.QUICK_STITCH_SOURCE] = second
        self.assertTrue(self.click())
        self.assertEqual(self.path().GetMg().off.x, -300)
        self.assertEqual(len(self.api.events), 2)

    def test_button_reports_invalid_input_without_removing_path(self):
        mesh = self.make_mesh()
        previous = world_points(self.extract(mesh))
        self.owner[self.api.QUICK_STITCH_SOURCE] = None
        with redirect_stdout(io.StringIO()):
            self.assertTrue(self.click())
        self.assertTrue(self.api.messages)
        self.assertEqual(world_points(self.path()), previous)

    def test_empty_and_non_spline_input_return_empty_null(self):
        for child in (None, c4d.BaseObject(c4d.Ocube)):
            if child is not None:
                child.InsertUnder(self.owner)
            result = self.build()
            self.assertTrue(result.CheckType(c4d.Onull))
            self.assertIsNone(result.GetDown())
        self.extract(self.make_mesh())
        for field in (self.api.QUICK_STITCH_COUNT, self.api.QUICK_STITCH_THICKNESS):
            old_value = self.owner[field]
            self.owner[field] = 0
            self.assertIsNone(self.build().GetDown())
            self.owner[field] = old_value

    def test_shape_scaling_does_not_accumulate(self):
        shape = self.owner[self.api.QUICK_STITCH_SHAPE]
        original = vectors(knot["vPos"] for knot in shape.GetKnots())
        arc = c4d.SplineObject(2, c4d.SPLINETYPE_BEZIER)
        make_arc = self.namespace["create_spline_from_splinedata"]
        self.assertTrue(make_arc(shape, arc, 6, 3))
        first = vectors(arc.GetAllPoints())
        self.assertTrue(make_arc(shape, arc, 6, 3))
        self.assertEqual(vectors(arc.GetAllPoints()), first)
        self.assertEqual(vectors(knot["vPos"] for knot in shape.GetKnots()), original)

    def test_copied_generator_has_independent_path_and_parameters(self):
        self.extract(self.make_mesh())
        self.owner[self.api.QUICK_STITCH_COUNT] = 7
        copied = self.owner.GetClone()
        self.document.InsertObject(copied)
        self.assertTrue(self.subject.Init(copied, True))
        self.assertEqual(copied[self.api.QUICK_STITCH_COUNT], 7)
        original_path = self.path()
        copied_path = self.path(copied)
        self.assertNotEqual(original_path, copied_path)
        original_points = vectors(original_path.GetAllPoints())
        copied_path.SetPoint(0, copied_path.GetPoint(0) + c4d.Vector(10, 0, 0))
        copied_path.Message(c4d.MSG_UPDATE)
        result = self.build(copied)
        linked_path = result.GetDown()[c4d.MG_OBJECT_LINK]
        self.assertEqual(linked_path.GetUp(), result)
        self.assertNotEqual(linked_path, original_path)
        self.assertEqual(vectors(original_path.GetAllPoints()), original_points)
        self.assertEqual(vectors(linked_path.GetAllPoints()),
                         vectors(copied_path.GetAllPoints()))

    def test_primitive_spline_is_supported(self):
        circle = c4d.BaseObject(c4d.Osplinecircle)
        circle.InsertUnder(self.owner)
        result = self.build()
        self.assertEqual(result.GetDown()[c4d.MG_OBJECT_LINK].GetType(),
                         c4d.Osplinecircle)

    def test_native_cloner_and_sweep_produce_mesh(self):
        self.extract(self.make_mesh())
        self.owner[self.api.QUICK_STITCH_COUNT] = 7
        result = self.build()
        self.document.InsertObject(result)
        result.SetMg(self.owner.GetMg())
        self.document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        cloner = result.GetDown()
        data = mograph.GeGetMoData(cloner)
        self.assertIsNotNone(data)
        self.assertEqual(data.GetCount(), 7)
        self.assertGreater(polygon_count(result), 0)

    def test_native_callback_updates_parameters_and_path(self):
        self.extract(self.make_mesh())
        self.owner[self.api.QUICK_STITCH_COUNT] = 5
        source_path = str(Path(self.namespace["__file__"]))
        # Python Generator supplies the same native hh capsule used by
        # ObjectData, so this also exercises the real CheckCache call.
        self.owner[c4d.TPYTHON_CODE] = f"""
import c4d
import re
from pathlib import Path
source = Path({source_path!r})
implementation = {{'__name__': 'quick_stitch_callback_test', '__file__': str(source)}}
exec(compile(source.read_text(encoding='utf-8-sig'), str(source), 'exec'), implementation)
symbols = {{name: int(value) for name, value in re.findall(
    r'(QUICK_STITCH_\\w+)\\s*=\\s*(\\d+)',
    (source.parent / 'res/description/quick_stitch.h').read_text(encoding='utf-8-sig'))}}
class CallbackResources:
    def __getattr__(self, name):
        return symbols[name] if name in symbols else getattr(c4d, name)
implementation['c4d'] = CallbackResources()
subject = implementation['QuickStitch']()
def main():
    return subject.GetVirtualObjects(op, hh)
"""
        # Match QuickStitch.SetOptimizeCache(False), rather than the Python
        # Generator's default parameter-only optimization.
        self.owner[c4d.OPYTHON_OPTIMIZE] = False
        self.owner.SetDeformMode(True)
        for count in (5, 8):
            self.owner[self.api.QUICK_STITCH_COUNT] = count
            self.document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
            root = self.owner.GetCache()
            self.assertIsNotNone(root)
            data = mograph.GeGetMoData(root.GetDown())
            self.assertIsNotNone(data)
            self.assertEqual(data.GetCount(), count)

        path = self.path()
        path.SetPoint(0, path.GetPoint(0) + c4d.Vector(25, 0, 0))
        path.Message(c4d.MSG_UPDATE)
        path.SetDirty(c4d.DIRTYFLAGS_DATA)
        for unused in range(2):
            self.document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
            root = self.owner.GetCache()
            linked_path = root.GetDown()[c4d.MG_OBJECT_LINK]
            self.assertEqual(vectors(linked_path.GetAllPoints()),
                             vectors(path.GetAllPoints()))
            self.assertGreater(polygon_count(root), 0)

    def test_missing_icon_uses_fallback_and_logs(self):
        with redirect_stdout(io.StringIO()) as output:
            bitmap = self.namespace["load_icon"]("missing-quick-stitch-icon.tif")
        self.assertIsNone(bitmap)
        self.assertIn("could not load icon", output.getvalue())

    def test_only_one_plugin_entry_point(self):
        root = Path(self.namespace["__file__"]).parent
        self.assertEqual(sorted(path.name for path in root.rglob("*.pyp")),
                         ["quick_stitch.pyp"])
        self.assertTrue((root / "quick_stitch_original_py2.pyp.bak").is_file())


def run(root=None):
    active_document = c4d.documents.GetActiveDocument()
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    QuickStitchRegression.namespace = load_workspace(root)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QuickStitchRegression)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if c4d.documents.GetActiveDocument() != active_document:
        raise RuntimeError("The regression run changed the active document.")
    if not result.wasSuccessful():
        raise RuntimeError("Quick Stitch regression checks failed.")
    return result.testsRun


if __name__ == "__main__":
    run()
