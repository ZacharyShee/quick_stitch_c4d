"""Inspect actual native Sweep geometry for every independent stitch style."""
import math
from pathlib import Path

import c4d


def load_support(root,name):
    path=root/"examples"/name
    scope={"__name__":"preview_support","__file__":str(path)}
    exec(compile(path.read_text(),str(path),"exec"),scope)
    return scope


def strands(output):
    for group in output.GetChildren():
        for path in group.GetChildren():
            if not isinstance(path,c4d.SplineObject):
                continue
            points,start=path.GetAllPoints(),0
            for i in range(path.GetSegmentCount()):
                segment=path.GetSegment(i)
                if segment["closed"]:
                    raise RuntimeError("An example contains a connected closed needle.")
                yield points[start:start+segment["cnt"]]
                start+=segment["cnt"]


def atlas(outputs,configs,mesh_support,filename):
    forward=(c4d.Vector(0,0,18)-c4d.Vector(17,11,-18)).GetNormalized()
    right=forward.Cross(c4d.Vector(0,1,0)).GetNormalized()
    up=right.Cross(forward).GetNormalized()
    light=c4d.Vector(-.4,.9,-.3).GetNormalized()
    scenes=[]
    for output,config in zip(outputs,configs):
        triangles=[]
        for group,sweep in enumerate(output.GetChildren()):
            color=config["color_"+"abc"[group]]
            rgb=[max(0,min(1,v))**(1/2.2)*255 for v in (color.x,color.y,color.z)]
            for polygon in mesh_support["polygons"](sweep,sweep.GetMl()):
                clipped=mesh_support["above_skin"](polygon)
                if len(clipped)<3:
                    continue
                normal=(polygon[1]-polygon[0]).Cross(polygon[2]-polygon[0]).GetNormalized()
                shade=.35+.65*abs(normal.Dot(light))
                triangles.append((sum(p.Dot(forward) for p in clipped)/len(clipped),
                                  [(p.Dot(right),p.Dot(up)) for p in clipped],
                                  tuple(round(v*shade) for v in rgb)))
        scenes.append(triangles)
    coordinates=[p for scene in scenes for unused,triangle,color in scene for p in triangle]
    xmin,xmax=min(p[0] for p in coordinates),max(p[0] for p in coordinates)
    ymin,ymax=min(p[1] for p in coordinates),max(p[1] for p in coordinates)
    scale=min(315/(xmax-xmin),230/(ymax-ymin))
    clip=c4d.bitmaps.GeClipMap()
    clip.Init(1600,1200,32)
    clip.BeginDraw()
    clip.SetColor(17,22,30);clip.FillRect(0,0,1599,1199)
    font=c4d.bitmaps.GeClipMap.GetDefaultFont(c4d.GE_FONT_DEFAULT_SYSTEM)
    clip.SetFont(font,32);clip.SetColor(238,244,251)
    clip.TextAt(35,27,"ALL 8 STYLES  |  independent needle arcs")
    clip.SetFont(font,18);clip.SetColor(150,168,190)
    clip.TextAt(37,81,"Native Sweep mesh + complete editable profiles. Negative Profile Offset sinks the ends naturally.")
    labels=("Running","Double Running","Slanted","Zigzag","V / Chevron","X / Cross","Diamond","Steering Wheel Braid")
    for index,(output,config,scene) in enumerate(zip(outputs,configs,scenes)):
        left,top=35+(index%4)*385,137+(index//4)*505
        clip.SetColor(28,35,46);clip.FillRect(left,top,left+359,top+474)
        clip.SetFont(font,22);clip.SetColor(234,240,249)
        clip.TextAt(left+16,top+15,str(index+1).zfill(2)+"  "+labels[index])
        needles=list(strands(output))
        clip.SetFont(font,15);clip.SetColor(151,169,191)
        clip.TextAt(left+16,top+49,str(len(needles))+" independent open pieces")
        clip.SetColor(47,53,62);clip.FillRect(left+15,top+81,left+344,top+319)
        for depth,triangle,color in sorted(scene,reverse=True,key=lambda t:t[0]):
            projected=[c4d.Vector(round(left+180+(x-(xmin+xmax)/2)*scale),
                                  round(top+200-(y-(ymin+ymax)/2)*scale),0)
                       for x,y in triangle]
            clip.SetColor(*color);clip.FillPolygon(projected)
        clip.SetFont(font,15);clip.SetColor(215,227,242)
        clip.TextAt(left+16,top+335,"Single needle / side profile")
        needle=needles[0]
        a,b=needle[0],needle[-1]
        direction=c4d.Vector(b.x-a.x,0,b.z-a.z)
        width=direction.GetLength()
        direction=direction.GetNormalized()
        x0=left+(360-width*35)/2
        baseline=top+427
        clip.SetColor(47,53,62);clip.FillRect(left+15,baseline,left+344,top+451)
        clip.SetColor(118,137,160);clip.Line(left+15,baseline,left+344,baseline)
        for p,q in zip(needle,needle[1:]):
            clip.SetColor(*(109,203,255) if max(p.y,q.y)>=0 else (117,136,160))
            px,py=round(x0+(p-a).Dot(direction)*35),round(baseline-p.y*35)
            qx,qy=round(x0+(q-a).Dot(direction)*35),round(baseline-q.y*35)
            for offset in (-1,0,1):
                clip.Line(px,py+offset,qx,qy+offset)
        clip.SetFont(font,13);clip.SetColor(145,164,188)
        clip.TextAt(left+17,top+454,"One complete curve / signed Profile Offset")
    clip.EndDraw()
    if clip.GetBitmap().Save(str(filename),c4d.FILTER_PNG,None,0)!=c4d.IMAGERESULT_OK:
        raise RuntimeError("Could not save all-style preview.")


def run(root=None,overwrite=False):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    scene=root/"examples/All_Styles_Independent_Arcs.c4d"
    image=root/"examples/all_styles_side_preview.png"
    if not overwrite and (scene.exists() or image.exists()):
        raise FileExistsError("Pass overwrite=True to replace generated examples.")
    active=c4d.documents.GetActiveDocument()
    support=load_support(root,"build_examples.py")
    mesh_support=load_support(root,"braid_side_preview.py")
    engine=support["load_engine"](root)
    document=c4d.documents.BaseDocument()
    outputs,configs=[],[]
    for style in range(1,9):
        config=support["configuration"](engine)
        config.update(style=style,count=6,radius=.25,seam_width=6,stitch_length=3.8,
                      arch=.6,surface_offset=-.3,detail=16,profile_steps=4)
        owner=c4d.BaseObject(c4d.Onull)
        owner.SetName(str(style).zfill(2)+" "+engine.STYLE_NAMES[style]+" / independent")
        document.InsertObject(owner)
        guide=c4d.SplineObject(2,c4d.SPLINETYPE_LINEAR)
        guide.SetAllPoints([c4d.Vector(0),c4d.Vector(0,0,36)])
        guide.Message(c4d.MSG_UPDATE);guide.InsertUnder(owner)
        output=engine.build(owner,guide,config)
        output.InsertUnder(owner);guide.Remove()
        ground=c4d.PolygonObject(4,1)
        ground.SetAllPoints([c4d.Vector(-7,0,-3),c4d.Vector(-7,0,39),
                             c4d.Vector(7,0,39),c4d.Vector(7,0,-3)])
        ground.SetPolygon(0,c4d.CPolygon(0,1,2,3))
        ground.Message(c4d.MSG_UPDATE);ground.InsertUnder(owner)
        ground.SetName("Skin plane / Y=0")
        ground[c4d.ID_BASEOBJECT_USECOLOR]=c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        ground[c4d.ID_BASEOBJECT_COLOR]=c4d.Vector(.07,.08,.1)
        owner.SetRelPos(c4d.Vector(((style-1)%4)*17,0,((style-1)//4)*52))
        outputs.append(output);configs.append(config)
    document.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    atlas(outputs,configs,mesh_support,image)
    camera=c4d.BaseObject(c4d.Ocamera)
    forward=(c4d.Vector(25,0,42)-c4d.Vector(92,55,-90)).GetNormalized()
    right=forward.Cross(c4d.Vector(0,1,0)).GetNormalized()
    up=right.Cross(forward).GetNormalized()
    camera.SetMg(c4d.Matrix(c4d.Vector(92,55,-90),right,up,-forward))
    camera.SetName("All-style side inspection camera")
    document.InsertObject(camera)
    if hasattr(document,"ForceCreateBaseDraw"):
        document.ForceCreateBaseDraw()
    draw=document.GetActiveBaseDraw()
    if draw is not None:
        draw.SetSceneCamera(camera)
    if not c4d.documents.SaveDocument(document,str(scene),
                                     c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
                                     c4d.FORMAT_C4DEXPORT):
        raise RuntimeError("Could not save all-style scene.")
    if c4d.documents.GetActiveDocument()!=active:
        raise RuntimeError("Active scene changed.")
    print("Saved:",scene)
    print("Saved:",image)


if __name__=="__main__":
    run()
