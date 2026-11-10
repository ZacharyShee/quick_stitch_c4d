"""Parametric stitch paths and surface projection for Quick Stitch Pro.

No scene changes are made here: all output belongs to a returned cache hierarchy.
Coordinates, pitch and thread radius are expressed in the generator's local space.
"""
import math
import re

import c4d

PLUGIN_ID = 1054816
PLUGIN_NAME = "Quick Stitch Pro"
PLUGIN_VERSION = "V1.0"
PLUGIN_AUTHOR = "Zachary Shee"

LEGACY, RUNNING, DOUBLE, SLANT, ZIGZAG, CHEVRON, CROSS, DIAMOND, BRAID = range(9)
STYLE_NAMES = (
    "Original / Custom", "Running", "Double Running", "Slanted",
    "Zigzag", "V / Chevron", "X / Cross", "Diamond", "Steering Wheel Braid",
)
LANG_AUTO, LANG_EN, LANG_ZH = 0, 1, 2
MAX_STITCHES = 4096
MAX_POINTS = 300000
EPSILON = 1.0e-8
PERCENT_RANGES = {1107: (0.0, 1.0), 1125: (0.05, 0.95)}
CUSTOM_PROFILE = 4

# ID, Python type, default. Existing IDs 1000-1011 retain their meanings.
PARAMETERS = {
    "style": (1100, int, LEGACY),
    "distribution": (1101, int, 1),
    "pitch": (1102, float, 6.0),
    "seam_width": (1103, float, 6.0),
    "stitch_length": (1104, float, 3.8),
    "arch": (1105, float, 0.4),
    "cross_clearance": (1106, float, 0.15),
    "phase": (1107, float, 0.0),
    "mirror": (1108, bool, False),
    "surface": (1109, c4d.BaseList2D, None),
    "conform": (1110, bool, False),
    "surface_offset": (1111, float, 0.0),
    "ray_distance": (1112, float, 20.0),
    "up_axis": (1113, int, 0),
    "material_a": (1115, c4d.BaseList2D, None),
    "material_b": (1116, c4d.BaseList2D, None),
    "material_c": (1117, c4d.BaseList2D, None),
    "color_a": (1118, c4d.Vector, (0.15, 0.6, 1.0)),
    "color_b": (1119, c4d.Vector, (0.85, 0.035, 0.02)),
    "color_c": (1120, c4d.Vector, (0.025, 0.08, 0.22)),
    "detail": (1121, int, 8),
    "profile_steps": (1122, int, 1),
    # IDs 1123, 1124 and 1129 are retired; old stored values are not evaluated.
    "lean": (1125, float, 0.5),
    "flip_normal": (1126, bool, False),
    "reverse": (1127, bool, False),
    "needle_shape": (1128, c4d.SplineData, None),
    "shape_preset": (1130, int, 0),
    "language": (1132, int, LANG_AUTO),
}

UI_LABELS = {
    "en": {
        1000: "Object",
        1001: "Step",
        1002: "Count",
        1003: "Width",
        1004: "Height",
        1005: "Thickness",
        1006: "Offset",
        1007: "Shape",
        1008: "Make Stitch",
        1009: "R.H",
        1010: "R.B",
        1011: "R.P",
        1100: "Stitch Style",
        1101: "Distribution",
        1102: "Pitch",
        1103: "Seam Width",
        1104: "Stitch Length",
        1105: "Needle Arch Height",
        1106: "Crossing Clearance",
        1107: "Start Offset",
        1108: "Mirror Pattern",
        1109: "Surface",
        1110: "Surface Fit",
        1111: "Profile Offset",
        1112: "Projection Distance",
        1113: "Reference Up Axis",
        1115: "Material A / Left",
        1116: "Material B / Right",
        1117: "Material C / Lacing",
        1118: "Preview Color A",
        1119: "Preview Color B",
        1120: "Preview Color C",
        1121: "Curve Detail",
        1122: "Thread Profile Detail",
        1125: "Slant / Stagger",
        1126: "Flip Surface Normal",
        1127: "Reverse Direction",
        1128: "Needle Profile",
        1130: "Profile Preset",
        1132: "Language",
        1133: "Plugin: Quick Stitch Pro",
        1134: "Version: V1.0",
        1135: "Author: Zachary Shee",
        1136: "Based on Quick Stitch by Nishiki (MIT License)",
        2000: "Style and Layout",
        2001: "Original Shape",
        2002: "Pattern Dimensions",
        2003: "Surface and Orientation",
        2004: "Thread Materials",
        2005: "Quality",
        2006: "Needle Shape",
        2007: "About",
    },
    "zh": {
        1000: "目标对象",
        1001: "步幅",
        1002: "数量",
        1003: "宽度",
        1004: "高度",
        1005: "线径 (半径)",
        1006: "偏移",
        1007: "形状",
        1008: "生成缝线",
        1009: "R.H",
        1010: "R.B",
        1011: "R.P",
        1100: "缝线样式",
        1101: "分布方式",
        1102: "针距",
        1103: "缝宽",
        1104: "针长",
        1105: "针拱高度",
        1106: "交叉间距",
        1107: "起始偏移",
        1108: "左右镜像",
        1109: "贴合表面",
        1110: "表面贴合",
        1111: "轮廓偏移",
        1112: "投射距离",
        1113: "参考上轴",
        1115: "材质 A / 左线",
        1116: "材质 B / 右线",
        1117: "材质 C / 中间穿线",
        1118: "预览颜色 A",
        1119: "预览颜色 B",
        1120: "预览颜色 C",
        1121: "曲线精度",
        1122: "截面精度",
        1125: "倾斜 / 错位",
        1126: "翻转表面法线",
        1127: "反向布局",
        1128: "单针轮廓曲线",
        1130: "轮廓预设",
        1132: "界面语言",
        1133: "插件名称: Quick Stitch Pro",
        1134: "版本: V1.0",
        1135: "作者: Zachary Shee",
        1136: "原版基础: Nishiki (MIT License)",
        2000: "样式与布局",
        2001: "原版形状",
        2002: "图案尺寸",
        2003: "曲面与方向",
        2004: "缝线材质",
        2005: "网格质量",
        2006: "针脚形状",
        2007: "关于",
    },
}

