#!/usr/bin/env python3
"""펫 캐릭터 GLB 생성기 (외부 의존성 없음).

구/호(arc) 프리미티브를 조합한 캐릭터와 노드 TRS 애니메이션 클립
(Idle / Hello / Play / Laugh)을 하나의 .glb 로 굽는다.

    python3 scripts/make_pet_glb.py            # -> public/assets/pet.glb
    python3 scripts/make_pet_glb.py out.glb
"""
import json
import math
import struct
import sys
from pathlib import Path

TAU = 2 * math.pi
FPS = 30
HID = 0.001  # "숨김" 상태의 스케일 (0 은 역행렬이 깨져서 피한다)


# ── 수학 헬퍼 ────────────────────────────────────────────────────────────────
def clamp01(x):
    return max(0.0, min(1.0, x))


def smooth(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def pulse(t, a, b, fade):
    """a 에서 올라와 b 에서 내려가는 0..1 엔벨로프."""
    return smooth((t - a) / fade) * smooth((b - t) / fade)


def bump(t, c, w):
    return math.exp(-(((t - c) / w) ** 2))


def lerp(a, b, k):
    return a + (b - a) * k


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat(e):
    """오일러(x, y, z 라디안) -> 쿼터니언(x, y, z, w). 적용 순서는 Z, X, Y."""
    x, y, z = e
    qx = (math.sin(x / 2), 0, 0, math.cos(x / 2))
    qy = (0, math.sin(y / 2), 0, math.cos(y / 2))
    qz = (0, 0, math.sin(z / 2), math.cos(z / 2))
    return qmul(qmul(qy, qx), qz)


def srgb(hex_color):
    h = hex_color.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c] + [1.0]


# ── 지오메트리 ───────────────────────────────────────────────────────────────
def sphere(seg=32, rings=20):
    pos, nor, idx = [], [], []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(seg + 1):
            th = TAU * j / seg
            p = (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th))
            pos.append(p)
            nor.append(p)
    for i in range(rings):
        for j in range(seg):
            a = i * (seg + 1) + j
            b = a + seg + 1
            idx += [a, a + 1, b, b, a + 1, b + 1]
    return pos, nor, idx


def moved(mesh, scale, offset):
    pos, nor, idx = mesh
    return [tuple(p[k] * scale + offset[k] for k in range(3)) for p in pos], nor, idx


def merge(parts):
    pos, nor, idx = [], [], []
    for p, n, i in parts:
        base = len(pos)
        pos += p
        nor += n
        idx += [base + v for v in i]
    return pos, nor, idx


def arc(R, r, a0, a1, seg=28, tube=12, caps=True):
    """XY 평면 위의 튜브 호. 각도는 +X 에서 +Y 방향(도)."""
    a0, a1 = math.radians(a0), math.radians(a1)
    pos, nor, idx = [], [], []
    for i in range(seg + 1):
        a = lerp(a0, a1, i / seg)
        ex, ey = math.cos(a), math.sin(a)
        for j in range(tube + 1):
            b = TAU * j / tube
            n = (ex * math.cos(b), ey * math.cos(b), math.sin(b))
            pos.append((R * ex + r * n[0], R * ey + r * n[1], r * n[2]))
            nor.append(n)
    for i in range(seg):
        for j in range(tube):
            a = i * (tube + 1) + j
            b = a + tube + 1
            idx += [a, b, a + 1, a + 1, b, b + 1]
    parts = [(pos, nor, idx)]
    if caps:
        ball = sphere(12, 8)
        for a in (a0, a1):
            parts.append(moved(ball, r, (R * math.cos(a), R * math.sin(a), 0)))
    return merge(parts)


# ── 캐릭터 정의 ──────────────────────────────────────────────────────────────
MATERIALS = {
    "fur": ("#FAD08F", 0.85),
    "white": ("#FFF6E6", 0.85),
    "pink": ("#FF9BAE", 0.9),
    "dark": ("#3B2A22", 0.3),
    "shine": ("#FFFFFF", 0.4),
    "green": ("#1EC97B", 0.75),
    "leaf": ("#5BD66F", 0.7),
    "mouth": ("#8C2F39", 0.8),
    "tongue": ("#FF7E95", 0.7),
}

