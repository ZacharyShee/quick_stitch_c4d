"""Run the new-pattern and legacy regression suites inside Cinema 4D."""
import io
import math
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import c4d

_support_path = Path(__file__).with_name("c4d_regression.py")
_support = {"__name__": "quick_stitch_test_support", "__file__": str(_support_path)}
exec(compile(_support_path.read_text(encoding="utf-8-sig"), str(_support_path), "exec"), _support)
vectors = _support["vectors"]
polygon_count = _support["polygon_count"]


def paths(root):
    return [child for group in root.GetChildren() for child in group.GetChildren()
            if isinstance(child, c4d.SplineObject)]


class CachedHost(_support["DirectCallHost"]):
    """Supply an evaluated cache while simulating native parameter invalidation."""
    def __init__(self, node):
        super().__init__(node)
        self.cache = None
        self.inputs_changed = False

    def GetCache(self):
        return self.cache

    def IsDirty(self, flags):
        return True

    def CompareDependenceList(self):
        return not self.inputs_changed


class PatternRegression(_support["QuickStitchRegression"]):
    def setUp(self):
        super().setUp()
        self.outputs = []

    def build(self, owner=None):
        result = super().build(owner)
        # C4D owns children through their root, not through Python child wrappers.
        # A direct-call test must keep that root alive until assertions finish.
        self.outputs.append(result)
        return result

    def pattern(self, style=6, length=120, count=12):
        line = c4d.SplineObject(2, c4d.SPLINETYPE_LINEAR)
        line.SetAllPoints([c4d.Vector(0), c4d.Vector(0, 0, length)])
        line.Message(c4d.MSG_UPDATE)
        line.InsertUnder(self.owner)
        self.owner[1100], self.owner[1101] = style, 0
        self.owner[1002], self.owner[1005] = count, 0.2
        return line

    def plane(self):
        mesh = c4d.PolygonObject(4, 1)
        mesh.SetAllPoints([
            c4d.Vector(-50, 0, -50), c4d.Vector(-50, 0, 200),
            c4d.Vector(50, 0, 200), c4d.Vector(50, 0, -50),
        ])
        mesh.SetPolygon(0, c4d.CPolygon(0, 1, 2, 3))
        mesh.Message(c4d.MSG_UPDATE)
        self.document.InsertObject(mesh)
        return mesh

    def circle(self, count=96, radius=30):
        spline = c4d.SplineObject(count, c4d.SPLINETYPE_LINEAR)
        spline.SetAllPoints([c4d.Vector(radius * math.cos(i * 2*math.pi/count), 0,
                                       radius * math.sin(i * 2*math.pi/count))
                            for i in range(count)])
        spline[c4d.SPLINEOBJECT_CLOSED] = True
        spline.Message(c4d.MSG_UPDATE)
        spline.InsertUnder(self.owner)
        return spline

    def native_callback(self):
        source = str(Path(self.namespace["__file__"]))
        symbols = repr(self.api.symbols)
        self.owner[c4d.OPYTHON_CODE] = f"""
import c4d
from pathlib import Path
source = Path({source!r})
implementation = {{'__name__': 'pattern_callback', '__file__': str(source)}}
exec(compile(source.read_text(encoding='utf-8-sig'), str(source), 'exec'), implementation)
symbols = {symbols}
class ResourceProxy:
    def __getattr__(self, name):
        return symbols[name] if name in symbols else getattr(c4d, name)
implementation['c4d'] = ResourceProxy()
subject = implementation['QuickStitch']()
def main():
    return subject.GetVirtualObjects(op, hh)
"""
        self.owner[c4d.OPYTHON_OPTIMIZE] = False
        self.owner.SetDeformMode(True)

    def test_all_new_styles_generate_native_mesh(self):
        self.pattern()
        for style, groups in enumerate((1, 2, 1, 1, 1, 2, 2, 3), 1):
            with self.subTest(style=style):
                self.owner[1100] = style
                result = self.build()
                self.assertEqual(len(result.GetChildren()), groups)
                self.document.InsertObject(result)
                self.document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
                self.assertGreater(polygon_count(result), 0)
                result.Remove()

    def evaluated_polygons(self,output):
        self.document.InsertObject(output)
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        output.Remove()  # Count this hierarchy without any document siblings.
        return polygon_count(output)

    def test_default_mesh_density_is_close_to_the_original(self):
        self.pattern(style=1,length=600,count=100)
        self.assertEqual(self.owner[1121],8)
        self.assertEqual(self.owner[1122],1)
        current=self.evaluated_polygons(self.build())
        self.owner[1100]=0
        self.owner[1003],self.owner[1004],self.owner[1006]=3.8,.4,0.0
        original=self.evaluated_polygons(self.build())
        self.assertGreater(current,original*.7)
        self.assertLess(current,original*1.3)
        print("Default density / 100 needles: original={}, new={}".format(original,current))

    def test_higher_mesh_quality_remains_available(self):
        self.pattern(style=1,count=3)
        low=self.evaluated_polygons(self.build())
        self.owner[1121],self.owner[1122]=12,8
        high=self.evaluated_polygons(self.build())
        self.assertGreater(high,low*4)

    def test_saved_mesh_quality_is_not_overwritten_on_import_or_copy(self):
        self.owner[1121],self.owner[1122]=12,8
        self.subject.Message(self.owner,c4d.MSG_MULTI_DOCUMENTIMPORTED,None)
        copied=self.owner.GetClone()
        self.assertTrue(self.subject.Init(copied,True))
        for owner in (self.owner,copied):
            self.assertEqual(owner[1121],12)
            self.assertEqual(owner[1122],8)

    def test_fixed_pitch_ignores_count(self):
        self.pattern(style=1, length=120, count=2)
        self.owner[1101], self.owner[1102] = 1, 10.0
        strand = paths(self.build())[0]
        self.assertEqual(strand.GetSegmentCount(), 12)
        points = strand.GetAllPoints()
        self.assertGreater(max(p.z for p in points), 110)
        self.assertLess(max(abs(p.x) for p in points), 0.001)

    def test_new_patterns_support_primitive_circle_paths(self):
        self.pattern(style=8,count=12).Remove()
        circle=c4d.BaseObject(c4d.Osplinecircle)
        circle[c4d.PRIM_CIRCLE_RADIUS]=30
        circle.InsertUnder(self.owner)
        result=self.build()
        self.assertEqual(len(result.GetChildren()),3)
        self.assertTrue(all(not p.GetSegment(i)["closed"] for p in paths(result)
                            for i in range(p.GetSegmentCount())))

    def test_count_is_distributed_across_disconnected_segments(self):
        line = self.pattern(style=1, count=12)
        line.ResizeObject(4, 2)
        line.SetSegment(0, 2, False)
        line.SetSegment(1, 2, False)
        line.SetAllPoints([c4d.Vector(0), c4d.Vector(0,0,60),
                           c4d.Vector(30,0,0), c4d.Vector(30,0,120)])
        line.Message(c4d.MSG_UPDATE)
        output = paths(self.build())[0]
        self.assertEqual(output.GetSegmentCount(), 12)
        points = output.GetAllPoints()
        start = 0
        counts = {0: 0, 30: 0}
        for i in range(output.GetSegmentCount()):
            segment = output.GetSegment(i)
            strand = points[start:start+segment["cnt"]]
            self.assertLess(max(p.x for p in strand)-min(p.x for p in strand), 0.001)
            counts[round(strand[0].x)] += 1
            start += segment["cnt"]
        self.assertEqual(counts, {0: 4, 30: 8})

    def test_closed_patterns_have_no_large_join_gap(self):
        self.pattern().Remove()
        self.circle()
        self.owner[1002] = 11  # Even-repeat patterns must resolve this at closure.
        expected=(11,22,11,12,22,22,44,88)
        for style in range(1,9):
            self.owner[1100] = style
            result=self.build()
            with self.subTest(style=style):
                self.assertEqual(sum(p.GetSegmentCount() for p in paths(result)),
                                 expected[style-1])
                for needle in self.needles(result):
                    self.assertLess((needle[0]-needle[-1]).GetLength(),25)
                    self.assertTrue(all(math.isfinite(p.x+p.y+p.z) for p in needle))
                    self.assertAlmostEqual(needle[0].y,0,places=5)
                    self.assertAlmostEqual(needle[-1].y,0,places=5)

    def test_x_crossing_separates_threads_by_diameter_and_clearance(self):
        self.pattern(style=6, length=20, count=1)
        self.owner[1106] = 0.15
        a,b = paths(self.build())
        def crossing(strand):
            return min(strand.GetAllPoints(), key=lambda p: abs(p.x)+abs(p.z-10))
        self.assertAlmostEqual(crossing(a).x, 0)
        self.assertAlmostEqual(crossing(a).y-crossing(b).y, 0.55, places=5)

    def test_mirror_reverses_slant_without_changing_path_length(self):
        self.pattern(style=3, count=1)
        first = paths(self.build())[0].GetAllPoints()
        self.owner[1108] = True
        second = paths(self.build())[0].GetAllPoints()
        self.assertEqual(vectors(c4d.Vector(-p.x,p.y,p.z) for p in first), vectors(second))

    def test_phase_shifts_pattern_along_path(self):
        self.pattern(style=1, count=10)
        first = paths(self.build())[0].GetPoint(0)
        self.owner[1107] = 0.25
        second = paths(self.build())[0].GetPoint(0)
        self.assertAlmostEqual(second.z-first.z, 3.0, places=4)

    def test_reverse_changes_chevron_direction(self):
        self.pattern(style=5, count=4)
        first=paths(self.build())[0].GetAllPoints()
        self.owner[1127]=True
        second=paths(self.build())[0].GetAllPoints()
        self.assertEqual(len(first),len(second))
        for a,b in zip(first,second):
            self.assertLess((c4d.Vector(a.x,a.y,120-a.z)-b).GetLength(),1e-7)

    def test_generator_transform_does_not_change_local_pattern(self):
        self.pattern(style=8)
        before = [p.GetAllPoints() for p in paths(self.build())]
        self.owner.SetRelPos(c4d.Vector(100,50,-30))
        self.owner.SetRelRot(c4d.Vector(.3,.2,.1))
        self.owner.SetRelScale(c4d.Vector(2))
        after = [p.GetAllPoints() for p in paths(self.build())]
        self.assertEqual([len(p) for p in before], [len(p) for p in after])
        for a, b in zip(before, after):
            self.assertLess(max((x-y).GetLength() for x,y in zip(a,b)), 0.0001)

    def test_surface_fit_on_plane_preserves_source_geometry(self):
        self.pattern(style=8)
        mesh = self.plane()
        original = vectors(mesh.GetAllPoints())
        self.owner[1110], self.owner[1109] = True, mesh
        result = self.build()
        self.assertEqual(len(result.GetChildren()), 3)
        self.assertEqual(vectors(mesh.GetAllPoints()), original)
        for strand in paths(result):
            self.assertLess(max(abs(p.x) for p in strand.GetAllPoints()), 3.1)
            self.assertAlmostEqual(min(p.y for p in strand.GetAllPoints()), 0, places=5)

    def test_surface_fit_follows_closed_cylinder(self):
        self.pattern(style=8, count=12).Remove()
        self.circle()
        count, radius = 64, 30
        mesh = c4d.PolygonObject(count*2,count)
        mesh.SetAllPoints([c4d.Vector(radius*math.cos(i*2*math.pi/count), y,
                                      radius*math.sin(i*2*math.pi/count))
                           for i in range(count) for y in (-15,15)])
        for i in range(count):
            a,b=2*i,2*((i+1)%count)
            mesh.SetPolygon(i,c4d.CPolygon(a,a+1,b+1,b))
        mesh.Message(c4d.MSG_UPDATE)
        self.document.InsertObject(mesh)
        self.owner[1110], self.owner[1109] = True, mesh
        result = self.build()
        self.assertEqual(len(result.GetChildren()),3)
        for strand in paths(result):
            radii=[math.hypot(p.x,p.z) for p in strand.GetAllPoints()]
            self.assertGreater(min(radii),29.3)
            self.assertLess(max(radii),32)
            self.assertLess(max(abs(p.y) for p in strand.GetAllPoints()),3.1)

    def test_surface_movement_invalidates_native_callback_cache(self):
        self.pattern(style=8, count=8)
        mesh = self.plane()
        self.owner[1110], self.owner[1109] = True, mesh
        self.native_callback()
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        before=paths(self.owner.GetCache())[0].GetPoint(0)
        mesh.SetRelPos(c4d.Vector(0,2,0))
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        after=paths(self.owner.GetCache())[0].GetPoint(0)
        self.assertAlmostEqual(after.y-before.y,2.0,places=4)

    def test_surface_fit_on_steering_wheel_torus(self):
        self.pattern(style=8,count=24).Remove()
        self.circle(count=96,radius=48)
        n,m=72,24
        mesh=c4d.PolygonObject(n*m,n*m)
        mesh.SetAllPoints([
            c4d.Vector((60+12*math.cos(j*2*math.pi/m))*math.cos(i*2*math.pi/n),
                       12*math.sin(j*2*math.pi/m),
                       (60+12*math.cos(j*2*math.pi/m))*math.sin(i*2*math.pi/n))
            for i in range(n) for j in range(m)])
        for i in range(n):
            for j in range(m):
                mesh.SetPolygon(i*m+j,c4d.CPolygon(
                    i*m+j,i*m+(j+1)%m,((i+1)%n)*m+(j+1)%m,((i+1)%n)*m+j))
        mesh.Message(c4d.MSG_UPDATE)
        self.document.InsertObject(mesh)
        self.owner[1110],self.owner[1109]=True,mesh
        self.owner[1111]=-.1
        for style in range(1,9):
            self.owner[1100]=style
            result=self.build()
            with self.subTest(style=style):
                self.assertTrue(result.GetChildren())
                for needle in self.needles(result):
                    distances=[math.hypot(math.hypot(p.x,p.z)-60,p.y) for p in needle]
                    self.assertGreater(min(distances),11.3)
                    self.assertLess(max(distances),14)
                    self.assertLess(distances[0],12)
                    self.assertLess(distances[-1],12)

    def test_material_slots_are_independent_and_use_thread_uvs(self):
        self.pattern(style=8)
        materials=[]
        for identifier in (1115,1116,1117):
            material=c4d.BaseMaterial(c4d.Mmaterial)
            self.document.InsertMaterial(material)
            self.owner[identifier]=material
            materials.append(material)
        result=self.build()
        for group, material in zip(result.GetChildren(), materials):
            tag=group.GetTag(c4d.Ttexture)
            self.assertEqual(tag.GetMaterial(),material)
            self.assertEqual(tag[c4d.TEXTURETAG_PROJECTION],c4d.TEXTURETAG_PROJECTION_UVW)

    def test_missing_surface_and_extreme_counts_fail_without_crashing(self):
        self.pattern(style=8)
        for configure in ("missing_surface","too_many"):
            self.owner[1110]=configure=="missing_surface"
            self.owner[1002]=8 if configure=="missing_surface" else 5000
            with redirect_stdout(io.StringIO()) as log:
                result=self.build()
            self.assertFalse(result.GetChildren())
            self.assertTrue(log.getvalue())

    def test_old_scene_without_new_parameters_defaults_to_original(self):
        self.extract(self.make_mesh())
        for identifier, unused_type, unused_default in self.namespace["patterns"].PARAMETERS.values():
            self.owner.GetDataInstance().RemoveData(identifier)
        self.assertEqual(self.namespace["patterns"].settings(self.owner)["style"],0)
        self.assertEqual(self.build().GetDown().GetType(),1018544)

    def test_new_pattern_copy_keeps_parameters_and_independent_geometry(self):
        self.pattern(style=8)
        self.owner[1107]=0.3
        copied=self.owner.GetClone()
        self.document.InsertObject(copied)
        self.assertTrue(self.subject.Init(copied,True))
        self.assertEqual(copied[1100],8)
        self.assertAlmostEqual(copied[1107],0.3)
        self.assertEqual([vectors(p.GetAllPoints()) for p in paths(self.build())],
                         [vectors(p.GetAllPoints()) for p in paths(self.build(copied))])

    def test_braid_pieces_are_independent_complete_profiles(self):
        self.pattern(style=8,count=6)
        output=self.build()
        self.assertEqual([p.GetSegmentCount() for p in paths(output)],[18,17,12])
        for path in paths(output):
            points,start=path.GetAllPoints(),0
            for index in range(path.GetSegmentCount()):
                segment=path.GetSegment(index)
                self.assertFalse(segment["closed"])
                needle=points[start:start+segment["cnt"]]
                self.assertGreaterEqual(len(needle),9)
                for tip in (needle[0],needle[-1]):
                    self.assertAlmostEqual(tip.y,0,places=5)
                self.assertAlmostEqual(max(p.y for p in needle),0.4,places=5)
                self.assertGreater(needle[1].y,needle[0].y)
                self.assertGreater(needle[-2].y,needle[-1].y)
                start+=segment["cnt"]

    def test_braid_offset_translates_the_complete_needle(self):
        self.pattern(style=8,count=4)
        def needle():
            path=paths(self.build())[0]
            return path.GetAllPoints()[:path.GetSegment(0)["cnt"]]
        self.owner[1105]=0.2
        low=needle()
        self.owner[1105]=1.2
        high=needle()
        self.assertAlmostEqual(max(p.y for p in high)-max(p.y for p in low),1.0,places=5)
        self.assertAlmostEqual(high[0].y,low[0].y,places=5)
        self.owner[1111]=-.6
        deep=needle()
        self.assertEqual(len(deep),len(high))
        for a,b in zip(high,deep):
            self.assertLess((b-a-c4d.Vector(0,-.6,0)).GetLength(),1e-8)

    def test_braid_partial_end_stitches_keep_profile_endpoints(self):
        self.pattern(style=8,count=4)
        self.owner[1107]=0.73
        for path in paths(self.build()):
            points,start=path.GetAllPoints(),0
            for index in range(path.GetSegmentCount()):
                count=path.GetSegment(index)["cnt"]
                self.assertAlmostEqual(points[start].y,0,places=5)
                self.assertAlmostEqual(points[start+count-1].y,0,places=5)
                start+=count

    def test_percent_resource_ranges_use_display_percent_units(self):
        import re
        resource=(Path(self.namespace["__file__"]).parent/
                  "res/description/quick_stitch.res").read_text(encoding="utf-8-sig")
        for name,minimum,maximum in (("PHASE",0,100),("LEAN",5,95)):
            block=re.search(r"REAL QUICK_STITCH_"+name+r"\s*\{([^}]+)\}",resource).group(1)
            properties=dict((key,float(number)) for key,number in re.findall(
                r"\b(MIN|MAX|MINSLIDER|MAXSLIDER|STEP)\s+([\d.]+)\s*;",block))
            self.assertEqual(properties,dict(MIN=minimum,MAX=maximum,MINSLIDER=minimum,
                                             MAXSLIDER=maximum,STEP=1))

    def test_native_percent_description_allows_full_range(self):
        if not c4d.plugins.FindPlugin(1054816,c4d.PLUGINTYPE_OBJECT):
            self.skipTest("No installed QuickStitch description to inspect.")
        class DescriptionHost:
            # Reuse the installed description without initializing the installed
            # plugin, whose older code could overwrite real global preferences.
            def GetType(unused_self):
                return 1054816

            def __getitem__(unused_self, field):
                return self.owner[field]
        description=c4d.Description()
        result=self.subject.GetDDescription(DescriptionHost(),description,0)
        self.assertTrue(result[0])
        for field,minimum,maximum in ((1107,0,1),(1125,.05,.95)):
            identifier=c4d.DescID(c4d.DescLevel(field,c4d.DTYPE_REAL,0))
            parameter=description.GetParameterI(identifier,None)
            if parameter is None:
                self.skipTest("Installed description predates pattern parameters.")
            self.assertEqual(parameter[c4d.DESC_MIN],minimum)
            self.assertEqual(parameter[c4d.DESC_MAX],maximum)
            self.assertEqual(parameter[c4d.DESC_MINSLIDER],minimum)
            self.assertEqual(parameter[c4d.DESC_MAXSLIDER],maximum)
            self.assertEqual(parameter[c4d.DESC_STEP],0.01)

    def test_editable_profile_changes_every_style_curve(self):
        self.pattern(style=8,count=4)
        engine=self.namespace["patterns"]
        for style in range(1,9):
            self.owner[1100]=style
            self.owner[1128]=engine.default_shape(0)
            first=paths(self.build())[0].GetAllPoints()
            self.owner[1128]=engine.default_shape(2)
            second=paths(self.build())[0].GetAllPoints()
            with self.subTest(style=style):
                self.assertAlmostEqual(max(p.y for p in first)-max(p.y for p in second),.28,places=5)

    def test_default_profile_matches_original_knots_and_native_curve(self):
        original=self.owner[1007]
        current=self.owner[1128]
        expected=((0,0,0,0,.5),(.5,1,-.25,0,.25),(1,0,0,.5,0))
        for a,b,values in zip(original.GetKnots(),current.GetKnots(),expected):
            self.assertEqual(a,b)
            self.assertEqual((b["vPos"].x,b["vPos"].y,b["vTangentLeft"].x,
                              b["vTangentLeft"].y,b["vTangentRight"].x
                              if b["vPos"].x else b["vTangentRight"].y),values)
        native=c4d.SplineObject(3,c4d.SPLINETYPE_BEZIER)
        self.namespace["create_spline_from_splinedata"](original,native,1,1)
        profile=self.namespace["patterns"].NeedleProfile(current)
        for t in (0,.01,.125,.25,.5,.75,.875,.99,1):
            point=(native.GetPoint(0) if t==0 else native.GetPoint(2) if t==1 else
                   native.GetSplinePoint(t))+c4d.Vector(.5,0,0)
            self.assertLess((profile.point(t)-point).GetLength(),1e-9)

    def test_retired_entry_parameters_have_no_effect_for_every_style(self):
        self.pattern(count=3)
        for style in range(1,9):
            self.owner[1100]=style
            self.owner[1123],self.owner[1129],self.owner[1124]=0.0,0.0,0.0
            first=[vectors(p.GetAllPoints()) for p in paths(self.build())]
            self.owner[1123],self.owner[1129],self.owner[1124]=100.0,.25,1.0
            second=[vectors(p.GetAllPoints()) for p in paths(self.build())]
            with self.subTest(style=style):
                self.assertEqual(first,second)

    def test_zero_arch_has_no_vertical_legs_in_every_style(self):
        self.pattern(count=3)
        self.owner[1105]=0.0
        self.owner[1111]=.37
        for style in range(1,9):
            self.owner[1100]=style
            result=self.build()
            for group,path in enumerate(paths(result)):
                points=path.GetAllPoints()
                with self.subTest(style=style,group=group):
                    if style==6 and group==0:  # X's explicit crossing clearance.
                        self.assertAlmostEqual(max(p.y for p in points),.37+.55,places=5)
                    else:
                        self.assertLess(max(abs(p.y-.37) for p in points),1e-8)
            for needle in self.needles(result):
                self.assertAlmostEqual(needle[0].y,.37,places=7)
                self.assertAlmostEqual(needle[-1].y,.37,places=7)

    def assert_matches_original_curve(self,needle,shape,height,offset,center=10,width=3.8):
        original=c4d.SplineObject(shape.GetKnotCount(),c4d.SPLINETYPE_BEZIER)
        self.namespace["create_spline_from_splinedata"](shape,original,width,height)
        for point in needle:
            if abs(point.z-(original.GetPoint(0).x+center))<1e-10:
                expected=original.GetPoint(0)
                self.assertAlmostEqual(point.y,expected.y+offset,places=7)
                continue
            if abs(point.z-(original.GetPoint(original.GetPointCount()-1).x+center))<1e-10:
                expected=original.GetPoint(original.GetPointCount()-1)
                self.assertAlmostEqual(point.y,expected.y+offset,places=7)
                continue
            low,high=0.,1.
            for unused in range(48):
                mid=(low+high)*.5
                if original.GetSplinePoint(mid).x+center<point.z:
                    low=mid
                else:
                    high=mid
            expected=original.GetSplinePoint((low+high)*.5)
            self.assertAlmostEqual(point.y,expected.y+offset,places=7)
        for i in range(201):
            p=original.GetSplinePoint(i/200)
            point=c4d.Vector(0,p.y+offset,p.x+center)
            distances=[]
            for a,b in zip(needle,needle[1:]):
                d=b-a
                blend=max(0,min(1,(point-a).Dot(d)/max(1e-24,d.GetLengthSquared())))
                distances.append((point-(a+d*blend)).GetLength())
            self.assertLessEqual(min(distances),max(3e-6,height*.01))

    def test_entire_needle_matches_original_at_normal_low_and_zero_heights(self):
        self.pattern(style=1,length=20,count=1)
        self.owner[1121]=12  # Exercise the original high-precision tolerance.
        self.owner[1111]=.31
        for height in (1.1,.4,.05,.001,0):
            self.owner[1105]=height
            needle=list(self.needles(self.build()))[0]
            with self.subTest(height=height):
                self.assert_matches_original_curve(needle,self.owner[1007],height,.31)
                self.assertAlmostEqual(min(p.y for p in needle),.31,places=7)
                self.assertAlmostEqual(max(p.y for p in needle),.31+height,places=7)

    def test_edited_endpoints_are_used_without_hidden_extensions_or_rescaling(self):
        self.pattern(style=1,length=20,count=1)
        self.owner[1121]=12
        shape=self.owner[1128]
        knots=shape.GetKnots()
        knots[0]["vPos"]=c4d.Vector(.1,-.4,0)
        knots[-1]["vPos"]=c4d.Vector(.9,-.2,0)
        for i,knot in enumerate(knots):
            shape.SetKnot(i,**knot)
        self.owner[1128]=shape
        needle=list(self.needles(self.build()))[0]
        self.assertAlmostEqual(needle[0].z,8.1+.1*3.8,places=7)
        self.assertAlmostEqual(needle[-1].z,8.1+.9*3.8,places=7)
        self.assertAlmostEqual(needle[0].y,-.16,places=7)
        self.assertAlmostEqual(needle[-1].y,-.08,places=7)
        self.assert_matches_original_curve(needle,shape,.4,0)

    def test_editor_uses_original_zero_to_one_view_without_changing_shape(self):
        self.assertIsNone(self.owner[1007].GetRange())
        self.assertEqual(self.owner[1128].GetKnots(),self.owner[1007].GetKnots())
        limits=self.owner[1128].GetRange()
        self.assertEqual((limits["xmin"],limits["xmax"],limits["ymin"],limits["ymax"]),(0,1,0,1))

    def test_thickness_never_raises_or_lowers_the_complete_profile(self):
        self.pattern(count=2)
        for style in range(1,9):
            self.owner[1100],self.owner[1005]=style,.15
            thin=paths(self.build())
            self.owner[1005]=.8
            thick=paths(self.build())
            with self.subTest(style=style):
                for group,(a,b) in enumerate(zip(thin,thick)):
                    if style==6 and group==0:
                        # The upper X thread changes its explicit crossing gap.
                        continue
                    self.assertEqual(vectors(a.GetAllPoints()),vectors(b.GetAllPoints()))
                for needle in self.needles(self.build()):
                    self.assertAlmostEqual(needle[0].y,0,places=7)
                    self.assertAlmostEqual(needle[-1].y,0,places=7)

    def test_removed_entry_controls_are_absent_and_offset_allows_negative_values(self):
        import re
        resource=(Path(self.namespace["__file__"]).parent/
                  "res/description/quick_stitch.res").read_text(encoding="utf-8-sig")
        for name in ("EMBED","ENTRY_LENGTH","ROUNDNESS"):
            self.assertNotRegex(resource,r"\bREAL QUICK_STITCH_"+name+r"\b")
        self.assertNotIn("BUTTON QUICK_STITCH_APPLY_PRESET",resource)
        block=re.search(r"REAL QUICK_STITCH_SURFACE_OFFSET\s*\{([^}]+)\}",resource).group(1)
        self.assertNotRegex(block,r"\bMIN\b")

    def test_offset_edit_updates_the_complete_native_callback_cache(self):
        self.pattern(style=2,count=2)
        self.native_callback()
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        first=[p.GetAllPoints() for p in paths(self.owner.GetCache())]
        self.owner[1111]=-.35
        self.owner.SetDirty(c4d.DIRTYFLAGS_DATA)
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        second=[p.GetAllPoints() for p in paths(self.owner.GetCache())]
        self.assertEqual([len(p) for p in first],[len(p) for p in second])
        for a,b in zip(first,second):
            for p,q in zip(a,b):
                self.assertLess((q-p-c4d.Vector(0,-.35,0)).GetLength(),1e-8)

    def test_tangent_edits_change_shape_without_changing_crown_height(self):
        self.pattern(style=1,count=1)
        first=list(self.needles(self.build()))[0]
        shape=self.owner[1128]
        knot=shape.GetKnots()[1]
        knot["vTangentLeft"]=c4d.Vector(-.1,0,0)
        knot["vTangentRight"]=c4d.Vector(.1,0,0)
        shape.SetKnot(1,**knot)
        self.owner[1128]=shape
        second=list(self.needles(self.build()))[0]
        self.assertAlmostEqual(max(p.y for p in first),max(p.y for p in second),places=7)
        self.assertNotEqual(vectors(first),vectors(second))

    def set_profile_parameter(self,field,value):
        result=self.subject.SetDParameter(self.owner,c4d.DescID(c4d.DescLevel(field)),
                                          value,c4d.DESCFLAGS_SET_USERINTERACTION)
        self.assertTrue(result[0])
        self.assertTrue(result[1]&c4d.DESCFLAGS_SET_PARAM_SET)

    def test_profile_presets_apply_immediately_without_a_button(self):
        self.pattern(style=1,count=1)
        for preset in (2,1,3,0):
            with self.subTest(preset=preset):
                self.set_profile_parameter(1130,preset)
                self.assertEqual(self.owner[1130],preset)
                self.assertEqual(self.owner[1128].GetKnots(),
                                 self.namespace["patterns"].default_shape(preset).GetKnots())
                self.assertEqual(self.owner[1128].GetRange()["ymin"],0)

    def test_preset_and_curve_restore_together_in_one_undo_step(self):
        self.pattern(style=1,count=1)
        self.set_profile_parameter(1128,self.namespace["patterns"].editable_shape(preset=1))
        before=self.owner[1128].GetKnots()
        before_preset=self.owner[1130]
        # The Attribute Manager owns this undo transaction; SetDParameter must
        # update both fields inside it without adding another undo operation.
        self.document.StartUndo()
        self.document.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL,self.owner)
        self.set_profile_parameter(1130,2)
        self.document.EndUndo()
        applied=self.owner[1128].GetKnots()
        self.assertAlmostEqual(applied[1]["vPos"].y,.3)
        self.assertTrue(self.document.DoUndo())
        self.assertEqual(self.owner[1128].GetKnots(),before)
        self.assertEqual(self.owner[1130],before_preset)
        self.assertTrue(self.document.DoRedo())
        self.assertEqual(self.owner[1128].GetKnots(),applied)
        self.assertEqual(self.owner[1130],2)

    def test_manual_curve_edits_show_custom_and_can_switch_back_to_original(self):
        self.pattern(style=1,count=1)
        original=self.owner[1007].GetKnots()
        edited=self.namespace["patterns"].editable_shape(preset=2)
        self.set_profile_parameter(1128,edited)
        self.assertEqual(self.owner[1130],4)
        self.set_profile_parameter(1130,4)
        self.assertEqual(self.owner[1128].GetKnots(),edited.GetKnots())
        self.set_profile_parameter(1130,0)
        self.assertEqual(self.owner[1130],0)
        self.assertEqual(self.owner[1128].GetKnots(),original)
        self.assertEqual(self.owner[1007].GetKnots(),original)

    def test_selecting_curve_knots_does_not_change_the_active_preset(self):
        self.pattern(style=1,count=1)
        curve=self.owner[1128]
        curve.SelectAll()
        self.set_profile_parameter(1128,curve)
        self.assertEqual(self.owner[1130],0)
        self.assertTrue(self.namespace["patterns"].matches_profile_preset(self.owner[1128],0))

    def test_old_editor_range_migrates_without_rescaling_existing_geometry(self):
        self.pattern(style=1,count=1)
        shape=self.namespace["patterns"].default_shape(2)
        knot=shape.GetKnots()[0]
        knot["vPos"]=c4d.Vector(0,-.2,0)
        shape.SetKnot(0,**knot)
        shape.SetRange(0,1,.1,-1,1,.1)
        self.owner.GetDataInstance()[1128]=shape
        self.owner.GetDataInstance()[1130]=0
        before=self.owner[1128].GetKnots()
        geometry=[vectors(p.GetAllPoints()) for p in paths(self.build())]
        self.subject.Message(self.owner,c4d.MSG_MULTI_DOCUMENTIMPORTED,None)
        self.assertEqual(self.owner[1128].GetKnots(),before)
        self.assertEqual(self.owner[1128].GetRange()["ymin"],0)
        self.assertEqual(self.owner[1128].GetRange()["ymax"],1)
        self.assertEqual(self.owner[1130],4)
        self.assertEqual([vectors(p.GetAllPoints()) for p in paths(self.build())],geometry)

    def test_import_initializes_missing_profile_without_overwriting_custom_curve(self):
        for field in (1128,1130):
            self.owner.GetDataInstance().RemoveData(field)
        self.assertIsNone(self.owner[1128])
        self.assertTrue(self.subject.Message(self.owner,c4d.MSG_MULTI_DOCUMENTIMPORTED,None))
        self.assertEqual(self.owner[1128].GetKnots(),self.owner[1007].GetKnots())
        self.assertIsNone(self.owner[1129])
        self.assertEqual(self.owner[1130],0)
        self.owner[1128]=self.namespace["patterns"].default_shape(2)
        self.owner[1129]=.17
        before=self.owner[1128].GetKnots()
        self.subject.Message(self.owner,c4d.MSG_MULTI_DOCUMENTIMPORTED,None)
        self.assertEqual(self.owner[1128].GetKnots(),before)
        self.assertAlmostEqual(self.owner[1129],.17)

    def test_profile_edit_invalidates_native_callback_cache(self):
        self.pattern(style=8,count=2)
        self.native_callback()
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        first=max(p.y for path in paths(self.owner.GetCache()) for p in path.GetAllPoints())
        self.set_profile_parameter(1130,2)
        self.document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        second=max(p.y for path in paths(self.owner.GetCache()) for p in path.GetAllPoints())
        self.assertAlmostEqual(first-second,.28,places=5)

    def test_custom_profile_is_independent_after_cloning(self):
        self.pattern(style=8,count=2)
        copied=self.owner.GetClone()
        self.document.InsertObject(copied)
        self.assertTrue(self.subject.Init(copied,True))
        copied[1128]=self.namespace["patterns"].default_shape(2)
        self.assertAlmostEqual(self.owner[1128].GetKnots()[1]["vPos"].y,1)
        self.assertAlmostEqual(copied[1128].GetKnots()[1]["vPos"].y,.3)

    def test_invalid_profiles_return_empty_output_with_a_message(self):
        self.pattern(style=8,count=2)
        shape=c4d.SplineData()
        shape.DeleteAllPoints()
        self.owner[1128]=shape
        output=io.StringIO()
        with redirect_stdout(output):
            result=self.build()
        self.assertEqual(result.GetChildren(),[])
        self.assertIn("control points",output.getvalue())

    def test_cubic_and_linear_editor_interpolation_are_supported(self):
        engine=self.namespace["patterns"]
        for mode in (1,2):
            shape=engine.default_shape()
            for i,knot in enumerate(shape.GetKnots()):
                knot["interpol"]=mode
                shape.SetKnot(i,**knot)
            profile=engine.NeedleProfile(shape)
            for t in (.125,.25,.625,.75):
                expected=shape.GetPoint(t)
                point=profile.point(t)
                if mode==1:
                    # Geometric comparison: native linear spans ease along X.
                    expected=shape.GetPoint(point.x)
                self.assertAlmostEqual(point.y,expected.y,places=5)

    def needles(self,output):
        for path in paths(output):
            points,start=path.GetAllPoints(),0
            for index in range(path.GetSegmentCount()):
                segment=path.GetSegment(index)
                self.assertFalse(segment["closed"])
                needle=points[start:start+segment["cnt"]]
                minimum=self.namespace["patterns"].sampling_detail(
                    self.namespace["patterns"].settings(self.owner))+1
                self.assertGreaterEqual(len(needle),minimum)
                yield needle
                start+=segment["cnt"]

    def test_every_style_uses_independent_complete_profiles(self):
        self.pattern(length=120,count=6)
        for style,expected in enumerate((6,12,6,6,12,12,24,47),1):
            self.owner[1100]=style
            result=self.build()
            with self.subTest(style=style):
                needles=list(self.needles(result))
                self.assertEqual(len(needles),expected)
                for needle in needles:
                    self.assertAlmostEqual(needle[0].y,0,places=5)
                    self.assertAlmostEqual(needle[-1].y,0,places=5)
                    self.assertGreater(needle[1].y,needle[0].y)
                    self.assertGreater(needle[-2].y,needle[-1].y)
                    self.assertGreater(max(p.y for p in needle),0.39)

    def test_arch_and_whole_profile_offset_work_for_every_style(self):
        self.pattern(count=4)
        for style in range(1,9):
            self.owner[1100]=style
            self.owner[1111]=0.0
            self.owner[1105]=0.2
            low=list(self.needles(self.build()))[0]
            self.owner[1105]=1.2
            high=list(self.needles(self.build()))[0]
            self.owner[1111]=-.6
            deep=list(self.needles(self.build()))[0]
            with self.subTest(style=style):
                self.assertAlmostEqual(max(p.y for p in high)-max(p.y for p in low),1,places=5)
                self.assertAlmostEqual(low[0].y,high[0].y,places=5)
                self.assertAlmostEqual(deep[0].y-high[0].y,-0.6,places=5)
                self.assertEqual(len(high),len(deep))
                for a,b in zip(high,deep):
                    self.assertLess((b-a-c4d.Vector(0,-.6,0)).GetLength(),1e-8)

    def test_partial_end_pieces_keep_the_whole_curve_for_every_style(self):
        self.pattern(count=4)
        self.owner[1107]=0.73
        for style in range(1,9):
            self.owner[1100]=style
            for needle in self.needles(self.build()):
                with self.subTest(style=style):
                    self.assertAlmostEqual(needle[0].y,0,places=5)
                    self.assertAlmostEqual(needle[-1].y,0,places=5)

    def test_every_style_fits_the_complete_profile_to_skin(self):
        self.pattern(count=4)
        self.owner[1110],self.owner[1109]=True,self.plane()
        self.owner[1111]=-.3
        for style in range(1,9):
            self.owner[1100]=style
            for needle in self.needles(self.build()):
                with self.subTest(style=style):
                    self.assertAlmostEqual(needle[0].y,-.3,places=5)
                    self.assertAlmostEqual(needle[-1].y,-.3,places=5)

    def test_whole_profile_offset_follows_surface_normal_when_layout_rotates(self):
        self.pattern(count=4)
        self.owner[1110],self.owner[1109]=True,self.plane()
        self.owner[1010]=0.5
        self.owner[1111]=-.3
        for style in range(1,9):
            self.owner[1100]=style
            for needle in self.needles(self.build()):
                with self.subTest(style=style):
                    self.assertAlmostEqual(needle[0].y,-.3,places=5)
                    self.assertAlmostEqual(needle[-1].y,-.3,places=5)

    def test_partial_x_keeps_clearance_at_the_actual_crossing(self):
        self.pattern(style=6,length=20,count=4)
        self.owner[1107]=0.2
        output=self.build()
        a,b=paths(output)
        def crossing(path):
            return min(path.GetAllPoints(),key=lambda p:abs(p.x)+abs(p.z-18.5))
        upper,lower=crossing(a),crossing(b)
        self.assertAlmostEqual(upper.x,0,places=5)
        self.assertAlmostEqual(upper.z,18.5,places=5)
        self.assertAlmostEqual(upper.y-lower.y,0.55,places=5)
        for needle in self.needles(output):
            self.assertAlmostEqual(needle[0].y,0,places=5)
            self.assertAlmostEqual(needle[-1].y,0,places=5)

    def test_language_switching_and_about_metadata(self):
        engine = self.namespace["patterns"]
        self.assertEqual(engine.PLUGIN_NAME, "Quick Stitch Pro")
        self.assertEqual(engine.PLUGIN_VERSION, "V1.0")
        self.assertEqual(engine.PLUGIN_AUTHOR, "Zachary Shee")
        self.assertIn("Zachary Shee", engine.UI_LABELS["en"][1135])
        self.assertIn("Zachary Shee", engine.UI_LABELS["zh"][1135])
        self.assertIn("V1.0", engine.UI_LABELS["en"][1134])
        self.assertIn("V1.0", engine.UI_LABELS["zh"][1134])

        previous_lang = engine.load_global_language()
        try:
            self.set_profile_parameter(1132, engine.LANG_ZH)
            self.assertEqual(self.owner[1132], engine.LANG_ZH)
            self.assertEqual(engine.effective_language(self.owner), "zh")
            status_msg = engine.format_error(
                ValueError("Select at least one edge on the linked object."),
                self.owner, for_console=False)
            console_msg = engine.format_error(
                ValueError("Needle Profile needs between 2 and 128 control points."),
                self.owner, for_console=True)
            self.assertIn("至少选择一条边", status_msg)
            self.assertIn("control points", console_msg)

            self.set_profile_parameter(1132, engine.LANG_EN)
            self.assertEqual(self.owner[1132], engine.LANG_EN)
            self.assertEqual(engine.effective_language(self.owner), "en")
        finally:
            self.set_profile_parameter(1132, previous_lang)

    def test_initialization_preserves_language_with_setter_callbacks_enabled(self):
        engine = self.namespace["patterns"]
        base = self.namespace["QuickStitch"]

        class InitSubject(base):
            def InitAttr(subject, host, datatype, field):
                return super().InitAttr(host.node, datatype, field)

        class InitHost(_support["DirectCallHost"]):
            def __setitem__(host, field, value):
                result = subject.SetDParameter(
                    host.node, c4d.DescID(c4d.DescLevel(field)), value,
                    c4d.DESCFLAGS_SET_NONE)
                if not result:
                    host.node[field] = value

        for lang in (engine.LANG_ZH, engine.LANG_EN, engine.LANG_AUTO):
            with self.subTest(language=lang):
                self.language_preferences["language"] = lang
                self.language_save.reset_mock()
                node = c4d.BaseObject(c4d.Opython)
                node.SetDeformMode(False)
                self.document.InsertObject(node)
                subject = InitSubject()
                self.assertTrue(subject.Init(InitHost(node)))
                self.assertEqual(node[1132], lang)
                self.assertEqual(self.language_preferences["language"], lang)
                self.language_save.assert_not_called()

    def test_noninteractive_language_writes_do_not_change_global_preference(self):
        engine = self.namespace["patterns"]
        self.language_preferences["language"] = engine.LANG_ZH
        self.language_save.reset_mock()
        self.subject.SetDParameter(self.owner, c4d.DescID(c4d.DescLevel(1132)),
                                   engine.LANG_EN, c4d.DESCFLAGS_SET_NONE)
        self.assertEqual(self.owner[1132], engine.LANG_EN)
        self.assertEqual(self.language_preferences["language"], engine.LANG_ZH)
        self.language_save.assert_not_called()
        self.set_profile_parameter(1132, engine.LANG_AUTO)
        self.assertEqual(self.language_preferences["language"], engine.LANG_AUTO)

    def test_language_changes_reuse_geometry_even_when_native_cache_is_dirty(self):
        self.pattern(style=8, count=3)
        engine = self.namespace["patterns"]
        host = CachedHost(self.owner)
        with patch.object(engine, "build", wraps=engine.build) as build:
            host.cache = self.subject.GetVirtualObjects(host, None)
            first = host.cache
            self.assertEqual(build.call_count, 1)
            for lang in (engine.LANG_ZH, engine.LANG_AUTO, engine.LANG_EN):
                self.set_profile_parameter(1132, lang)
                result = self.subject.GetVirtualObjects(host, None)
                self.assertIs(result, first)
                self.assertEqual(build.call_count, 1)

    def test_language_changes_do_not_hide_simultaneous_geometry_edits(self):
        self.pattern(style=1, count=3)
        engine = self.namespace["patterns"]
        host = CachedHost(self.owner)
        with patch.object(engine, "build", wraps=engine.build) as build:
            host.cache = self.subject.GetVirtualObjects(host, None)
            first = host.cache
            self.owner[1105] = 1.2
            self.set_profile_parameter(1132, engine.LANG_ZH)
            result = self.subject.GetVirtualObjects(host, None)
            self.assertIsNot(result, first)
            self.assertEqual(build.call_count, 2)
            self.assertAlmostEqual(max(p.y for p in paths(result)[0].GetAllPoints()), 1.2)

    def test_language_cache_tracks_material_links_independently_of_names(self):
        self.pattern(style=1, count=3)
        engine = self.namespace["patterns"]
        materials = []
        for unused in range(2):
            material = c4d.BaseMaterial(c4d.Mmaterial)
            material.SetName("Thread")
            self.document.InsertMaterial(material)
            materials.append(material)
        self.owner[1115] = materials[0]
        host = CachedHost(self.owner)
        with patch.object(engine, "build", wraps=engine.build) as build:
            host.cache = self.subject.GetVirtualObjects(host, None)
            first = host.cache
            self.set_profile_parameter(1132, engine.LANG_ZH)
            self.assertIs(self.subject.GetVirtualObjects(host, None), first)
            self.assertEqual(build.call_count, 1)
            self.owner[1115] = materials[1]
            self.set_profile_parameter(1132, engine.LANG_EN)
            result = self.subject.GetVirtualObjects(host, None)
            self.assertIsNot(result, first)
            self.assertEqual(build.call_count, 2)
            self.assertEqual(result.GetDown().GetTag(c4d.Ttexture).GetMaterial(),
                             materials[1])

    def test_language_changes_do_not_hide_path_or_surface_changes(self):
        guide = self.pattern(style=1, count=3)
        engine = self.namespace["patterns"]
        self.owner[1110], self.owner[1109] = True, self.plane()
        host = CachedHost(self.owner)
        with patch.object(engine, "build", wraps=engine.build) as build:
            host.cache = self.subject.GetVirtualObjects(host, None)
            self.owner.SetRelPos(c4d.Vector(0, 2, 0))
            self.set_profile_parameter(1132, engine.LANG_ZH)
            host.cache = self.subject.GetVirtualObjects(host, None)
            self.assertEqual(build.call_count, 2)
            self.assertAlmostEqual(paths(host.cache)[0].GetPoint(0).y, -2, places=5)
            guide.SetPoint(1, c4d.Vector(0, 0, 150))
            guide.Message(c4d.MSG_UPDATE)
            host.inputs_changed = True
            self.set_profile_parameter(1132, engine.LANG_EN)
            self.subject.GetVirtualObjects(host, None)
            self.assertEqual(build.call_count, 3)

    def test_language_changes_reuse_the_legacy_cloner_cache(self):
        self.extract(self.make_mesh())
        engine = self.namespace["patterns"]
        host = CachedHost(self.owner)
        with patch.object(self.subject, "_remember_geometry",
                          wraps=self.subject._remember_geometry) as remember:
            host.cache = self.subject.GetVirtualObjects(host, None)
            first = host.cache
            self.assertEqual(remember.call_count, 1)
            self.set_profile_parameter(1132, engine.LANG_ZH)
            self.assertIs(self.subject.GetVirtualObjects(host, None), first)
            self.assertEqual(remember.call_count, 1)

    def test_generator_movement_with_surface_fit_invalidates_cache(self):
        self.pattern(style=1, count=4)
        mesh = self.plane()
        self.owner[1110], self.owner[1109] = True, mesh
        self.native_callback()
        self.document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        first = paths(self.owner.GetCache())[0].GetPoint(0)
        self.owner.SetRelPos(c4d.Vector(0, 5, 0))
        self.document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        second = paths(self.owner.GetCache())[0].GetPoint(0)
        # Since the path is a child of owner, moving owner +5Y moves local
        # projected points to Y=-5 in owner space so world Y stays on the Y=0 plane.
        self.assertAlmostEqual(second.y - first.y, -5.0, places=4)


def run(root=None):
    active=c4d.documents.GetActiveDocument()
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    PatternRegression.namespace=_support["load_workspace"](root)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PatternRegression)
    result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    if c4d.documents.GetActiveDocument()!=active:
        raise RuntimeError("Active document changed.")
    if not result.wasSuccessful():
        raise RuntimeError("Pattern regression checks failed.")
    return result.testsRun


if __name__=="__main__":
    run()