UI_CYCLES = {
    "en": {
        1100: {
            0: "Original / Custom",
            1: "Running Stitch",
            2: "Double Running Stitch",
            3: "Slanted Stitch",
            4: "Zigzag Stitch",
            5: "V / Chevron",
            6: "X / Cross Stitch",
            7: "Diamond Lacing",
            8: "Steering Wheel Braid",
        },
        1101: {0: "By Count", 1: "By Pitch"},
        1113: {0: "+Y", 1: "+Z", 2: "+X", 3: "-Y", 4: "-Z", 5: "-X"},
        1130: {
            0: "Original Shape",
            1: "Rounded Arch",
            2: "Low Arch",
            3: "Straight",
            4: "Custom",
        },
        1132: {0: "Auto (Follow C4D)", 1: "English", 2: "简体中文"},
    },
    "zh": {
        1100: {
            0: "原版 / 自定义",
            1: "单排短针",
            2: "双排平行短针",
            3: "单向斜针",
            4: "Z 字针",
            5: "V 形 / 人字针",
            6: "X 形 / 十字交叉针",
            7: "菱形针",
            8: "方向盘编织",
        },
        1101: {0: "按数量", 1: "按针距"},
        1113: {0: "+Y", 1: "+Z", 2: "+X", 3: "-Y", 4: "-Z", 5: "-X"},
        1130: {
            0: "原版默认",
            1: "圆拱",
            2: "低拱",
            3: "平直轮廓",
            4: "自定义",
        },
        1132: {0: "自动 (跟随 C4D)", 1: "English", 2: "简体中文"},
    },
}

ERROR_TRANSLATIONS = {
    "Could not allocate the stitch curve.": "无法分配缝线曲线内存。",
    "Link an editable polygon object in the Object field.": "请在“目标对象”栏中指定可编辑多边形对象。",
    "Select at least one edge on the linked object.": "请在目标对象上至少选择一条边。",
    "The Quick Stitch object must belong to a document.": "Quick Stitch 对象必须属于活动文档。",
    "Could not copy the source mesh.": "无法复制源网格模型。",
    "Could not create a spline from the selected edges.": "无法从所选边生成样条路径。",
    "Could not copy the generated path.": "无法复制生成的样条路径。",
    "Unknown stitch style.": "未知的缝线样式。",
    "Unknown needle profile preset.": "未知的轮廓预设。",
    "Could not allocate the needle profile.": "无法分配单针轮廓内存。",
    "Needle Profile must contain spline editor data.": "单针轮廓曲线必须包含样条编辑器数据。",
    "Needle Profile needs between 2 and 128 control points.": "单针轮廓曲线需要 2 到 128 个控制点。",
    "Needle Profile contains invalid coordinates.": "单针轮廓曲线包含无效坐标。",
    "Needle Profile needs a positive horizontal span.": "单针轮廓曲线需要大于零的水平跨度。",
    "Could not allocate the needle profile spline.": "无法分配单针轮廓样条内存。",
    "Needle Profile must progress from left to right without loops.": "单针轮廓曲线必须从左向右前进，不能折返。",
    "Surface Fit needs a polygon mesh in Surface or Object.": "表面贴合需要在“贴合表面”或“目标对象”中指定多边形模型。",
    "Surface must be a scene object containing a polygon mesh.": "贴合表面必须是包含多边形网格的场景对象。",
    "Surface cannot be Quick Stitch or one of its parents.": "贴合表面不能是 Quick Stitch 本身或其父级对象。",
    "Surface must contain an evaluated polygon mesh.": "贴合表面必须包含已求值的多边形网格。",
    "Could not evaluate the path spline.": "无法求值路径样条。",
    "Pitch must be greater than zero.": "针距必须大于零。",
    "Too many stitches; increase Pitch or reduce Count.": "针脚数量过多；请增大针距或减少数量。",
    "Needle Profile is too detailed; simplify its control points.": "单针轮廓曲线过于复杂；请简化控制点。",
    "A needle needs two endpoints and an optional crossing marker.": "单针需要两个端点和可选的交叉标记。",
    "Could not allocate thread paths.": "无法分配缝线路径内存。",
    "Thread material slots accept materials only.": "缝线材质槽仅接受材质。",
    "Too many stitches; reduce Count.": "针脚数量过多；请减少数量。",
    "Projection Distance must be greater than zero.": "投射距离必须大于零。",
    "Too many stitches across path segments.": "所有路径段的总针脚数量过多。",
    "Visible needle pieces must be open.": "可见针段必须是开放样条。",
    "Thread detail is too high; reduce Detail or stitch count.": "曲线精度或针脚数量过高，超出最大点数限制。",
}


def c4d_is_chinese():
    if hasattr(c4d, "GeGetLanguage"):
        index = 0
        while index < 64:
            try:
                info = c4d.GeGetLanguage(index)
            except Exception:
                break
            if not info:
                break
            if info.get("default_language", False):
                ext = str(info.get("extensions", "")).lower()
                name = str(info.get("name", "")).lower()
                return ("zh" in ext or "cn" in ext or "chinese" in name or "中文" in name)
            index += 1
    if hasattr(c4d, "GetObjectName") and hasattr(c4d, "Onull"):
        try:
            null_name = str(c4d.GetObjectName(c4d.Onull))
            return any("\u4e00" <= ch <= "\u9fff" for ch in null_name)
        except Exception:
            pass
    return False


def load_global_language():
    if hasattr(c4d, "plugins") and hasattr(c4d.plugins, "GetWorldPluginData"):
        try:
            bc = c4d.plugins.GetWorldPluginData(PLUGIN_ID)
            if bc is not None and bc[1132] in (LANG_AUTO, LANG_EN, LANG_ZH):
                return int(bc[1132])
        except Exception:
            pass
    return LANG_AUTO