GEOMS = {
    "sphere": sphere(),
    "ring": arc(0.33, 0.07, 0, 360, seg=48, tube=14, caps=False),
    "happy": arc(0.062, 0.015, 20, 160),
    "smile": arc(0.034, 0.009, 200, 340),
}

HC = (0.0, 0.42, 0.02)  # 머리 타원체 중심 (Head 조인트 기준)
HR = (0.58, 0.52, 0.52)  # 머리 타원체 반지름


def head_surf(x, y, lift=0.0):
    """머리 표면 위 (x, y) 지점의 위치와, +Z 를 법선에 맞추는 회전."""
    dx, dy = (x - HC[0]) / HR[0], (y - HC[1]) / HR[1]
    z = HC[2] + HR[2] * math.sqrt(max(0.0, 1 - dx * dx - dy * dy))
    n = ((x - HC[0]) / HR[0] ** 2, (y - HC[1]) / HR[1] ** 2, (z - HC[2]) / HR[2] ** 2)
    ln = math.sqrt(sum(c * c for c in n))
    n = tuple(c / ln for c in n)
    pos = (x + n[0] * lift, y + n[1] * lift, z + n[2] * lift)
    return pos, (-math.asin(n[1]), math.atan2(n[0], n[2]), 0.0)


NODES = []


def N(name, parent=None, t=(0, 0, 0), r=(0, 0, 0), s=(1, 1, 1), geom=None, mat=None):
    if isinstance(s, (int, float)):
        s = (s, s, s)
    NODES.append(dict(name=name, parent=parent, t=tuple(t), r=tuple(r), s=tuple(s), geom=geom, mat=mat))


def ball(name, parent, t, s, mat, r=(0, 0, 0)):
    N(name, parent, t=t, r=r, s=s, geom="sphere", mat=mat)


