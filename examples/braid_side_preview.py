"""Native Sweep-mesh and side-profile checks for independent braid needles."""
import math
from pathlib import Path

import c4d


def strand(path,index=0):
    start=sum(path.GetSegment(i)["cnt"] for i in range(index))
    return path.GetAllPoints()[start:start+path.GetSegment(index)["cnt"]]


def paths(output):
    return [child for sweep in output.GetChildren() for child in sweep.GetChildren()
            if isinstance(child,c4d.SplineObject)]


def polygons(node,matrix):
    cache=node.GetCache()
    if cache is not None:
        part=cache
        while part:
            yield from polygons(part,matrix*part.GetMl())
            part=part.GetNext()
    elif isinstance(node,c4d.PolygonObject):
        points=[matrix*p for p in node.GetAllPoints()]
        for face in node.GetAllPolygons():
            yield [points[i] for i in (face.a,face.b,face.c)]
            if face.c!=face.d:
                yield [points[i] for i in (face.a,face.c,face.d)]
    else:
        for child in node.GetChildren():
            yield from polygons(child,matrix*child.GetMl())


def above_skin(points):
    """Clip native polygons at the skin plane; submerged tips stay occluded."""
    clipped=[]
    previous=points[-1]
    for current in points:
        before,after=previous.y>=0,current.y>=0
        if before!=after:
            t=-previous.y/(current.y-previous.y)
            clipped.append(previous+(current-previous)*t)
        if after:
            clipped.append(current)
        previous=current
    return clipped


def preview(outputs,configs,filename):
    clip=c4d.bitmaps.GeClipMap()
    clip.Init(1500,1000,32)
    clip.BeginDraw()
    clip.SetColor(17,22,30);clip.FillRect(0,0,1499,999)
    font=c4d.bitmaps.GeClipMap.GetDefaultFont(c4d.GE_FONT_DEFAULT_SYSTEM)
    clip.SetFont(font,30);clip.SetColor(239,243,250)
    clip.TextAt(30,26,"INDEPENDENT BRAID NEEDLES  |  actual Sweep mesh")
    clip.SetFont(font,17);clip.SetColor(156,172,193)
    clip.TextAt(32,72,"One complete profile per needle. Arch height scales the entire curve, including both ends.")
    camera=c4d.Vector(17,11,-18)
    forward=(c4d.Vector(0,0,18)-camera).GetNormalized()
    right=forward.Cross(c4d.Vector(0,1,0)).GetNormalized()
    up=right.Cross(forward).GetNormalized()
    light=c4d.Vector(-.4,.9,-.3).GetNormalized()
    for panel,(output,config) in enumerate(zip(outputs,configs)):
        left=30+490*panel
        clip.SetColor(28,35,46);clip.FillRect(left,115,left+459,964)
        clip.SetFont(font,23);clip.SetColor(230,238,250)
        clip.TextAt(left+18,131,"Arch height: "+str(config["arch"]))
        clip.SetFont(font,15);clip.SetColor(142,160,183)
        clip.TextAt(left+18,171,"Oblique mesh view / skin hides submerged ends")
        triangles=[]
        for group,sweep in enumerate(output.GetChildren()):
            color=config["color_"+"abc"[group]]
            rgb=[max(0,min(1,v))**(1/2.2)*255 for v in (color.x,color.y,color.z)]
            for triangle in polygons(sweep,sweep.GetMl()):
                clipped=above_skin(triangle)
                if len(clipped)<3:
                    continue
                normal=(triangle[1]-triangle[0]).Cross(triangle[2]-triangle[0]).GetNormalized()
                shade=.35+.65*abs(normal.Dot(light))
                screen=[(p.Dot(right),p.Dot(up)) for p in clipped]
                triangles.append((sum(p.Dot(forward) for p in clipped)/len(clipped),
                                  screen,tuple(round(v*shade) for v in rgb)))
        all_points=[p for unused,triangle,color in triangles for p in triangle]
        xmin,xmax=min(p[0] for p in all_points),max(p[0] for p in all_points)
        ymin,ymax=min(p[1] for p in all_points),max(p[1] for p in all_points)
        scale=min(406/(xmax-xmin),326/(ymax-ymin))
        clip.SetColor(48,53,61);clip.FillRect(left+18,208,left+441,575)
        for unused,triangle,color in sorted(triangles,reverse=True,key=lambda t:t[0]):
            projected=[(round(left+230+(x-(xmin+xmax)/2)*scale),
                        round(392-(y-(ymin+ymax)/2)*scale)) for x,y in triangle]
            clip.SetColor(*color)
            clip.FillPolygon([c4d.Vector(x,y,0) for x,y in projected])

        clip.SetFont(font,18);clip.SetColor(230,238,250)
        clip.TextAt(left+18,607,"One needle / exact generated side profile")
        needle=strand(paths(output)[0])
        a,b=needle[0],needle[-1]
        chord=c4d.Vector(b.x-a.x,0,b.z-a.z)
        direction=chord.GetNormalized()
        scale=100
        x0=left+(460-chord.GetLength()*scale)/2
        baseline=842
        clip.SetColor(48,53,61);clip.FillRect(left+18,baseline,left+441,931)
        clip.SetColor(153,168,187);clip.Line(left+18,baseline,left+441,baseline)
        clip.SetFont(font,14);clip.TextAt(left+23,baseline+8,"skin plane")
        color=config["color_a"]
        rgb=tuple(round(v**(1/2.2)*255) for v in (color.x,color.y,color.z))
        for p,q in zip(needle,needle[1:]):
            p2=(round(x0+(p-a).Dot(direction)*scale),round(baseline-p.y*scale))
            q2=(round(x0+(q-a).Dot(direction)*scale),round(baseline-q.y*scale))
            clip.SetColor(*(rgb if max(p.y,q.y)>=0 else (111,129,151)))
            for offset in range(-2,3):
                clip.Line(p2[0],p2[1]+offset,q2[0],q2[1]+offset)
        clip.SetFont(font,14);clip.SetColor(153,169,190)
        clip.TextAt(left+18,940,"Entire profile is editable; no appended entry segments")
    clip.EndDraw()
    if clip.GetBitmap().Save(str(filename),c4d.FILTER_PNG,None,0)!=c4d.IMAGERESULT_OK:
        raise RuntimeError("Could not save the side preview.")