def save_global_language(lang):
    if lang not in (LANG_AUTO, LANG_EN, LANG_ZH):
        return
    if hasattr(c4d, "plugins") and hasattr(c4d.plugins, "SetWorldPluginData"):
        try:
            bc = c4d.plugins.GetWorldPluginData(PLUGIN_ID)
            if bc is None:
                bc = c4d.BaseContainer()
            bc[1132] = int(lang)
            c4d.plugins.SetWorldPluginData(PLUGIN_ID, bc, add=True)
        except Exception:
            pass


def effective_language(op=None):
    mode = LANG_AUTO
    if op is not None:
        try:
            stored = op[1132]
            if stored in (LANG_AUTO, LANG_EN, LANG_ZH):
                mode = int(stored)
        except Exception:
            pass
    if mode == LANG_ZH:
        return "zh"
    if mode == LANG_EN:
        return "en"
    return "zh" if c4d_is_chinese() else "en"


def _apply_localized_parameter(parameter, field, labels, cycles):
    if parameter is None:
        return
    if field in labels:
        parameter[c4d.DESC_NAME] = labels[field]
        if hasattr(c4d, "DESC_SHORT_NAME"):
            parameter[c4d.DESC_SHORT_NAME] = labels[field]
    if field in cycles and hasattr(c4d, "DESC_CYCLE"):
        cycle = parameter.GetContainerInstance(c4d.DESC_CYCLE)
        if cycle is not None:
            for item_id, text in cycles[field].items():
                cycle.SetString(item_id, text)


def localize_description(description, lang):
    key = "zh" if lang == "zh" else "en"
    labels = dict(UI_LABELS[key])
    if hasattr(c4d, "ID_OBJECTPROPERTIES"):
        labels[c4d.ID_OBJECTPROPERTIES] = "对象" if key == "zh" else "Object"
    cycles = UI_CYCLES[key]
    visited = set()
    try:
        for unused_bc, paramid, unused_groupid in description:
            if paramid is None or paramid.GetDepth() != 1:
                continue
            field = paramid[0].id
            visited.add(field)
            _apply_localized_parameter(
                description.GetParameterI(paramid, None), field, labels, cycles)
    except TypeError:
        pass
    dtypes = {
        1000: getattr(c4d, "DTYPE_BASELISTLINK", 133),
        1002: c4d.DTYPE_LONG,
        1003: c4d.DTYPE_REAL,
        1004: c4d.DTYPE_REAL,
        1005: c4d.DTYPE_REAL,
        1006: c4d.DTYPE_REAL,
        1007: getattr(c4d, "CUSTOMDATATYPE_SPLINE", 1009290),
        1008: getattr(c4d, "DTYPE_BUTTON", 8),
        1009: c4d.DTYPE_REAL,
        1010: c4d.DTYPE_REAL,
        1011: c4d.DTYPE_REAL,
        1100: c4d.DTYPE_LONG,
        1101: c4d.DTYPE_LONG,
        1102: c4d.DTYPE_REAL,
        1103: c4d.DTYPE_REAL,
        1104: c4d.DTYPE_REAL,
        1105: c4d.DTYPE_REAL,
        1106: c4d.DTYPE_REAL,
        1107: c4d.DTYPE_REAL,
        1108: getattr(c4d, "DTYPE_BOOL", 400006001),
        1109: getattr(c4d, "DTYPE_BASELISTLINK", 133),
        1110: getattr(c4d, "DTYPE_BOOL", 400006001),
        1111: c4d.DTYPE_REAL,
        1112: c4d.DTYPE_REAL,
        1113: c4d.DTYPE_LONG,
        1115: getattr(c4d, "DTYPE_BASELISTLINK", 133),
        1116: getattr(c4d, "DTYPE_BASELISTLINK", 133),
        1117: getattr(c4d, "DTYPE_BASELISTLINK", 133),
        1118: getattr(c4d, "DTYPE_COLOR", 3),
        1119: getattr(c4d, "DTYPE_COLOR", 3),
        1120: getattr(c4d, "DTYPE_COLOR", 3),
        1121: c4d.DTYPE_LONG,
        1122: c4d.DTYPE_LONG,
        1125: c4d.DTYPE_REAL,
        1126: getattr(c4d, "DTYPE_BOOL", 400006001),
        1127: getattr(c4d, "DTYPE_BOOL", 400006001),
        1128: getattr(c4d, "CUSTOMDATATYPE_SPLINE", 1009290),
        1130: c4d.DTYPE_LONG,
        1132: c4d.DTYPE_LONG,
        1133: getattr(c4d, "DTYPE_STATICTEXT", 24),
        1134: getattr(c4d, "DTYPE_STATICTEXT", 24),
        1135: getattr(c4d, "DTYPE_STATICTEXT", 24),
        1136: getattr(c4d, "DTYPE_STATICTEXT", 24),
        2000: getattr(c4d, "DTYPE_GROUP", 1),
        2001: getattr(c4d, "DTYPE_GROUP", 1),
        2002: getattr(c4d, "DTYPE_GROUP", 1),
        2003: getattr(c4d, "DTYPE_GROUP", 1),
        2004: getattr(c4d, "DTYPE_GROUP", 1),
        2005: getattr(c4d, "DTYPE_GROUP", 1),
        2006: getattr(c4d, "DTYPE_GROUP", 1),
        2007: getattr(c4d, "DTYPE_GROUP", 1),
    }
    for field, dtype in dtypes.items():
        if field in visited:
            continue
        identifier = c4d.DescID(c4d.DescLevel(field, dtype, 0))
        _apply_localized_parameter(
            description.GetParameterI(identifier, None), field, labels, cycles)


def translate_error_text(error):
    text = str(error)
    if text in ERROR_TRANSLATIONS:
        return ERROR_TRANSLATIONS[text]
    match = re.match(
        r"^Surface projection missed (\d+) samples\. Increase Projection Distance, "
        r"choose a closer path, or disable Surface Fit\.$", text)
    if match:
        return ("表面投射有 {} 个采样点未命中。请增大投射距离、"
                "使路径更贴近表面，或关闭表面贴合。".format(match.group(1)))
    return text