def build_nodes():
    N("Pet")

    for side, sx in (("L", 1), ("R", -1)):
        N("Foot" + side, "Pet", t=(0.21 * sx, 0.075, 0.1))
        ball("Foot%sMesh" % side, "Foot" + side, (0, 0, 0.04), (0.15, 0.085, 0.2), "white")

    N("Hips", "Pet", t=(0, 0.5, 0))
    ball("BodyMesh", "Hips", (0, 0, 0), (0.5, 0.48, 0.45), "fur")
    ball("BellyMesh", "Hips", (0, -0.04, 0.17), (0.34, 0.35, 0.31), "white")

    N("Tail", "Hips", t=(0, -0.2, -0.36))
    ball("TailMesh", "Tail", (0, 0.03, -0.12), 0.13, "white")

    N("Scarf", "Hips", t=(0, 0.37, 0), r=(math.pi / 2, 0, 0), s=(1, 0.92, 1.3), geom="ring", mat="green")
    ball("ScarfKnot", "Hips", (0.2, 0.33, 0.31), 0.085, "green")
    ball("ScarfEnd", "Hips", (0.25, 0.2, 0.36), (0.06, 0.13, 0.04), "green", r=(0, 0, 0.3))

    for side, sx in (("L", 1), ("R", -1)):
        N("Arm" + side, "Hips", t=(0.4 * sx, 0.2, 0.04), r=(0, 0, 0.44 * sx))
        ball("Arm%sMesh" % side, "Arm" + side, (0, -0.17, 0), (0.105, 0.2, 0.105), "fur")

    N("Head", "Hips", t=(0, 0.42, 0))
    ball("HeadMesh", "Head", HC, HR, "fur")

    for side, sx in (("L", 1), ("R", -1)):
        N("Ear" + side, "Head", t=(0.34 * sx, 0.76, 0))
        ball("Ear%sMesh" % side, "Ear" + side, (0.07 * sx, 0.09, 0), (0.18, 0.18, 0.1), "fur")
        ball("Ear%sInner" % side, "Ear" + side, (0.07 * sx, 0.085, 0.055), (0.11, 0.11, 0.06), "pink")

        pos, rot = head_surf(0.2 * sx, 0.46)
        N("Eye" + side, "Head", t=pos, r=rot)
        ball("Eye%sMesh" % side, "Eye" + side, (0, 0, 0), (0.062, 0.078, 0.028), "dark")
        ball("Eye%sShine" % side, "Eye" + side, (-0.018, 0.03, 0.022), 0.02, "shine")
        ball("Eye%sShine2" % side, "Eye" + side, (0.02, -0.026, 0.024), 0.009, "shine")

        pos, rot = head_surf(0.2 * sx, 0.46, lift=0.008)
        N("Eye%sHappy" % side, "Head", t=pos, r=rot, s=HID)
        N("Eye%sHappyMesh" % side, "Eye%sHappy" % side, t=(0, -0.035, 0), geom="happy", mat="dark")

        pos, rot = head_surf(0.37 * sx, 0.3)
        ball("Cheek" + side, "Head", pos, (0.085, 0.055, 0.018), "pink", r=rot)

    ball("Muzzle", "Head", (0, 0.3, 0.47), (0.17, 0.125, 0.1), "white")
    ball("Nose", "Head", (0, 0.345, 0.563), (0.045, 0.032, 0.028), "dark")

    N("MouthSmile", "Head", t=(0, 0.3, 0.562))
    N("MouthSmileL", "MouthSmile", t=(0.034, 0, 0), geom="smile", mat="dark")
    N("MouthSmileR", "MouthSmile", t=(-0.034, 0, 0), geom="smile", mat="dark")

    N("MouthOpen", "Head", t=(0, 0.268, 0.552), s=HID)
    ball("MouthOpenMesh", "MouthOpen", (0, 0, 0), (0.06, 0.055, 0.022), "mouth")
    ball("Tongue", "MouthOpen", (0, -0.022, 0.01), (0.036, 0.026, 0.016), "tongue")

    N("Sprout", "Head", t=(0, 0.93, 0.02))
    ball("SproutStem", "Sprout", (0, 0.06, 0), (0.02, 0.08, 0.02), "leaf")
    ball("SproutLeafL", "Sprout", (0.075, 0.15, 0), (0.09, 0.022, 0.05), "leaf", r=(0, 0, 0.5))
    ball("SproutLeafR", "Sprout", (-0.075, 0.15, 0), (0.09, 0.022, 0.05), "leaf", r=(0, 0, -0.5))


# ── 애니메이션 클립 ──────────────────────────────────────────────────────────
# 채널 함수 규칙:  't' = 기본 위치에 더할 오프셋,  'r' = 기본 오일러에 더할 오프셋,
#                 's' = 절대 스케일.
def uni(v):
    return (v, v, v)


def face(h, mouth=lambda t: 1.0):
    """h(t)=1 이면 웃는 눈(^ ^) + 벌린 입, 0 이면 기본 표정."""
    ch = {}
    for side in "LR":
        ch[("Eye" + side, "s")] = lambda t: uni(lerp(1, HID, h(t)))
        ch[("Eye%sHappy" % side, "s")] = lambda t: uni(lerp(HID, 1, h(t)))
    ch[("MouthSmile", "s")] = lambda t: uni(lerp(1, HID, h(t)))

    def open_scale(t):
        v = lerp(HID, 1, h(t))
        return (v, v * mouth(t), v)

    ch[("MouthOpen", "s")] = open_scale
    return ch


