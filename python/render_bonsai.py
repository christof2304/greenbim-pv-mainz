"""IFC mit Bonsai laden und ein Vorschaubild rendern (Blender im Hintergrund).

    blender -b --python render_bonsai.py -- modell.ifc bild.png [azimut_grad] [hoehe_grad]
"""
import math
import sys

import addon_utils
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ifc, png = argv[0], argv[1]
cam_az = float(argv[2]) if len(argv) > 2 else 210.0   # Blickrichtung von SSW
cam_el = float(argv[3]) if len(argv) > 3 else 35.0

# Kein read_factory_settings: das deaktiviert Erweiterungen und lässt Blender
# versuchen, Bonsais Python-Pakete aufzuräumen. Stattdessen Startszene leeren.
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
if not hasattr(bpy.ops.bim, "load_project"):
    addon_utils.enable("bl_ext.blender_org.bonsai", default_set=False)
bpy.ops.bim.load_project(filepath=ifc, should_start_fresh_session=True)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, (hi - lo).length

scene = bpy.context.scene
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.lens = 50
a, e = math.radians(cam_az), math.radians(cam_el)
dist = size * 1.6
cam.location = center + Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))) * dist
cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(40), 0, math.radians(200))
scene.collection.objects.link(sun)

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.show_object_outline = True
scene.display.render_aa = "16"
scene.render.film_transparent = False
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (1, 1, 1)
scene.display.shading.background_type = "WORLD"
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
scene.render.filepath = png
bpy.ops.render.render(write_still=True)
print("RENDERED", png, len(meshes), "objects")