def format_error(error, op=None, for_console=False):
    text = str(error)
    if effective_language(op) == "zh":
        zh_text = translate_error_text(text)
        if for_console and zh_text != text:
            return "{}: {} ({})".format(PLUGIN_NAME, zh_text, text)
        return "{}: {}".format(PLUGIN_NAME, zh_text)
    return "{}: {}".format(PLUGIN_NAME, text)


def default_shape(preset=0):
    """The original three knots and tangent handles, also used by new needles."""
    if preset not in range(4):
        raise ValueError("Unknown needle profile preset.")
    shape = c4d.SplineData()
    if not shape.MakePointBuffer(3):
        raise MemoryError("Could not allocate the needle profile.")
    height = (1.0, 1.0, 0.3, 0.0)[preset]
    shoulder = c4d.Vector(0.12, 0.45, 0) if preset == 1 else c4d.Vector(0, 0.5*height, 0)
    crown = 0.2 if preset == 1 else 0.25
    shape.SetKnot(0, c4d.Vector(0), 65536, vTangentRight=shoulder, interpol=0)
    shape.SetKnot(1, c4d.Vector(0.5, height, 0), 131072,
                  vTangentLeft=c4d.Vector(-crown, 0, 0),
                  vTangentRight=c4d.Vector(crown, 0, 0), interpol=0)
    shape.SetKnot(2, c4d.Vector(1, 0, 0), 196608,
                  vTangentLeft=c4d.Vector(-shoulder.x, shoulder.y, 0), interpol=0)
    return shape


def editable_shape(shape=None, preset=0):
    """Use the original 0..1 editor view without remapping any curve geometry."""
    shape = default_shape(preset) if shape is None else c4d.SplineData(shape)
    shape.SetRange(0, 1, 0.1, 0, 1, 0.1)
    return shape


def matches_profile_preset(shape, preset):
    if not isinstance(shape, c4d.SplineData) or preset not in range(4):
        return False
    keys = ("vPos", "vTangentLeft", "vTangentRight", "interpol")
    actual, expected = shape.GetKnots(), default_shape(preset).GetKnots()
    return (len(actual) == len(expected) and
            all(all(a[key] == b[key] for key in keys) for a, b in zip(actual, expected)))


class NeedleProfile:
    """Read the editor's native Bezier geometry without modifying its data."""
    def __init__(self, shape):
        shape = default_shape() if shape is None else shape
        if not isinstance(shape, c4d.SplineData):
            raise ValueError("Needle Profile must contain spline editor data.")
        knots = shape.GetKnots()
        if not 2 <= len(knots) <= 128:
            raise ValueError("Needle Profile needs between 2 and 128 control points.")
        for knot in knots:
            for key in ("vPos", "vTangentLeft", "vTangentRight"):
                vector = knot[key]
                if not all(math.isfinite(v) for v in (vector.x, vector.y, vector.z)):
                    raise ValueError("Needle Profile contains invalid coordinates.")
        self.first = knots[0]["vPos"].x
        self.width = knots[-1]["vPos"].x - self.first
        if self.width <= EPSILON:
            raise ValueError("Needle Profile needs a positive horizontal span.")
        self.curve = c4d.SplineObject(len(knots), c4d.SPLINETYPE_BEZIER)
        if self.curve is None:
            raise MemoryError("Could not allocate the needle profile spline.")
        # This is the same knot/tangent transfer used by Original / Custom.
        # Native spline evaluation preserves its vertical endpoint tangents.
        for index, knot in enumerate(knots):
            self.curve.SetPoint(index, knot["vPos"])
            left, right = knot["vTangentLeft"], knot["vTangentRight"]
            if knot["interpol"] == 1:  # Straight outgoing span in the editor.
                right = c4d.Vector(0)
            if index and knots[index-1]["interpol"] == 1:
                left = c4d.Vector(0)
            self.curve.SetTangent(index, left, right)
        self.curve.Message(c4d.MSG_UPDATE)
        self.knots = len(knots)
        self.editor = c4d.SplineData(shape)
        self.positions = [c4d.Vector(knot["vPos"]) for knot in knots]
        self.modes = [knot["interpol"] for knot in knots]
        # A profile describes progress between the two holes, so folded handles
        # cannot be used for an unambiguous crossing location.
        previous = -EPSILON
        for i in range(max(128, self.knots*8) + 1):
            p = self.point(i / max(128, self.knots*8))
            if p.x < previous-EPSILON or not -EPSILON <= p.x <= 1+EPSILON:
                raise ValueError("Needle Profile must progress from left to right without loops.")
            previous = p.x

    def point(self, t):
        # Native GetSplinePoint(1) can return a point just before the last knot.
        # Keep the editor's actual endpoint positions, including their heights.
        if t <= 0:
            point = self.positions[0]
            return c4d.Vector(point.x, point.y, 0)
        if t >= 1:
            point = self.positions[-1]
            return c4d.Vector(point.x, point.y, 0)
        segment = min(self.knots-2, int(t*(self.knots-1)))
        if self.modes[segment] == 2:
            blend = t*(self.knots-1)-segment
            a, b = self.positions[segment:segment+2]
            point = self.editor.GetPoint(a.x*(1-blend)+b.x*blend)
        else:
            point = self.curve.GetSplinePoint(t)
        return c4d.Vector(point.x, point.y, 0)


def value(op, identifier, default):
    result = op[identifier]
    return default if result is None else result


def settings(op):
    result = {}
    for name, (identifier, unused_type, default) in PARAMETERS.items():
        if isinstance(default, tuple):
            default = c4d.Vector(*default)
        result[name] = value(op, identifier, default)
    result["count"] = int(value(op, 1002, 100))
    result["radius"] = float(value(op, 1005, 0.5))
    result["rotation"] = c4d.utils.HPBToMatrix(c4d.Vector(
        value(op, 1009, 0.0), value(op, 1011, 0.0), value(op, 1010, 0.0)))
    return result


def resolved_surface(op, config):
    if not config["conform"]:
        return None
    surface = config["surface"]
    if surface is None:
        surface = op[1000]
    if surface is None:
        raise ValueError("Surface Fit needs a polygon mesh in Surface or Object.")
    if not isinstance(surface, c4d.BaseObject):
        raise ValueError("Surface must be a scene object containing a polygon mesh.")
    parent = op
    while parent is not None:
        if surface == parent:
            raise ValueError("Surface cannot be Quick Stitch or one of its parents.")
        parent = parent.GetUp()
    return surface