def clip_idle():
    D = 4.0
    b = lambda t: math.sin(TAU * t / 2)
    blink = lambda t: (1, 1 - 0.93 * bump(t, 2.6, 0.07), 1)
    return "Idle", D, {
        ("Hips", "t"): lambda t: (0, 0.012 * b(t), 0),
        ("Hips", "s"): lambda t: (1 + 0.008 * b(t), 1 + 0.014 * b(t), 1 + 0.008 * b(t)),
        ("Head", "r"): lambda t: (0.025 * math.sin(TAU * t / 2 + 0.6), 0, 0.045 * math.sin(TAU * t / 4)),
        ("Tail", "r"): lambda t: (0, 0.45 * math.sin(TAU * t * 1.5), 0),
        ("EyeL", "s"): blink,
        ("EyeR", "s"): blink,
        ("EarL", "r"): lambda t: (0, 0, -0.3 * bump(t, 1.1, 0.09)),
        ("EarR", "r"): lambda t: (0, 0, 0.3 * bump(t, 3.4, 0.09)),
        ("ArmL", "r"): lambda t: (0, 0, 0.05 * b(t)),
        ("ArmR", "r"): lambda t: (0, 0, -0.05 * b(t)),
        ("Sprout", "r"): lambda t: (0, 0, 0.08 * math.sin(TAU * t / 2 + 1.0)),
    }


def clip_hello():
    D = 2.6
    k = lambda t: pulse(t, 0.0, D, 0.35)
    h = lambda t: pulse(t, 0.2, D - 0.2, 0.15)
    wv = lambda t: math.sin(TAU * 2.3 * (t - 0.3))
    hop = lambda t: math.sin(math.pi * clamp01((t - 0.05) / 0.4))
    ch = {
        ("Pet", "t"): lambda t: (0, 0.14 * hop(t), 0),
        ("ArmL", "r"): lambda t: (-0.15 * k(t), 0, (1.76 + 0.35 * wv(t)) * k(t)),
        ("ArmR", "r"): lambda t: (0, 0, -0.25 * k(t)),
        ("Head", "r"): lambda t: (0.03 * wv(t) * k(t), 0, -0.13 * k(t)),
        ("Hips", "r"): lambda t: (0, 0, -0.05 * k(t)),
        ("Hips", "t"): lambda t: (0, 0.02 * abs(wv(t)) * k(t), 0),
        ("Tail", "r"): lambda t: (0, 0.6 * math.sin(TAU * 3 * t) * k(t), 0),
        ("EarL", "r"): lambda t: (0, 0, -0.12 * wv(t) * k(t)),
        ("EarR", "r"): lambda t: (0, 0, -0.12 * wv(t) * k(t)),
        ("Sprout", "r"): lambda t: (0, 0, 0.3 * wv(t) * k(t)),
    }
    ch.update(face(h, lambda t: 0.9 + 0.15 * wv(t)))
    return "Hello", D, ch


def clip_play():
    D = 3.2

    def jump(t, a, d, height):
        u = (t - a) / d
        return height * 4 * u * (1 - u) if 0 < u < 1 else 0.0

    y = lambda t: jump(t, 0.3, 0.8, 0.62) + jump(t, 1.42, 0.45, 0.28) + jump(t, 1.9, 0.45, 0.28)
    spin = lambda t: TAU * smooth((t - 0.3) / 0.8)
    lean = lambda t: 0.16 * (bump(t, 1.64, 0.16) - bump(t, 2.12, 0.16))
    air = lambda t: clamp01(y(t) / 0.2)
    au = lambda t: pulse(t, 0.25, 2.7, 0.25)
    h = lambda t: pulse(t, 0.2, 2.85, 0.15)
    fl = lambda t: math.sin(TAU * 3 * t)

    def squash(t):
        q = (
            -0.18 * bump(t, 0.2, 0.09)
            + 0.1 * bump(t, 0.55, 0.16)
            - 0.2 * bump(t, 1.17, 0.08)
            - 0.1 * bump(t, 1.89, 0.05)
            - 0.12 * bump(t, 2.4, 0.07)
        )
        return (1 - 0.6 * q, 1 + q, 1 - 0.6 * q)

    ch = {
        ("Pet", "t"): lambda t: (0, y(t), 0),
        ("Pet", "r"): lambda t: (0, spin(t), lean(t)),
        ("Pet", "s"): squash,
        ("ArmL", "r"): lambda t: (0, 0, (1.9 + 0.25 * fl(t)) * au(t)),
        ("ArmR", "r"): lambda t: (0, 0, -(1.9 + 0.25 * fl(t)) * au(t)),
        ("Head", "r"): lambda t: (-0.12 * au(t), 0, -0.5 * lean(t)),
        ("FootL", "r"): lambda t: (0.5 * air(t), 0, 0),
        ("FootR", "r"): lambda t: (0.5 * air(t), 0, 0),
        ("EarL", "r"): lambda t: (0, 0, -0.25 * air(t)),
        ("EarR", "r"): lambda t: (0, 0, 0.25 * air(t)),
        ("Tail", "r"): lambda t: (0, 0.6 * math.sin(TAU * 3.5 * t) * au(t), 0),
        ("Sprout", "r"): lambda t: (0, 0, 0.35 * fl(t) * au(t)),
    }
    ch.update(face(h, lambda t: 1.1))
    return "Play", D, ch


