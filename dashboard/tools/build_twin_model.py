#!/usr/bin/env python3
"""Build the slim digital-twin bundle for the dashboard from Pollen's official Reachy Mini MJCF.

    python dashboard/tools/build_twin_model.py <mjcf_dir> [out_dir]
      mjcf_dir: copy of reachy_mini/descriptions/reachy_mini/mjcf (reachy_mini.xml + assets/)
      out_dir : dashboard/frontend/public/model (default)

Why split the model in two:
  * MuJoCo-WASM only needs the KINEMATICS — bodies, joints, explicit inertials, sites, the Stewart
    closing constraints, actuators. All <geom> elements are removed (visual AND collision), so the
    model compiles instantly with zero mesh bytes and the passive chain still follows the motors.
  * three.js draws the 41 visual meshes, decimated (fast_simplification) and stored as a compact
    indexed binary (float32 xyz + uint16/uint32 index, ~1/5 of STL) so the CM4 + tunnel can serve it.
    geoms.json lists every visual geom: body, local pos/quat, mesh id, rgba → attached to body frames.

Output: twin.xml, geoms.json (geoms + pack offsets), meshes.bin (one fetch), manifest.json (sizes, faces, sha)
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

try:
    import fast_simplification as fs
except ImportError:  # pragma: no cover
    fs = None

TARGET_FACES_TOTAL = 90_000          # whole robot; < 2 MB binary before gzip
MIN_FACES = 120                      # never below this per mesh
MAX_FACES = 9_000                    # cap the hero meshes


def _f(s: str | None, default: str) -> list[float]:
    return [float(x) for x in (s or default).split()]


def decimate(mesh: trimesh.Trimesh, target: int) -> trimesh.Trimesh:
    if len(mesh.faces) <= target or fs is None:
        return mesh
    v, f = fs.simplify(mesh.vertices.astype(np.float64), mesh.faces.astype(np.int64), target_count=target, agg=7)
    out = trimesh.Trimesh(v, f, process=True)
    out.remove_unreferenced_vertices()
    return out


def pack(mesh: trimesh.Trimesh) -> bytes:
    v = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    f = np.ascontiguousarray(mesh.faces)
    if len(v) < 65535:
        idx = f.astype(np.uint16); itype = 2
    else:
        idx = f.astype(np.uint32); itype = 4
    # header: magic 'RMB1', nverts u32, nfaces u32, index bytes u8, pad 3
    head = b"RMB1" + struct.pack("<IIB3x", len(v), len(f), itype)
    return head + v.tobytes() + idx.tobytes()


def main() -> int:
    src = Path(sys.argv[1]).expanduser()
    out = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "frontend/public/model"
    out.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(src / "reachy_mini.xml")
    root = tree.getroot()
    comp = root.find("compiler")
    meshdir = src / (comp.get("meshdir", "assets") if comp is not None else "assets")

    materials = {m.get("name"): _f(m.get("rgba"), "0.5 0.5 0.5 1") for m in root.iter("material")}
    mesh_files = {m.get("name") or Path(m.get("file")).stem: m.get("file") for m in root.iter("mesh")}

    # collect visual geoms per body, then strip every geom
    geoms: list[dict] = []
    used: set[str] = set()
    for body in root.iter("body"):
        bname = body.get("name")
        for g in list(body.findall("geom")):
            if g.get("class") == "visual" and g.get("mesh") and bname:
                rgba = _f(g.get("rgba"), " ".join(map(str, materials.get(g.get("material"), [0.5, 0.5, 0.5, 1]))))
                geoms.append({"body": bname, "pos": _f(g.get("pos"), "0 0 0"), "quat": _f(g.get("quat"), "1 0 0 0"),
                              "mesh": g.get("mesh"), "rgba": rgba})
                used.add(g.get("mesh"))
            body.remove(g)
    for body in root.iter("worldbody"):
        for g in list(body.findall("geom")):
            body.remove(g)
    # drop mesh assets + materials + cameras (three.js has its own camera); keep sites/equality/actuators
    for asset in root.findall("asset"):
        for m in list(asset):
            if m.tag in ("mesh", "material", "texture"):
                asset.remove(m)
    for parent in root.iter():
        for cam in list(parent.findall("camera")):
            parent.remove(cam)
    if comp is not None:
        comp.attrib.pop("meshdir", None)
    # the hidden .bak / includes are irrelevant; make the model self-contained
    root.set("model", "reachy_mini_twin")
    # Twin gains: the daemon's PRESENT joint angles are the actuator targets, so the motors only
    # need to be quick and well damped (measured on the Mac: kp 50/kv 1 settles a 0.4 rad body-yaw
    # step in 64 ms of sim time and a cold start to <0.01 rad in 0.3 s; kp>=100 destabilises the
    # closed chain at the 2 ms timestep). Antennas are light → gentler gains.
    for act in root.iter("position"):
        if act.get("name") in ("yaw_body",) or (act.get("name") or "").startswith("stewart_"):
            act.set("kp", "50"); act.set("kv", "1.0"); act.set("forcerange", "-20 20")
        elif "antenna" in (act.get("name") or ""):
            act.set("kp", "20"); act.set("kv", "0.3"); act.set("forcerange", "-5 5")
    xml = ET.tostring(root, encoding="unicode")
    (out / "twin.xml").write_text(xml)

    # meshes: budget faces proportional to sqrt(original faces) so small parts keep detail
    loaded: dict[str, trimesh.Trimesh] = {}
    for name in sorted(used):
        m = trimesh.load(meshdir / mesh_files[name], force="mesh")
        if isinstance(m, trimesh.Scene):
            m = trimesh.util.concatenate(tuple(m.geometry.values()))
        loaded[name] = m
    weights = {n: np.sqrt(len(m.faces)) for n, m in loaded.items()}
    wsum = sum(weights.values())
    manifest = {"meshes": {}, "total_faces_in": 0, "total_faces_out": 0, "total_bytes": 0}
    packed = bytearray(); offsets: dict[str, list[int]] = {}
    for name, m in loaded.items():
        target = int(np.clip(TARGET_FACES_TOTAL * weights[name] / wsum, MIN_FACES, MAX_FACES))
        d = decimate(m, target)
        blob = pack(d)
        offsets[name] = [len(packed), len(blob)]
        packed += blob
        while len(packed) % 4:
            packed += b"\0"
        manifest["meshes"][name] = {"faces_in": int(len(m.faces)), "faces": int(len(d.faces)), "verts": int(len(d.vertices)),
                                    "bytes": len(blob), "sha": hashlib.sha1(blob).hexdigest()[:10]}
        manifest["total_faces_in"] += len(m.faces); manifest["total_faces_out"] += len(d.faces); manifest["total_bytes"] += len(blob)
    (out / "meshes.bin").write_bytes(bytes(packed))          # ONE fetch for every mesh (offsets in geoms.json)
    manifest["geoms"] = len(geoms)
    manifest["twin_xml_bytes"] = len(xml)
    manifest["pack_bytes"] = len(packed)
    manifest["pack_sha"] = hashlib.sha1(bytes(packed)).hexdigest()[:10]
    (out / "geoms.json").write_text(json.dumps({"geoms": geoms, "meshes": sorted(used), "pack": "meshes.bin",
                                                "offsets": offsets, "sha": manifest["pack_sha"],
                                                "xml_sha": hashlib.sha1(xml.encode()).hexdigest()[:10]}, separators=(",", ":")))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: v for k, v in manifest.items() if k != "meshes"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