def _matrix_tuple(matrix):
    return tuple(component for vector in (matrix.off, matrix.v1, matrix.v2, matrix.v3)
                 for component in (vector.x, vector.y, vector.z))


def geometry_signature(op, config):
    """Snapshot geometry/render inputs, excluding the language and preset label."""
    def frozen(item):
        if isinstance(item, c4d.Vector):
            return (item.x, item.y, item.z)
        if isinstance(item, c4d.Matrix):
            return _matrix_tuple(item)
        if isinstance(item, c4d.SplineData):
            return tuple((frozen(knot["vPos"]), frozen(knot["vTangentLeft"]),
                          frozen(knot["vTangentRight"]), knot["interpol"])
                         for knot in item.GetKnots())
        if isinstance(item, c4d.BaseList2D):
            # Materials have no GetGUID; native markers identify both objects
            # and materials across Python wrappers without retaining the node.
            marker = item.FindUniqueID(c4d.MAXON_CREATOR_ID)
            return (item.GetType(), bytes(marker) if marker is not None else hash(item))
        return item

    fields = {name: frozen(item) for name, item in config.items()
              if name not in ("language", "shape_preset")}
    for identifier in (1000, 1003, 1004, 1006, 1007):
        fields["legacy_" + str(identifier)] = frozen(op[identifier])
    return tuple(sorted(fields.items()))


def dependency_signature(node, owner=None):
    """Only immutable values are retained across generator evaluations."""
    if node is None:
        return None
    result = []
    if owner is not None:
        result.append(("owner", _matrix_tuple(owner.GetMg())))
    pending = [node]
    while pending:
        current = pending.pop()
        matrix = current.GetMg()
        result.append((str(current.GetGUID()), current.GetDirty(
            c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_MATRIX | c4d.DIRTYFLAGS_CACHE),
            _matrix_tuple(matrix)))
        pending.extend(current.GetChildren())
    return tuple(result)


def unit(vector, fallback=None):
    if vector.GetLengthSquared() > EPSILON:
        return vector.GetNormalized()
    return c4d.Vector(0, 1, 0) if fallback is None else c4d.Vector(fallback)


def perpendicular(normal, tangent):
    projected = normal - tangent * normal.Dot(tangent)
    if projected.GetLengthSquared() < EPSILON:
        axis = min((c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0),
                    c4d.Vector(0, 0, 1)), key=lambda v: abs(v.Dot(tangent)))
        projected = axis - tangent * axis.Dot(tangent)
    return unit(projected)


def rotate(vector, axis, angle):
    return (vector * math.cos(angle) + axis.Cross(vector) * math.sin(angle) +
            axis * axis.Dot(vector) * (1.0 - math.cos(angle)))


def transport(normal, before, after):
    axis = before.Cross(after)
    length = axis.GetLength()
    if length > EPSILON:
        normal = rotate(normal, axis / length, math.atan2(length, before.Dot(after)))
    return perpendicular(normal, after)


def _meshes(node, matrix):
    """Evaluate editable meshes, deform caches and already evaluated generators."""
    deform = node.GetDeformCache()
    if deform is not None:
        yield from _meshes(deform, matrix * deform.GetMl())
        for child in node.GetChildren():
            yield from _meshes(child, matrix * child.GetMl())
        return
    cache = node.GetCache()
    if cache is not None:
        child = cache
        while child is not None:
            yield from _meshes(child, matrix * child.GetMl())
            child = child.GetNext()
        return
    if isinstance(node, c4d.PolygonObject):
        yield node, matrix
    for child in node.GetChildren():
        yield from _meshes(child, matrix * child.GetMl())


class SurfaceProjector:
    def __init__(self, goal, inverse_owner, distance, flip=False):
        self.distance = distance
        self.flip = flip
        self.entries = []
        self.misses = 0
        for mesh, matrix in _meshes(goal, goal.GetMg()):
            baked = mesh.GetClone(c4d.COPYFLAGS_NO_HIERARCHY)
            transform = inverse_owner * matrix
            points = [transform * p for p in mesh.GetAllPoints()]
            baked.SetAllPoints(points)
            baked.SetMl(c4d.Matrix())
            baked.Message(c4d.MSG_UPDATE)
            collider = c4d.utils.GeRayCollider()
            if not collider.Init(baked, True):
                continue
            normals = [c4d.Vector(0) for unused in points]
            polygons = mesh.GetAllPolygons()
            for polygon in polygons:
                normal = (points[polygon.b] - points[polygon.a]).Cross(
                    points[polygon.c] - points[polygon.a])
                for index in set((polygon.a, polygon.b, polygon.c, polygon.d)):
                    normals[index] += normal
            self.entries.append((baked, collider, points, polygons, normals))
        if not self.entries:
            raise ValueError("Surface must contain an evaluated polygon mesh.")

    def _normal(self, entry, hit):
        unused_mesh, unused_collider, points, polygons, normals = entry
        polygon = polygons[hit["face_id"]]
        triangles = [(polygon.a, polygon.b, polygon.c)]
        if polygon.c != polygon.d:
            triangles.append((polygon.a, polygon.c, polygon.d))
        for a, b, c in triangles:
            e0, e1, delta = points[b] - points[a], points[c] - points[a], hit["hitpos"] - points[a]
            d00, d01, d11 = e0.Dot(e0), e0.Dot(e1), e1.Dot(e1)
            denominator = d00 * d11 - d01 * d01
            if abs(denominator) < EPSILON:
                continue
            v = (d11 * delta.Dot(e0) - d01 * delta.Dot(e1)) / denominator
            w = (d00 * delta.Dot(e1) - d01 * delta.Dot(e0)) / denominator
            u = 1.0 - v - w
            if min(u, v, w) >= -0.001:
                normal = unit(normals[a] * u + normals[b] * v + normals[c] * w)
                if normal.Dot(hit["f_normal"]) < 0:
                    normal = -normal
                return -normal if self.flip else normal
        normal = unit(hit["f_normal"])
        return -normal if self.flip else normal

    def hit(self, point, direction, search_axes=False):
        axes = [unit(direction)]
        if search_axes:
            axes.extend((c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1)))
        nearest = None
        best = self.distance * self.distance
        for axis in axes:
            for entry in self.entries:
                collider = entry[1]
                if not collider.Intersect(point + axis * self.distance, -axis,
                                          2.0 * self.distance):
                    continue
                for index in range(collider.GetIntersectionCount()):
                    hit = collider.GetIntersection(index)
                    distance = (hit["hitpos"] - point).GetLengthSquared()
                    if distance <= best:
                        best = distance
                        nearest = (hit["hitpos"], self._normal(entry, hit))
        return nearest