def clip_laugh():
    D = 2.8
    k = lambda t: pulse(t, 0.0, D, 0.3)
    h = lambda t: pulse(t, 0.1, D - 0.15, 0.15)
    ha = lambda t: math.sin(TAU * 6 * t)
    rock = lambda t: math.sin(TAU * 1.2 * t)

    def belly(t):
        q = (0.5 + 0.5 * ha(t)) * k(t)
        return (1 + 0.03 * q, 1 - 0.045 * q, 1 + 0.03 * q)

    ch = {
        ("Pet", "r"): lambda t: (0, 0, 0.05 * rock(t) * k(t)),
        ("Hips", "t"): lambda t: (0, 0.02 * ha(t) * k(t), 0),
        ("Hips", "s"): belly,
        ("Head", "r"): lambda t: ((-0.22 + 0.05 * ha(t)) * k(t), 0, 0.07 * rock(t) * k(t)),
        ("ArmL", "r"): lambda t: ((-0.75 + 0.1 * ha(t)) * k(t), 0, -0.3 * k(t)),
        ("ArmR", "r"): lambda t: ((-0.75 + 0.1 * ha(t)) * k(t), 0, 0.3 * k(t)),
        ("EarL", "r"): lambda t: (0, 0, -0.1 * ha(t) * k(t)),
        ("EarR", "r"): lambda t: (0, 0, 0.1 * ha(t) * k(t)),
        ("Tail", "r"): lambda t: (0, 0.5 * math.sin(TAU * 3 * t) * k(t), 0),
        ("Sprout", "r"): lambda t: (0, 0, 0.2 * ha(t) * k(t)),
    }
    ch.update(face(h, lambda t: 0.75 + 0.45 * (0.5 + 0.5 * ha(t))))
    return "Laugh", D, ch


# ── GLB 직렬화 ───────────────────────────────────────────────────────────────
FLOAT, USHORT = 5126, 5123
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