def run(root=None,overwrite=False):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    support_path=root/"examples/build_examples.py"
    support={"__name__":"example_support","__file__":str(support_path)}
    exec(compile(support_path.read_text(),str(support_path),"exec"),support)
    engine=support["load_engine"](root)
    picture=root/"examples/braid_side_preview.png"
    scene=root/"examples/Braid_Independent_Arcs.c4d"
    if not overwrite and (picture.exists() or scene.exists()):
        raise FileExistsError("Pass overwrite=True to replace generated side examples.")
    active=c4d.documents.GetActiveDocument()
    document=c4d.documents.BaseDocument()
    outputs,configs=[],[]
    for index,height in enumerate((0.0,0.6,1.2)):
        config=support["configuration"](engine)
        config.update(style=engine.BRAID,count=6,radius=.25,seam_width=6,
                      arch=height,surface_offset=0.0,detail=16,profile_steps=4)
        owner=c4d.BaseObject(c4d.Onull)
        owner.SetName("Arch "+str(height)+" / independent needles")
        document.InsertObject(owner)
        guide=c4d.SplineObject(2,c4d.SPLINETYPE_LINEAR)
        guide.SetAllPoints([c4d.Vector(0),c4d.Vector(0,0,36)])
        guide.Message(c4d.MSG_UPDATE);guide.InsertUnder(owner)
        output=engine.build(owner,guide,config)
        output.InsertUnder(owner)
        guide.Remove()
        ground=c4d.PolygonObject(4,1)
        ground.SetAllPoints([c4d.Vector(-7,0,-3),c4d.Vector(-7,0,39),
                             c4d.Vector(7,0,39),c4d.Vector(7,0,-3)])
        ground.SetPolygon(0,c4d.CPolygon(0,1,2,3))
        ground.Message(c4d.MSG_UPDATE);ground.InsertUnder(owner)
        ground.SetName("Skin plane / Y=0")
        ground[c4d.ID_BASEOBJECT_USECOLOR]=c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        ground[c4d.ID_BASEOBJECT_COLOR]=c4d.Vector(.07,.08,.10)
        owner.SetRelPos(c4d.Vector(index*16,0,0))
        outputs.append(output);configs.append(config)
    document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    preview(outputs,configs,picture)
    camera=c4d.BaseObject(c4d.Ocamera)
    target=c4d.Vector(16,0,18)
    forward=(target-c4d.Vector(50,28,-60)).GetNormalized()
    right=forward.Cross(c4d.Vector(0,1,0)).GetNormalized()
    up=right.Cross(forward).GetNormalized()
    camera.SetMg(c4d.Matrix(c4d.Vector(50,28,-60),right,up,-forward))
    camera.SetName("Side inspection camera")
    document.InsertObject(camera)
    if hasattr(document,"ForceCreateBaseDraw"):
        document.ForceCreateBaseDraw()
    draw=document.GetActiveBaseDraw()
    if draw is not None:
        draw.SetSceneCamera(camera)
    if not c4d.documents.SaveDocument(document,str(scene),
                                     c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,c4d.FORMAT_C4DEXPORT):
        raise RuntimeError("Could not save the side inspection scene.")
    if c4d.documents.GetActiveDocument()!=active:
        raise RuntimeError("Active document changed.")
    print("Saved:",scene)
    print("Saved:",picture)


if __name__=="__main__":
    run()