class PathSampler:
    def __init__(self, path, owner, config):
        # A detached clone with the generator-relative transform is our local
        # coordinate system; all spline helper results use that system.
        self.path = path.GetClone()
        self.path.SetMl(~owner.GetMg() * path.GetMg())
        self.helper = c4d.utils.SplineHelp()
        flags = c4d.SPLINEHELPFLAGS_GLOBALSPACE | c4d.SPLINEHELPFLAGS_USERDEFORMERS
        if not self.helper.InitSplineWith(self.path, flags):
            raise ValueError("Could not evaluate the path spline.")
        self.config = config

    def segment(self, index, count, projector):
        return SegmentSampler(self, index, count, projector)


class SegmentSampler:
    def __init__(self, sampler, index, count, projector):
        self.helper, self.index = sampler.helper, index
        self.config, self.projector = sampler.config, projector
        self.length = self.helper.GetSegmentLength(index)
        cache = (self.helper.GetCacheObject() if hasattr(self.helper, "GetCacheObject")
                 else sampler.path.GetRealSpline())
        if isinstance(cache, c4d.SplineObject) and cache.GetSegmentCount():
            self.closed = cache.GetSegment(index)["closed"]
        else:
            real = sampler.path.GetRealSpline()
            self.closed = bool(real and real.IsClosed())
        # Lower default mesh density without lowering the existing frame precision.
        self.steps = min(8192, max(64, count * max(12, int(self.config["detail"]))))
        axes = (c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1), c4d.Vector(1, 0, 0),
                c4d.Vector(0, -1, 0), c4d.Vector(0, 0, -1), c4d.Vector(-1, 0, 0))
        hint = axes[max(0, min(5, int(self.config["up_axis"])))]
        self.frames = []
        previous_tangent = None
        positions = [self.helper.GetPosition(i / self.steps, index, True, True)
                     for i in range(self.steps + 1)]
        for i, point in enumerate(positions):
            before = (positions[i - 1] if i else
                      positions[-2] if self.closed else positions[0])
            after = (positions[i + 1] if i < self.steps else
                     positions[1] if self.closed else positions[-1])
            # Derive the tangent from arc-length samples. Some native Python
            # builds return the normal from SplineHelp.GetTangent().
            tangent = unit(after - before, c4d.Vector(0, 0, 1))
            if previous_tangent is not None:
                hint = transport(hint, previous_tangent, tangent)
            if projector is not None:
                hit = projector.hit(point, hint, search_axes=True)
                if hit is not None:
                    point, hint = hit
                else:
                    projector.misses += 1
            normal = perpendicular(hint, tangent)
            self.frames.append((point, tangent, normal))
            hint, previous_tangent = normal, tangent
        if self.closed:
            first, last = self.frames[0], self.frames[-1]
            delta = math.atan2(first[1].Dot(last[2].Cross(first[2])),
                               last[2].Dot(first[2]))
            self.frames = [(p, t, rotate(n, t, delta * i / self.steps))
                           for i, (p, t, n) in enumerate(self.frames)]

    def position(self, distance, across, elevation):
        if self.config["reverse"]:
            distance = self.length - distance
        offset = (distance % self.length if self.closed else
                  max(0.0, min(self.length, distance))) / self.length
        scaled = offset * self.steps
        index = min(self.steps - 1, int(scaled))
        blend = scaled - index
        a, b = self.frames[index], self.frames[index + 1]
        center = a[0] * (1 - blend) + b[0] * blend
        tangent = unit(a[1] * (1 - blend) + b[1] * blend)
        normal = perpendicular(a[2] * (1 - blend) + b[2] * blend, tangent)
        side = unit(normal.Cross(tangent))
        if self.config["mirror"]:
            across = -across
        local = self.config["rotation"] * c4d.Vector(across, 0, 0)
        point = center + side * local.x + normal * local.y + tangent * local.z
        if self.projector is not None:
            hit = self.projector.hit(point, normal)
            if hit is not None:
                point, normal = hit
            else:
                self.projector.misses += 1
        if self.projector is not None:
            # Offset translates the complete profile along the skin normal.
            # Thickness never moves the centerline or forces endpoints down.
            return point + normal * (self.config["surface_offset"] + elevation)
        lift = self.config["rotation"] * c4d.Vector(0, elevation, 0)
        return (point + normal * self.config["surface_offset"] +
                side * lift.x + normal * lift.y + tangent * lift.z)


def stitch_count(length, closed, config, allocation):
    if config["distribution"] == 1:
        pitch = config["pitch"]
        if pitch <= EPSILON:
            raise ValueError("Pitch must be greater than zero.")
        count = int(round(length / pitch)) if closed else int(math.floor(length / pitch))
    else:
        count = allocation
    if closed and count and config["style"] == ZIGZAG:
        count += count % 2
    if count > MAX_STITCHES:
        raise ValueError("Too many stitches; increase Pitch or reduce Count.")
    return max(0, count)


