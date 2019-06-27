# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####
#
########################################################
#          Script to Render Motion Blur in EEVEE       #
#                     by Pablo Gentile
# This is a working prototype, I will surely convert 
# into an addon with proper panels and buttons.

# Keep in mind that this is very alpha, don' expect this
# to be perfect, especially with reagr to usability
# still a big improvement over the shell version. 
# 
# Workflow:
# 1. Add A default Viewer node in the compositor, that takes 
#    exactly the same input as the Render Output.
#    (this is due to a bug/limitation of the Blender API, 
#    that prevents access to the Render Output via python)
# 2. Set the Motion Blur settings in the Render tab: Samples
#    and Shutter. 
#    Shutter should be set to 0.5 for standard 180 deg
#    cinematic blur. Smaller values give harder MBs and 
#    at 1 the blur will exagerated (trippy blurs).
# 3. The render will output to the folder specified in render 
#    settings, in EXR sequence format only –by now– and the 
#    filename is harcoded to _mb_output_0001.exr etc  
# 4. To render select this script in the text editor and hit 
#    Run Script
# 5. That's it. Wait until finished. You can check the progress
#    in the console.
# 6. You can't cancel the render right now –had some difficulties 
#    capturing the ESC– 
#    If you MUST end it before time you may kill Blender or CTL+C 
#    furiously in the console. Keep ion mind thar the render settings 
#    will be changed to accomodate the subframes careful with that,
#    revert the file. 

import bpy
from datetime import datetime
import numpy as np
from mathutils import *; from math import *

C = bpy.context
D = bpy.data

# exec time
startTime = datetime.now()

# FUNCTIONS
# ###################################
# render to array
def renderToArray(subfr):
    # move playhead
    C.scene.frame_set(subfr)
    # print(C.scene.frame_current)
    # render
    bpy.ops.render.render()
    # collect image
    pixels = bpy.data.images['Viewer Node'].pixels
    
    # buffer to numpy array for faster manipulation
    return ( np.array(pixels[:]) )



# ###################################

# future current frame for saving number
realframe = C.scene.frame_start
print("EMB starting  configuration\nframe start: " + str(realframe))

# shutter angle in magnitude format
shutter_mult = C.scene.eevee.motion_blur_shutter # shutter_angle/360 # eevee.motion_blur_shutter
print("shutter: " + str(shutter_mult))

# Samples / amount of subframes to actually render based on shutter angle
effective_subframes = int(C.scene.eevee.motion_blur_samples) # ceil(fr_multiplier*shutter_mult)
print("samples: " + str(effective_subframes))

# total number of subframes including unrendered
fr_multiplier = int(effective_subframes/shutter_mult) # 12
print("total subframes interpolated: " + str(fr_multiplier))

# contribution of each subframe to real frame
subframe_ratio = 1/effective_subframes #1/fr_multiplier
print("samples ratio: " + str(subframe_ratio))

# where to save the files
myRenderFolder = C.scene.render.filepath
print("output path: " + myRenderFolder)

# factor to scale the size of render
resolution_factor = C.scene.render.resolution_percentage/100
# effective render resolution
renderWidth = round(C.scene.render.resolution_x * resolution_factor)
renderHeight = round(C.scene.render.resolution_y * resolution_factor)
# gamma de la imagen final
mygamma = 2.2
# Rebake: true for recalculate all bakes after the insertion of subframes, for better accuracy
rebake = False

# Original values backup
origFrameStart = C.scene.frame_start
origFrameEnd = C.scene.frame_end
origFrameRate = C.scene.render.fps

# Start
# Disable camera Motion blur
orig_mb = bpy.context.scene.eevee.use_motion_blur
C.scene.eevee.use_motion_blur = False


#### inicializa la imagen 
image_name = '__motion_blur_temp__'

if image_name in D.images:
    D.images.remove(D.images[image_name])
image_object = D.images.new(name=image_name, width=renderWidth, height=renderHeight)
image_object = D.images[image_name]
num_pixels = len(image_object.pixels)

# Expand the timeline to render subframes
C.scene.frame_end *= fr_multiplier
C.scene.render.fps *= fr_multiplier
C.scene.render.frame_map_old = 1
C.scene.render.frame_map_new = fr_multiplier

# Set expanded render variables
expFrameStart = C.scene.frame_start
expFrameEnd = C.scene.frame_end
expFrameRate = C.scene.render.fps
# inicializa el array con la imagen a procesar
#myrender_arr = np.zeros(shape=(num_pixels))
# llena un array con el ratio para hacer average poder multiplicarlo
ratios_array = np.full((num_pixels), subframe_ratio)

##########
# re-bake all for better accuracy
if (rebake):
    bpy.ops.ptcache.free_bake_all()
    bpy.ops.ptcache.bake_all(bake=True)


##########################################################
### RENDER

for realframe in range( origFrameStart, origFrameEnd+1): 
    # escape con CTL C
#    if KeyboardInterrupt:
#        break
    expanded_frame = realframe * fr_multiplier
    # inicializa el array y renderiza el primer frame
    myrender_arr = renderToArray(expanded_frame)/effective_subframes
    print("frame: " + str(realframe) + ".0 // " + str(expanded_frame))
    
    # render remaining subframes
    for subfr in range(expanded_frame+1, expanded_frame + effective_subframes):
        print("frame: " + str(realframe) + "." + str(subfr-expanded_frame)+ " // " + str(subfr))

        temparray = renderToArray(subfr)
        # temparray *= ratios_array
        #myrender_arr += (np.array(pixels[:]) * ratios_array)
        myrender_arr += (temparray/effective_subframes)

    # assign array to image with gamma    
    image_object.pixels = myrender_arr **(1/mygamma)

    image_object.filepath_raw = myRenderFolder+ "/_mb_output_" + "%04d" % realframe + ".exr"
    image_object.file_format = 'OPEN_EXR'
    #image_object.filepath_raw = "//__testBlend.png"
    #image_object.file_format = 'PNG'
    image_object.save()

# Restore the timeline 
C.scene.frame_end /= fr_multiplier
C.scene.render.fps /= fr_multiplier
C.scene.render.frame_map_old = 1
C.scene.render.frame_map_new = 1
# Restore camera Motion blur
C.scene.eevee.use_motion_blur = orig_mb

print("EMB Render completed in " + str( datetime.now() - startTime)) 