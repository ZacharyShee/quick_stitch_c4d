"""Compare editable needle profiles using native generated paths in a detached doc."""
from pathlib import Path

import c4d


def support(root):
    path = root / "examples/build_examples.py"
    scope = {"__name__": "profile_example_support", "__file__": str(path)}
    exec(compile(path.read_text(), str(path), "exec"), scope)
    return scope


def first_needle(output):
    for sweep in output.GetChildren():
        for path in sweep.GetChildren():
            if isinstance(path, c4d.SplineObject):
                return path.GetAllPoints()[:path.GetSegment(0)["cnt"]]
    raise RuntimeError("Example contains no needle.")


def variants(engine):
    names = ("01  Complete original profile", "02  Low arch / same curve",
             "03  Zero arch / straight", "04  Whole curve lowered",
             "05  Edited tangent handles", "06  Custom asymmetric points")
    curves = [engine.default_shape() for unused in names]
    knot = curves[4].GetKnots()[1]
    knot["vTangentLeft"] = c4d.Vector(-.1, 0, 0)
    knot["vTangentRight"] = c4d.Vector(.1, 0, 0)
    curves[4].SetKnot(1, **knot)
    shape = c4d.SplineData()
    shape.MakePointBuffer(4)
    shape.SetKnot(0, c4d.Vector(0), 65536,
                  vTangentRight=c4d.Vector(0, .3, 0))
    shape.SetKnot(1, c4d.Vector(.3, 1, 0), 131072,
                  vTangentLeft=c4d.Vector(-.12, 0, 0),
                  vTangentRight=c4d.Vector(.12, 0, 0))
    shape.SetKnot(2, c4d.Vector(.7, .55, 0), 196608,
                  vTangentLeft=c4d.Vector(-.1, .15, 0),
                  vTangentRight=c4d.Vector(.1, -.15, 0))
    shape.SetKnot(3, c4d.Vector(1, 0, 0), 262144,
                  vTangentLeft=c4d.Vector(0, .25, 0))
    curves[5] = shape
    return names, curves


def original_reference(config):
    """Use Original / Custom's knot/tangent transfer, mapped onto the Z axis."""
    knots = config["needle_shape"].GetKnots()
    curve = c4d.SplineObject(len(knots), c4d.SPLINETYPE_BEZIER)
    width, height = config["stitch_length"], config["arch"]
    start = (12-width)*.5
    for index, knot in enumerate(knots):
        p = knot["vPos"]
        curve.SetPoint(index, c4d.Vector(0, p.y*height+config["surface_offset"], start+p.x*width))
        tangents = [c4d.Vector(0, knot[key].y*height, knot[key].x*width)
                    for key in ("vTangentLeft", "vTangentRight")]
        curve.SetTangent(index, *tangents)
    curve[c4d.SPLINEOBJECT_ANGLE] = c4d.utils.DegToRad(15)
    curve.Message(c4d.MSG_UPDATE)
    return curve