def strokes(style, count, pitch, config, closed):
    """Return (material group, anchor vectors, closed), with X=distance, Y=width."""
    half = config["seam_width"] * 0.5
    gap = 2.0 * config["radius"] + config["cross_clearance"]
    phase = (config["phase"] % 1.0) * pitch
    length = min(config["stitch_length"], pitch * 0.95)
    lean = max(0.05, min(0.95, config["lean"]))

    def p(s, x, h=0):
        return c4d.Vector(s + phase, x, h)

    if style in (RUNNING, DOUBLE, SLANT, CHEVRON, CROSS):
        for i in range(count):
            center = (i + 0.5) * pitch
            start, end = center - length / 2, center + length / 2
            if style in (RUNNING, DOUBLE):
                for group, lateral in ((0, 0),) if style == RUNNING else ((0, -half), (1, half)):
                    yield group, [p(start, lateral), p(end, lateral)], False
            elif style == SLANT:
                yield 0, [p(start, -half), p(start + length * lean, half)], False
            elif style == CHEVRON:
                tip = p(start + length * lean, 0)
                yield 0, [p(start, -half), tip], False
                yield 0, [tip, p(start, half)], False
            else:
                # Exact crossing separation is 2*radius + user clearance.
                yield 0, [p(start, -half), p(center, 0, gap), p(end, half)], False
                yield 1, [p(start, half), p(center, 0, 0), p(end, -half)], False
    elif style == ZIGZAG:
        for i in range(count):
            yield 0, [p(i * pitch, half if i % 2 else -half),
                      p((i + 1) * pitch, -half if i % 2 else half)], False
    elif style == DIAMOND:
        for group in range(2):
            for i in range(count):
                corner = p((i + lean) * pitch, -half if group == 0 else half)
                yield group, [p(i * pitch, 0), corner], False
                yield group, [corner, p((i + 1) * pitch, 0)], False
    elif style == BRAID:
        inner = half * 0.32
        for group, sign, stagger in ((0, -1, 0.0), (1, 1, lean)):
            for i in range(count):
                start = (i + stagger) * pitch
                points = [p(start, sign * inner, 0),
                          p(start + pitch * 0.25, sign * half, 0),
                          p(start + pitch * 0.70, sign * half, 0),
                          p(start + pitch, sign * inner, 0)]
                # Each pair is a complete, independently editable needle;
                # no extra edge connects consecutive needles.
                for a, b in zip(points, points[1:]):
                    yield group, [a, b], False
        for i in range(count):
            points = [p(i * pitch, -inner, 0),
                      p((i + lean) * pitch, inner, 0),
                      p((i + 1) * pitch, -inner, 0)]
            for a, b in zip(points, points[1:]):
                yield 2, [a, b], False


def sampling_detail(config):
    return max(4, min(48, int(config["detail"])))


def _profile_samples(evaluate, parameters, width, tolerance):
    """Keep control points and refine shoulders in physical, rather than GUI, units."""
    result = []

    def refine(t0, a, t1, b, depth):
        error = 0.0
        chord = c4d.Vector((b.x-a.x)*width, b.y-a.y, 0)
        squared = chord.GetLengthSquared()
        for fraction in (0.25, 0.5, 0.75):
            actual = evaluate(t0 + (t1-t0)*fraction)
            delta = c4d.Vector((actual.x-a.x)*width, actual.y-a.y, 0)
            blend = max(0.0, min(1.0, delta.Dot(chord)/squared)) if squared > 1e-24 else 0.0
            error = max(error, (delta-chord*blend).GetLengthSquared())
        if error > tolerance*tolerance and depth < 5:
            middle = (t0+t1)*0.5
            p = evaluate(middle)
            refine(t0, a, middle, p, depth+1)
            refine(middle, p, t1, b, depth+1)
        else:
            result.append(b)
        if len(result) > 1024:
            raise ValueError("Needle Profile is too detailed; simplify its control points.")

    parameters = sorted(set(parameters))
    first = evaluate(parameters[0])
    result.append(first)
    for start, end in zip(parameters, parameters[1:]):
        last = evaluate(end)
        refine(start, first, end, last, 0)
        first = last
    return result


def needle_outline(profile, width, config, crossing=None):
    """Scale one complete editor curve; never add or replace its endpoints."""
    detail = sampling_detail(config)
    parameters = {i/detail for i in range(detail+1)}
    parameters.update(i/(profile.knots-1) for i in range(profile.knots))
    first, last = profile.point(0), profile.point(1)
    if crossing is not None:
        center, extra = crossing
        if first.x+EPSILON < center < last.x-EPSILON:
            low, high = 0.0, 1.0
            for unused in range(48):
                middle = (low+high)*0.5
                if profile.point(middle).x < center:
                    low = middle
                else:
                    high = middle
            parameters.add((low+high)*0.5)
        else:
            crossing = None

    def evaluate(t):
        point = profile.point(t)
        height = config["arch"]*point.y
        if crossing is not None:
            center, extra = crossing
            ramp = ((point.x-first.x)/(center-first.x) if point.x <= center else
                    (last.x-point.x)/(last.x-center))
            height += extra*math.sin(math.pi*0.5*max(0.0, ramp))
        return c4d.Vector(point.x, height, 0)

    height = max(abs(config["arch"]), abs(crossing[1]) if crossing is not None else 0)
    tolerance = max(1e-6, min(config["radius"]*0.04, width*0.001, max(height*0.005, 1e-6)))
    # Previously the tight adaptive tolerance overrode a lower sample count.
    # Keep the existing quality at 12..48, and allow genuinely lighter meshes below 12.
    tolerance *= 2.0 ** max(0.0, (12-detail)*0.5)
    return _profile_samples(evaluate, parameters, width, tolerance)