class Bin:
    def __init__(self):
        self.data = bytearray()
        self.views = []
        self.accessors = []

    def add(self, values, type_, comp=FLOAT, target=None, minmax=False):
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[type_]
        rows = [(v,) if width == 1 else tuple(v) for v in values]
        flat = [c for row in rows for c in row]
        blob = struct.pack("<%d%s" % (len(flat), "f" if comp == FLOAT else "H"), *flat)
        while len(self.data) % 4:
            self.data.append(0)
        view = {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(blob)}
        if target:
            view["target"] = target
        self.data += blob
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": comp, "count": len(rows), "type": type_}
        if minmax:
            acc["min"] = [f32(min(r[i] for r in rows)) for i in range(width)]
            acc["max"] = [f32(max(r[i] for r in rows)) for i in range(width)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def build_glb():
    build_nodes()
    bin_ = Bin()
    index = {n["name"]: i for i, n in enumerate(NODES)}

    mat_index = {name: i for i, name in enumerate(MATERIALS)}
    materials = [
        {
            "name": name,
            "pbrMetallicRoughness": {"baseColorFactor": srgb(color), "metallicFactor": 0.0, "roughnessFactor": rough},
        }
        for name, (color, rough) in MATERIALS.items()
    ]

    geom_acc = {}
    for name, (pos, nor, idx) in GEOMS.items():
        assert len(pos) < 65536
        geom_acc[name] = {
            "attributes": {
                "POSITION": bin_.add(pos, "VEC3", target=ARRAY_BUFFER, minmax=True),
                "NORMAL": bin_.add(nor, "VEC3", target=ARRAY_BUFFER),
            },
            "indices": bin_.add(idx, "SCALAR", comp=USHORT, target=ELEMENT_ARRAY_BUFFER),
        }

    meshes, mesh_index = [], {}
    nodes = []
    for n in NODES:
        node = {"name": n["name"]}
        if any(abs(v) > 1e-9 for v in n["t"]):
            node["translation"] = list(n["t"])
        if any(abs(v) > 1e-9 for v in n["r"]):
            node["rotation"] = list(quat(n["r"]))
        if any(abs(v - 1) > 1e-9 for v in n["s"]):
            node["scale"] = list(n["s"])
        if n["geom"]:
            key = (n["geom"], n["mat"])
            if key not in mesh_index:
                mesh_index[key] = len(meshes)
                meshes.append({"name": "%s_%s" % key, "primitives": [dict(geom_acc[n["geom"]], material=mat_index[n["mat"]])]})
            node["mesh"] = mesh_index[key]
        children = [i for i, c in enumerate(NODES) if c["parent"] == n["name"]]
        if children:
            node["children"] = children
        nodes.append(node)

    animations = []
    for name, duration, channels in (clip_idle(), clip_hello(), clip_play(), clip_laugh()):
        frames = int(round(duration * FPS))
        times = [i / FPS for i in range(frames + 1)]
        time_acc = bin_.add(times, "SCALAR", minmax=True)
        anim = {"name": name, "channels": [], "samplers": []}
        for (node_name, path), fn in channels.items():
            base = NODES[index[node_name]]
            if path == "t":
                out = [tuple(b + o for b, o in zip(base["t"], fn(t))) for t in times]
                acc = bin_.add(out, "VEC3")
            elif path == "s":
                acc = bin_.add([fn(t) for t in times], "VEC3")
            else:
                out, prev = [], None
                for t in times:
                    q = quat(tuple(b + o for b, o in zip(base["r"], fn(t))))
                    if prev and sum(a * b for a, b in zip(q, prev)) < 0:
                        q = tuple(-c for c in q)
                    out.append(q)
                    prev = q
                acc = bin_.add(out, "VEC4")
            anim["samplers"].append({"input": time_acc, "output": acc, "interpolation": "LINEAR"})
            anim["channels"].append(
                {
                    "sampler": len(anim["samplers"]) - 1,
                    "target": {"node": index[node_name], "path": {"t": "translation", "r": "rotation", "s": "scale"}[path]},
                }
            )
        animations.append(anim)

    while len(bin_.data) % 4:
        bin_.data.append(0)
    gltf = {
        "asset": {"version": "2.0", "generator": "make_pet_glb.py"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [index["Pet"]]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "animations": animations,
        "accessors": bin_.accessors,
        "bufferViews": bin_.views,
        "buffers": [{"byteLength": len(bin_.data)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_.data)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(js), b"JSON")
        + js
        + struct.pack("<I4s", len(bin_.data), b"BIN\x00")
        + bytes(bin_.data)
    )


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "public" / "assets" / "pet.glb"
    out.parent.mkdir(parents=True, exist_ok=True)
    glb = build_glb()
    out.write_bytes(glb)
    print("wrote %s (%.1f KB, %d nodes)" % (out, len(glb) / 1024, len(NODES)))