def draw(engine, outputs, configs, names, filename):
    clip = c4d.bitmaps.GeClipMap()
    clip.Init(1600, 1050, 32)
    clip.BeginDraw()
    font = c4d.bitmaps.GeClipMap.GetDefaultFont(c4d.GE_FONT_DEFAULT_SYSTEM)
    clip.SetColor(17, 22, 30); clip.FillRect(0, 0, 1599, 1049)
    clip.SetFont(font, 32); clip.SetColor(237, 244, 252)
    clip.TextAt(32, 22, "FULL-CURVE NEEDLES  |  normal, low and zero arch")
    clip.SetFont(font, 17); clip.SetColor(159, 178, 200)
    clip.TextAt(34, 72, "Blue: generated centerline. Orange dots: original native Bezier. Shaded area: below the skin.")
    for index, (output, config, name) in enumerate(zip(outputs, configs, names)):
        left, top = 30+(index % 3)*523, 118+(index//3)*454
        clip.SetColor(28, 35, 46); clip.FillRect(left, top, left+499, top+432)
        clip.SetFont(font, 22); clip.SetColor(231, 239, 250)
        clip.TextAt(left+17, top+15, name)
        clip.SetFont(font, 15); clip.SetColor(151, 174, 199)
        label = "Arch: {:g}     Profile Offset: {:g}     Width: {:g}".format(
            config["arch"], config["surface_offset"], config["stitch_length"])
        clip.TextAt(left+18, top+51, label)
        profile = engine.NeedleProfile(config["needle_shape"])
        clip.SetColor(19, 27, 37); clip.FillRect(left+19, top+84, left+480, top+218)
        clip.SetColor(69, 85, 105)
        clip.Line(left+48, top+198, left+451, top+198)
        clip.Line(left+48, top+105, left+48, top+198)
        clip.SetFont(font, 13); clip.SetColor(134, 156, 183)
        clip.TextAt(left+370, top+88, "Profile editor")
        curve = [profile.point(i/240) for i in range(241)]
        clip.SetColor(105, 200, 255)
        for p, q in zip(curve, curve[1:]):
            for offset in (0, 1):
                clip.Line(round(left+49+p.x*400), round(top+197-p.y*88+offset),
                          round(left+49+q.x*400), round(top+197-q.y*88+offset))
        for knot in config["needle_shape"].GetKnots():
            p = knot["vPos"]
            x, y = round(left+49+p.x*400), round(top+197-p.y*88)
            clip.FillRect(x-3, y-3, x+3, y+3)
        baseline = top+326
        clip.SetColor(46, 54, 65)
        clip.FillRect(left+19, baseline, left+480, top+405)
        clip.SetColor(125, 145, 169)
        clip.Line(left+19, baseline, left+480, baseline)
        clip.SetFont(font, 13); clip.TextAt(left+25, baseline+7, "skin")
        clip.SetColor(157, 177, 201)
        clip.TextAt(left+20, top+237, "Complete generated needle / original reference")
        needle = first_needle(output)
        first, last = needle[0], needle[-1]
        direction = c4d.Vector(last.x-first.x, 0, last.z-first.z).GetNormalized()
        width = (last-first).Dot(direction)
        x0 = left+(500-width*47)/2
        for p, q in zip(needle, needle[1:]):
            clip.SetColor(*((113, 207, 255) if max(p.y, q.y) >= 0 else (134, 151, 173)))
            for offset in (-1, 0, 1):
                clip.Line(round(x0+(p-first).Dot(direction)*47), round(baseline-p.y*47+offset),
                          round(x0+(q-first).Dot(direction)*47), round(baseline-q.y*47+offset))
        reference = original_reference(config)
        clip.SetColor(255, 184, 100)
        for i in range(0, 81, 4):
            point = (reference.GetPoint(0) if i == 0 else
                     reference.GetPoint(reference.GetPointCount()-1) if i == 80 else
                     reference.GetSplinePoint(i/80))
            x = round(x0+(point-first).Dot(direction)*47)
            y = round(baseline-point.y*47)
            clip.FillRect(x-1, y-1, x+1, y+1)
        clip.SetFont(font, 13); clip.SetColor(150, 173, 200)
        note = ("Height 0 flattens the whole needle; no vertical legs" if index == 2 else
                "Offset translates both ends and crown together" if index == 3 else
                "Original reference and generated curve coincide")
        clip.TextAt(left+19, top+411, note)
    clip.EndDraw()
    if clip.GetBitmap().Save(str(filename), c4d.FILTER_PNG, None, 0) != c4d.IMAGERESULT_OK:
        raise RuntimeError("Could not save profile controls preview.")


def run(root=None, overwrite=False):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    scene = root / "examples/Needle_Profile_Controls.c4d"
    picture = root / "examples/needle_profile_controls.png"
    if not overwrite and (scene.exists() or picture.exists()):
        raise FileExistsError("Pass overwrite=True to replace generated profile examples.")
    active = c4d.documents.GetActiveDocument()
    helpers = support(root)
    engine = helpers["load_engine"](root)
    names, curves = variants(engine)
    document = c4d.documents.BaseDocument()
    outputs, configs = [], []
    for index, (name, curve) in enumerate(zip(names, curves)):
        config = helpers["configuration"](engine)
        config.update(style=engine.RUNNING, count=1, radius=.25,
                      arch=(1.1,.08,0,1.1,1.1,1.1)[index], stitch_length=8,
                      surface_offset=-.3 if index == 3 else 0.0,
                      needle_shape=curve, detail=24)
        owner = c4d.BaseObject(c4d.Onull)
        owner.SetName(name)
        document.InsertObject(owner)
        path = c4d.SplineObject(2, c4d.SPLINETYPE_LINEAR)
        path.SetAllPoints([c4d.Vector(0), c4d.Vector(0, 0, 12)])
        path.Message(c4d.MSG_UPDATE); path.InsertUnder(owner)
        output = engine.build(owner, path, config)
        output.InsertUnder(owner); path.Remove()
        reference = c4d.BaseObject(c4d.Osweep)
        reference.SetName("Original native Bezier reference / orange")
        original_reference(config).InsertUnder(reference)
        circle = c4d.BaseObject(c4d.Osplinecircle)
        circle[c4d.PRIM_CIRCLE_RADIUS] = config["radius"]
        circle.InsertUnder(reference)
        reference.SetPhong(True, True, c4d.utils.DegToRad(50))
        reference[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        reference[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(1, .48, .15)
        reference.InsertUnder(owner)
        reference.SetRelPos(c4d.Vector(1.1, 0, 0))
        ground = c4d.PolygonObject(4, 1)
        ground.SetAllPoints([c4d.Vector(-2, 0, 0), c4d.Vector(-2, 0, 12),
                             c4d.Vector(2, 0, 12), c4d.Vector(2, 0, 0)])
        ground.SetPolygon(0, c4d.CPolygon(0, 1, 2, 3))
        ground.SetName("Skin plane / Y=0")
        ground.Message(c4d.MSG_UPDATE); ground.InsertUnder(owner)
        ground[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        ground[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(.07, .08, .1)
        owner.SetRelPos(c4d.Vector((index % 3)*8, 0, (index//3)*18))
        outputs.append(output); configs.append(config)
    document.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    draw(engine, outputs, configs, names, picture)
    camera = c4d.BaseObject(c4d.Ocamera)
    position = c4d.Vector(32, 18, -33)
    forward = (c4d.Vector(8, 0, 15)-position).GetNormalized()
    right = forward.Cross(c4d.Vector(0, 1, 0)).GetNormalized()
    up = right.Cross(forward).GetNormalized()
    camera.SetMg(c4d.Matrix(position, right, up, -forward))
    camera.SetName("Needle profile inspection camera")
    document.InsertObject(camera)
    if hasattr(document, "ForceCreateBaseDraw"):
        document.ForceCreateBaseDraw()
    draw_view = document.GetActiveBaseDraw()
    if draw_view is not None:
        draw_view.SetSceneCamera(camera)
    if not c4d.documents.SaveDocument(document, str(scene),
                                     c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
                                     c4d.FORMAT_C4DEXPORT):
        raise RuntimeError("Could not save profile controls scene.")
    if c4d.documents.GetActiveDocument() != active:
        raise RuntimeError("Active scene changed.")
    print("Saved:", scene)
    print("Saved:", picture)


if __name__ == "__main__":
    run()