def sample_needle(anchors, sampler, config):
    """Place a complete independent needle, including user-authored endpoints."""
    if len(anchors) not in (2, 3):
        raise ValueError("A needle needs two endpoints and an optional crossing marker.")
    a, b = anchors[0], anchors[-1]
    original_a, original_b = a, b
    start, end = 0.0, 1.0
    if not sampler.closed:
        delta = b.x - a.x
        if abs(delta) < EPSILON:
            if not 0 <= a.x <= sampler.length:
                return []
        else:
            limits = sorted(((0 - a.x) / delta, (sampler.length - a.x) / delta))
            start, end = max(0.0, limits[0]), min(1.0, limits[1])
            if end - start <= EPSILON:
                return []
            direction = b - a
            b = a + direction * end
            a = a + direction * start
    if (b - a).GetLengthSquared() <= EPSILON:
        return []
    crossing = None
    if len(anchors) == 3:
        direction = original_b - original_a
        fraction = (anchors[1] - original_a).Dot(direction) / direction.GetLengthSquared()
        crossing_t = (fraction - start) / (end - start)
        if EPSILON < crossing_t < 1.0 - EPSILON:
            crossing = (crossing_t, anchors[1].z)
    profile = config.get("_needle_profile") or NeedleProfile(config["needle_shape"])
    outline = needle_outline(profile, (b-a).GetLength(), config, crossing)
    points = []
    for point in outline:
        q = a*(1-point.x) + b*point.x
        points.append(sampler.position(q.x, q.y, point.y))
    return [(points, False)]


def make_sweep(group, strands, config):
    total = sum(len(points) for points, unused in strands)
    path = c4d.SplineObject(total, c4d.SPLINETYPE_LINEAR)
    if not path.ResizeObject(total, len(strands)):
        raise MemoryError("Could not allocate thread paths.")
    points = []
    for index, (strand, closed) in enumerate(strands):
        path.SetSegment(index, len(strand), closed)
        points.extend(strand)
    path.SetAllPoints(points)
    path[c4d.SPLINEOBJECT_INTERPOLATION] = c4d.SPLINEOBJECT_INTERPOLATION_NONE
    path.SetName("Thread Paths " + "ABC"[group])
    path.Message(c4d.MSG_UPDATE)
    profile = c4d.BaseObject(c4d.Osplinecircle)
    profile[c4d.PRIM_CIRCLE_RADIUS] = config["radius"]
    profile[c4d.SPLINEOBJECT_INTERPOLATION] = c4d.SPLINEOBJECT_INTERPOLATION_UNIFORM
    profile[c4d.SPLINEOBJECT_SUB] = max(1, min(32, int(config["profile_steps"])))
    sweep = c4d.BaseObject(c4d.Osweep)
    sweep.SetName(("Left / Thread A", "Right / Thread B", "Lacing / Thread C")[group])
    path.InsertUnder(sweep)
    profile.InsertUnder(sweep)
    sweep.SetPhong(True, True, c4d.utils.DegToRad(60))
    sweep[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
    sweep[c4d.ID_BASEOBJECT_COLOR] = config["color_" + "abc"[group]]
    material = config["material_" + "abc"[group]]
    if material is not None:
        if not isinstance(material, c4d.BaseMaterial):
            raise ValueError("Thread material slots accept materials only.")
        tag = c4d.TextureTag()
        tag.SetMaterial(material)
        tag[c4d.TEXTURETAG_PROJECTION] = c4d.TEXTURETAG_PROJECTION_UVW
        sweep.InsertTag(tag)
    return sweep


def build(owner, path, config, surface=None):
    root = c4d.BaseObject(c4d.Onull)
    root.SetName(STYLE_NAMES[config["style"]])
    if config["radius"] <= 0 or config["seam_width"] < 0 or config["stitch_length"] <= 0:
        return root
    if config["distribution"] == 0 and config["count"] <= 0:
        return root
    if config["distribution"] == 0 and config["count"] > MAX_STITCHES:
        raise ValueError("Too many stitches; reduce Count.")
    if config["distribution"] == 1 and config["pitch"] <= EPSILON:
        raise ValueError("Pitch must be greater than zero.")
    if config["ray_distance"] <= EPSILON and surface is not None:
        raise ValueError("Projection Distance must be greater than zero.")
    config = dict(config)
    config["_needle_profile"] = NeedleProfile(config["needle_shape"])
    sampler = PathSampler(path, owner, config)
    lengths = [sampler.helper.GetSegmentLength(i)
               for i in range(sampler.helper.GetSegmentCount())]
    total_length = sum(lengths)
    if total_length <= EPSILON:
        return root
    counts = [int(config["count"] * length / total_length) for length in lengths]
    if config["distribution"] == 0:
        remainder = config["count"] - sum(counts)
        order = sorted(range(len(lengths)), key=lambda i:
                       config["count"] * lengths[i] / total_length - counts[i], reverse=True)
        for i in order[:remainder]:
            counts[i] += 1
    projector = SurfaceProjector(surface, ~owner.GetMg(), config["ray_distance"],
                                 config["flip_normal"]) if surface is not None else None
    groups = [[], [], []]
    point_total = 0
    cell_total = 0
    for index, length in enumerate(lengths):
        if length <= EPSILON:
            continue
        estimate = (int(math.ceil(length / config["pitch"]))
                    if config["distribution"] == 1 else counts[index])
        if estimate > MAX_STITCHES:
            raise ValueError("Too many stitches; increase Pitch or reduce Count.")
        segment = sampler.segment(index, max(1, estimate), projector)
        count = stitch_count(length, segment.closed, config, counts[index])
        cell_total += count
        if cell_total > MAX_STITCHES:
            raise ValueError("Too many stitches across path segments.")
        if not count:
            continue
        pitch = length / count if segment.closed or config["distribution"] == 0 else config["pitch"]
        for group, anchors, closed in strokes(config["style"], count, pitch, config, segment.closed):
            if closed:
                raise ValueError("Visible needle pieces must be open.")
            estimate = (len(anchors) - 1) * sampling_detail(config) + 1
            if point_total + estimate > MAX_POINTS:
                raise ValueError("Thread detail is too high; reduce Detail or stitch count.")
            chunks = sample_needle(anchors, segment, config)
            point_total += sum(len(points) for points, unused in chunks)
            if point_total > MAX_POINTS:
                raise ValueError("Thread detail is too high; reduce Detail or stitch count.")
            groups[group].extend(chunks)
    if projector is not None and projector.misses:
        raise ValueError("Surface projection missed {} samples. Increase Projection Distance, "
                         "choose a closer path, or disable Surface Fit.".format(projector.misses))
    for group in reversed(range(3)):
        if groups[group]:
            make_sweep(group, groups[group], config).InsertUnder(root)
    return root
