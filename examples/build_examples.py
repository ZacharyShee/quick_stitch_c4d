"""Build a native C4D geometry gallery and a top-view curve atlas.

Run in Cinema 4D's Script Manager. This uses a detached document and leaves the
active scene alone. Existing output files require run(overwrite=True).
"""
import importlib.util
import math
from pathlib import Path

import c4d


def load_engine(root):
    path = root / "quick_stitch_patterns.py"
    spec = importlib.util.spec_from_file_location("quick_stitch_examples_engine", path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


def configuration(engine):
    result = {}
    for name, (unused_id, unused_type, default) in engine.PARAMETERS.items():
        result[name] = c4d.Vector(*default) if isinstance(default, tuple) else default
    result.update(count=8, radius=0.3, rotation=c4d.Matrix(), distribution=0,
                  seam_width=12.0, stitch_length=8.0, arch=0.8, surface_offset=-0.35, detail=12)
    return result


def thread_segments(output,clip_skin=False):
    for group, sweep in enumerate(output.GetChildren()):
        for child in sweep.GetChildren():
            if not isinstance(child, c4d.SplineObject):
                continue
            points, start = child.GetAllPoints(), 0
            for i in range(child.GetSegmentCount()):
                segment = child.GetSegment(i)
                strand = points[start:start+segment["cnt"]]
                for a,b in zip(strand, strand[1:]):
                    if clip_skin:
                        if a.y<0 and b.y<0:
                            continue
                        if (a.y<0)!=(b.y<0):
                            intersection=a+(b-a)*(-a.y/(b.y-a.y))
                            if a.y<0:
                                a=intersection
                            else:
                                b=intersection
                    yield group,a,b
                if segment["closed"]:
                    yield group,strand[-1],strand[0]
                start += segment["cnt"]


def atlas(gallery, config, filename):
    clip = c4d.bitmaps.GeClipMap()
    clip.Init(1600, 1280, 32)
    clip.BeginDraw()
    clip.SetColor(15,19,26)
    clip.FillRect(0,0,1599,1279)
    font = c4d.bitmaps.GeClipMap.GetDefaultFont(c4d.GE_FONT_DEFAULT_SYSTEM)
    clip.SetFont(font,34)
    clip.SetColor(239,244,250)
    clip.TextAt(40,30,"QUICK STITCH  |  8 parametric patterns")
    clip.SetFont(font,18)
    clip.SetColor(151,167,187)
    clip.TextAt(42,86,"Actual generated paths / top view / independent A, B, C thread groups")

    def thick_line(a,b,color,radius):
        clip.SetColor(*color)
        for dx in range(-radius,radius+1):
            for dy in range(-radius,radius+1):
                if dx*dx+dy*dy <= radius*radius:
                    clip.Line(a[0]+dx,a[1]+dy,b[0]+dx,b[1]+dy)

    colors=[]
    for letter in "abc":
        vector=config["color_"+letter]
        colors.append(tuple(int(max(0,min(1,x))**(1/2.2)*255)
                            for x in (vector.x,vector.y,vector.z)))
    labels=("Running","Double Running","Slanted","Zigzag",
            "V / Chevron","X / Cross","Diamond","Steering Wheel Braid")
    for index, output in enumerate(gallery):
        x,y=40+(index%4)*380,144+(index//4)*550
        clip.SetColor(27,33,44)
        clip.FillRect(x,y,x+359,y+509)
        clip.SetFont(font,22)
        clip.SetColor(230,237,246)
        clip.TextAt(x+18,y+18,str(index+1).zfill(2)+"  "+labels[index])
        center=x+180
        clip.SetColor(42,46,53)
        clip.FillRect(center-104,y+72,center+104,y+443)
        clip.SetColor(20,23,29)
        clip.FillRect(center-2,y+72,center+2,y+443)
        plot_y=y+83
        segments=sorted(thread_segments(output,clip_skin=True),
                        key=lambda item:(item[1].y+item[2].y)/2)
        for group,a,b in segments:
            p=(round(center+a.x*4.4),round(plot_y+a.z*4.4))
            q=(round(center+b.x*4.4),round(plot_y+b.z*4.4))
            thick_line(p,q,(10,13,19),3)
        for group,a,b in segments:
            p=(round(center+a.x*4.4),round(plot_y+a.z*4.4))
            q=(round(center+b.x*4.4),round(plot_y+b.z*4.4))
            thick_line(p,q,colors[group],2)
        clip.SetFont(font,16)
        clip.SetColor(145,161,181)
        text="A / B / C materials" if index==7 else "Adjust pitch, width, radius and arch"
        clip.TextAt(x+18,y+470,text)
    clip.EndDraw()
    if clip.GetBitmap().Save(str(filename),c4d.FILTER_PNG, None,0)!=c4d.IMAGERESULT_OK:
        raise RuntimeError("Could not save the pattern atlas.")


def run(root=None, overwrite=False):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    destination=root/"examples"
    destination.mkdir(exist_ok=True)
    scene_file=destination/"Quick_Stitch_Styles.c4d"
    image_file=destination/"stitch_styles.png"
    if not overwrite and (scene_file.exists() or image_file.exists()):
        raise FileExistsError("Generated examples exist; pass overwrite=True to replace them.")
    active=c4d.documents.GetActiveDocument()
    engine=load_engine(root)
    config=configuration(engine)
    document=c4d.documents.BaseDocument()
    owner=c4d.BaseObject(c4d.Onull)
    document.InsertObject(owner)
    line=c4d.SplineObject(2,c4d.SPLINETYPE_LINEAR)
    line.SetAllPoints([c4d.Vector(0),c4d.Vector(0,0,80)])
    line.Message(c4d.MSG_UPDATE)
    line.InsertUnder(owner)
    gallery=[]
    for style in range(1,9):
        config["style"]=style
        result=engine.build(owner,line,config)
        gallery.append(result)
    atlas(gallery,config,image_file)
    for i,result in enumerate(gallery):
        document.InsertObject(result)
        result.SetRelPos(c4d.Vector((i%4)*35,0,(i//4)*110))
        result.SetName(str(i+1).zfill(2)+" "+engine.STYLE_NAMES[i+1])
    owner.Remove()

    # A native mesh and closed braid demonstrate continuous surface fitting.
    owner=c4d.BaseObject(c4d.Onull)
    owner.SetName("09 Closed Cylinder / Surface Fit")
    document.InsertObject(owner)
    count,radius=96,30
    mesh=c4d.PolygonObject(count*2,count)
    mesh.SetAllPoints([c4d.Vector(radius*math.cos(i*2*math.pi/count),y,
                                  radius*math.sin(i*2*math.pi/count))
                       for i in range(count) for y in (-15,15)])
    for i in range(count):
        a,b=2*i,2*((i+1)%count)
        mesh.SetPolygon(i,c4d.CPolygon(a,a+1,b+1,b))
    mesh.Message(c4d.MSG_UPDATE)
    mesh.SetName("Surface mesh")
    mesh.InsertUnder(owner)
    mesh[c4d.ID_BASEOBJECT_USECOLOR]=c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
    mesh[c4d.ID_BASEOBJECT_COLOR]=c4d.Vector(.07,.08,.1)
    circle=c4d.SplineObject(count,c4d.SPLINETYPE_LINEAR)
    circle.SetAllPoints([c4d.Vector(radius*math.cos(i*2*math.pi/count),0,
                                    radius*math.sin(i*2*math.pi/count))
                         for i in range(count)])
    circle[c4d.SPLINEOBJECT_CLOSED]=True
    circle.Message(c4d.MSG_UPDATE)
    circle.InsertUnder(owner)
    config.update(style=engine.BRAID,count=24,seam_width=10,conform=True,detail=8)
    result=engine.build(owner,circle,config,mesh)
    result.InsertUnder(owner)
    circle.Remove()
    owner.SetRelPos(c4d.Vector(190,0,45))

    wheel=c4d.BaseObject(c4d.Onull)
    wheel.SetName("10 Steering Wheel / Torus Surface Fit")
    document.InsertObject(wheel)
    n,m=72,24
    torus=c4d.PolygonObject(n*m,n*m)
    torus.SetAllPoints([
        c4d.Vector((60+12*math.cos(j*2*math.pi/m))*math.cos(i*2*math.pi/n),
                   12*math.sin(j*2*math.pi/m),
                   (60+12*math.cos(j*2*math.pi/m))*math.sin(i*2*math.pi/n))
        for i in range(n) for j in range(m)])
    for i in range(n):
        for j in range(m):
            torus.SetPolygon(i*m+j,c4d.CPolygon(
                i*m+j,i*m+(j+1)%m,((i+1)%n)*m+(j+1)%m,((i+1)%n)*m+j))
    torus.SetName("Steering wheel surface")
    torus.Message(c4d.MSG_UPDATE)
    torus.InsertUnder(wheel)
    torus[c4d.ID_BASEOBJECT_USECOLOR]=c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
    torus[c4d.ID_BASEOBJECT_COLOR]=c4d.Vector(.07,.08,.1)
    guide=c4d.SplineObject(96,c4d.SPLINETYPE_LINEAR)
    guide.SetAllPoints([c4d.Vector(48*math.cos(i*2*math.pi/96),0,
                                   48*math.sin(i*2*math.pi/96)) for i in range(96)])
    guide[c4d.SPLINEOBJECT_CLOSED]=True
    guide.Message(c4d.MSG_UPDATE)
    guide.InsertUnder(wheel)
    config.update(count=36,seam_width=10)
    engine.build(wheel,guide,config,torus).InsertUnder(wheel)
    guide.Remove()
    wheel.SetRelPos(c4d.Vector(310,0,85))

    document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    if not c4d.documents.SaveDocument(document,str(scene_file),
                                     c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
                                     c4d.FORMAT_C4DEXPORT):
        raise RuntimeError("Could not save native geometry examples.")
    if c4d.documents.GetActiveDocument()!=active:
        raise RuntimeError("The active document changed.")
    print("Saved:",scene_file)
    print("Saved:",image_file)
    return str(scene_file),str(image_file)


if __name__=="__main__":
    run()
