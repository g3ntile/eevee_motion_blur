bl_info = {
    "name": "Eevee Motion Blur",
    "author": "Pablo Gentile",
    "version": (0, 4 , 1),
    "blender": (2, 80, 0),
    "location": "Render Settings > Full Eevee Motion Blur",
    "description": "Real motion blur for Eevee",
    "warning": "",
    "wiki_url": "https://github.com/g3ntile/eevee_motion_blur/wiki",
    "tracker_url": "https://github.com/g3ntile/eevee_motion_blur",
    "category": "Render"
}

import bpy
from datetime import datetime
import numpy as np
import math
from mathutils import *; from math import *

from bpy_extras.object_utils import world_to_camera_view
import array as arr
from bpy.props import FloatProperty
from bpy.props import IntProperty
from bpy.props import BoolProperty


# #################################### ###################################
#                                 FUNCTIONS
# #################################### ###################################
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ------------------------------------------------------------------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ----------------------------mbCompositorSetup---------------------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
def mbCompositorSetup():
    """Sets up a Viewer node attached to the same input as the Composite"""
    bpy.context.scene.use_nodes = True
    tree = bpy.context.scene.node_tree
    links = tree.links
    
    # check if Viewer already exists
    for node in tree.nodes:
        if (node.type == 'VIEWER'):
            return
    
    # store the socket linked to output RGB
    fromSocket = tree.nodes["Composite"].inputs[0].links[0].from_socket
    outSocket = tree.nodes["Composite"].inputs[0]

    # create output node
    v = tree.nodes.new('CompositorNodeViewer')  
    v.location[0] = tree.nodes["Composite"].viewLocation[0]
    v.location[1] = tree.nodes["Composite"].viewLocation[1]-150
    #v.location = 750,210
    v.use_alpha = True
    
    # create Reroute node RGB
    l = tree.nodes.new('NodeReroute')
    l.location[0] = tree.nodes["Composite"].viewLocation[0] -20
    l.location[1] = tree.nodes["Composite"].viewLocation[1]-150
    l.label = "RGB"


    # links both Nodes via reroute to share input
    # RGB
    links.new(fromSocket, l.inputs[0])  # link Image output to Viewer input
    links.new(l.outputs[0], v.inputs[0]) 
    links.new(l.outputs[0], outSocket) 
    
    # alpha 
    if (tree.nodes["Composite"].inputs[1].links):
        fromSocket_alpha = tree.nodes["Composite"].inputs[1].links[0].from_socket
        outSocket_alpha = tree.nodes["Composite"].inputs[1]
        
        # create Reroute node ALPHA
        l_a = tree.nodes.new('NodeReroute')
        l_a.location[0] = tree.nodes["Composite"].viewLocation[0] -20
        l_a.location[1] = tree.nodes["Composite"].viewLocation[1]-180
        l_a.label = "ALPHA"

        # alpha
        links.new(fromSocket_alpha, l_a.inputs[0])  # link Image output to Viewer input
        links.new(l_a.outputs[0], v.inputs[1]) 
        links.new(l_a.outputs[0], outSocket_alpha) 
    return


# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# -----------------------------render to array 2--------------------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
def renderToArray_2(frame, subfr):
    """Takes the output of a Viewer node and dumps it to a numpy array"""
    # move playhead
    bpy.context.scene.frame_set(frame , subframe=subfr)
        
    # render
    bpy.ops.render.render()
    
    # collect image
    pixels = bpy.data.images['Viewer Node'].pixels
    
    # buffer to numpy array for faster manipulation
    return ( np.array(pixels[:]) )

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ----------------------------- render 1 frame ---------------------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
def renderMBx1fr(realframe, shutter_mult, samples,context):
    """Renders one frame with motion blur and saves to output folder"""
    try :
        C = context
        scene = C.scene
        
        # timer
        startTime = datetime.now()
        
        # –––––––––––––––––––
        # 1. variables setup
        # –––––––––––––––––––
        # clamp shutter to 1
        shutter_mult = min(1, shutter_mult)
        
        #Setup variable sampling
        
        # a. adaptive sampling
        if (scene.eeveeMotionBlur_vars.use_adaptive):
            # proteccion contra valores inconsistentes
            if (scene.eeveeMotionBlur_vars.max_samples < scene.eeveeMotionBlur_vars.min_samples):
                scene.eeveeMotionBlur_vars.max_samples = scene.eeveeMotionBlur_vars.min_samples
            
            maxDelta = getMaxDelta(context)
            # print("Max delta is: " + str(maxDelta))
            samples = ceil((maxDelta*shutter_mult) / scene.eeveeMotionBlur_vars.pixel_tolerance) #ceil( (maxDelta) / scene.eeveeMotionBlur_vars.adaptive_blur_samples) 
            
            if (samples > scene.eeveeMotionBlur_vars.max_samples):
                samples = scene.eeveeMotionBlur_vars.max_samples
            if (samples < scene.eeveeMotionBlur_vars.min_samples):
                samples = scene.eeveeMotionBlur_vars.min_samples
            if (samples == 0):
                samples = 1
            
        # b. static sampling
        else :
            # static samples
            samples = ceil(scene.eevee.motion_blur_samples) 
        
        # total number of subframes including unrendered
        fr_multiplier = ceil(samples/shutter_mult) # 12
        
        # contribution of each subframe to real frame
        subframe_ratio = 1/samples 
        
        # time step for each subframe 
        substep = 1/fr_multiplier
        
        # where to save the files
        myRenderFolder = bpy.context.scene.render.filepath
        
        # factor to scale the size of render
        resolution_factor = bpy.context.scene.render.resolution_percentage/100
        
        # effective render resolution
        renderWidth = round(bpy.context.scene.render.resolution_x * resolution_factor)
        renderHeight = round(bpy.context.scene.render.resolution_y * resolution_factor)
        
        # gamma de la imagen final 0.454545
        mygamma = bpy.context.scene.eeveeMotionBlur_vars.gamma
        
        # Disable camera Motion blur
        orig_mb = bpy.context.scene.eevee.use_motion_blur
        bpy.context.scene.eevee.use_motion_blur = False
        
        #### temp image setup
        image_name = '__motion_blur_temp__'
        if image_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[image_name])
        image_object = bpy.data.images.new(name=image_name, alpha=True, width=renderWidth, height=renderHeight)
        # image_object.use_alpha = True
        image_object.alpha_mode = 'STRAIGHT'
        image_object = bpy.data.images[image_name]
        num_pixels = len(image_object.pixels)
        
        # –––––––––––––––––––
        # 2. Setup Compositor
        mbCompositorSetup()
        
        
        
        # 
        print ('rendering ' + str(samples) + ' subframe samples')
        # –––––––––––––––––––
        # 3. Render       
        # render frame base y setup array
        myrender_arr = renderToArray_2(realframe, 0.0)/samples
        print("\trendered subframe #1/"+ str(samples)+ " ("+ str(realframe) + ".0)" )
        
        # render de cada subframe
        for i in range(1, samples):
            subfr = i*substep
            
            temparray = renderToArray_2(realframe, subfr)
            # suma ponderada para autoaverage
            myrender_arr += (temparray/samples)
            
            print("\trendered subframe #" + str(i+1) + "/" + str(samples) + " (" + str(realframe+subfr) + ")" )
        
        # assign array to image with gamma    
        image_object.pixels = myrender_arr ** mygamma 
            
        # –––––––––––––––––––
        # 4. Save the image
        # Now respects the fileformat in render output
        image_object.file_format = bpy.context.scene.render.image_settings.file_format
        # myRenderFolder
        image_object.filepath_raw = myRenderFolder + "%04d" % realframe + bpy.context.scene.render.file_extension
        image_object.save_render(filepath =  bpy.path.abspath(C.scene.render.filepath) + "%04d" % realframe + bpy.context.scene.render.file_extension, scene = C.scene )
        #image_object.save()
        
        rendertime = ( datetime.now() - startTime)
        print("EMB Render frame "+ str(realframe) + " in " + str( rendertime).split(".")[0])
    except:
        rendertime = False
        pass

    return (rendertime) # {'FINISHED'}

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ---------------------------- render sequence  --------------------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# fn render sequence
def renderMB_sequence(startframe, endframe, context):
    try:
        # exec time
        startTime = datetime.now()

        startframe = context.scene.frame_start
        endframe = context.scene.frame_end
        shutter_mult = context.scene.eevee.motion_blur_shutter
        
        # classic
        samples=context.scene.eevee.motion_blur_samples
        formertime = False
        for frame in range(startframe, endframe+1, context.scene.frame_step):
            framerendertime = renderMBx1fr(frame, shutter_mult, samples, context)
            # if not the first frame averages with former average
            if (formertime) :
                framerendertime = (formertime + framerendertime) / 2
            formertime = framerendertime
            print ("rendered frame "+ str(frame) + "/"+str(endframe))
            print (str((endframe - frame)*framerendertime).split(".")[0] + " remaining ")
            
        # closing notice
        print("EMB Sequence Render completed in " + str( datetime.now() - startTime)) 
    except KeyboardInterrupt:
        print(' \n\nCANCELED')
        raise
    return

# adaptive sampling ::::::::::::::::::::::::::::::::::::::::::::::::::::::
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ----------------------------- fn obBoxToCamera -------------------------
# ------------------- convert bounding box to camera space ---------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# returns bounding box in camera space (0 –> 1)
def obBoxToCamera(obj, context):
    # print("\n\n2 . obBoxToCamera")
    scene = context.scene
    bb_vertices = [Vector(v) for v in obj.bound_box]
    mat = obj.matrix_world
    world_bb_vertices = [mat @ v for v in bb_vertices]

    co_2d = [world_to_camera_view(scene, scene.camera, v) for v in world_bb_vertices]  # from 0 to 1
    
    # devuelve una lista de las coordenadas 2D de los 8 vertices de la bounding box
    return(co_2d)

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ------------------------ fn obBoxToCamera_2_verts ----------------------
# ------------------- convert 2 opposing verts from the ------------------
# ----------------------- bounding box to camera space -------------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# returns bounding box in camera space (0 –> 1)
#    ToDo
def obBoxToCamera_2_verts(obj, context):
    scene = context.scene

    bb_vertices = [Vector(v) for v in obj.bound_box]
    bb_vertices = [bb_vertices[0] , bb_vertices[6] ]
 
    mat = obj.matrix_world
    world_bb_vertices = [mat @ v for v in bb_vertices]
    
    co_2d = [world_to_camera_view(scene, scene.camera, v) for v in world_bb_vertices]  # from 0 to 1

    return(co_2d)

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ---------------------------- fn getObCameraDelta -----------------------
# ------------------------ get object delta in camera --------------------
# 
# returns a list with the max delta
# result must be in pixels not camera space
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
def getObCameraDelta(obj, context):
    # print("\n\n3 . getObCameraDelta")
    C = context
    # print (C.scene.frame_current)
    
    #get next frame
    C.scene.frame_set (C.scene.frame_current + 1)
    # pasa 2 vertices del bounding box a camera space (beta)
    ob_next = obBoxToCamera_2_verts(obj, context)
    
    #get cur frame
    C.scene.frame_set (C.scene.frame_current - 1)

    # pasa 2 vertices del bounding box a camera space (beta)
    ob_current = obBoxToCamera_2_verts(obj, context)
    
    delta_a = get_2d_delta(ob_current[0], ob_next[0])
    delta_b = get_2d_delta(ob_current[1], ob_next[1])
    
    return (max(delta_a,delta_b))

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ------------------------------- get_2d_delta ---------------------------
# ------------------------    calculate 2D deltas    ---------------------
# 
# gets input in cam space, result is in pixels
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# fn get_2d_delta
# calculate 2D deltas 
# gets input in cam space, result is in pixels
def get_2d_delta(v1,v2):
    v1 = camSpaceToPixels(v1)
    v2 = camSpaceToPixels(v2)
    # Pythagoras
    c1 = ((v2[0]-v1[0]) ** 2 )
    c2 = ((v2[1]-v1[1]) ** 2 )
    return( int(math.sqrt(c1+c2)))
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ----------------------------- fn isObInCamera --------------------------
# --------- guess if obj is inside camera, return delta in pixels --------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# guess if obj is inside camera, return delta in pixels
def isObInCamera(obj, context):
    # print("\n\n1. isObInCamera checking " + obj.name)
    xs= [x[0] for x in obBoxToCamera(obj, context)]
    ys= [x[1] for x in obBoxToCamera(obj, context)]
    
    # discriminate obs inside camera plane from the ones outside
    if (min(xs) < 1 and min(ys) < 1):
        if ((max(xs) > 0 ) and (max(ys) > 0)):
            #print("\n\n" + obj.name + " is in camera!")
            return (getObCameraDelta(obj, context))
        else :
            #print("\n\n" + obj.name + " is NOT in camera!")
            return ([])
    else :
        #print("\n\n" + obj.name + " is NOT in camera!")
        return ([])

    return
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ----------------------------- fn camSpaceToPixels ----------------------
# ----------- converts cam space to pixels, input is a list [x,y] --------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––

def camSpaceToPixels(pos):
    scene = bpy.context.scene
    render_scale = scene.render.resolution_percentage / 100
    render_size = list(int(res) * render_scale for res in [scene.render.resolution_x, scene.render.resolution_y])
    pixel_coords = arr.array('f')
    pix_x = pos[0] * render_size[0]
    pix_y = pos[1] * render_size[1]
    
    return([pix_x, pix_y])

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
# ----------------------------- fn getMaxDelta ---------------------------
# -------------- loops through all objects in scene, guesses  ------------
# ---------- which are in camera view and returns the max delta ---------- 
# ------------  meaning maximum speed in pixels/frame found --------------
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––

# check all objs in scene
def getMaxDelta(context):    
    C = context
    mydeltas = [0]
    
    # object types to check for motion
    ## types = ['MESH', 'ARMATURE']

    for obj in C.scene.objects:
        if ((obj.hide_render == False) and (obj.type == 'MESH') ):
            
            delta = isObInCamera(obj, C)
            try:
                if (delta):
                    # print("–––––––––––––––––––– " + obj.type)
                    print("• " + obj.name + " is in camera moving at " + str(delta) + "px per frame")
                    mydeltas.append(delta)
            except:
                print ("except")
                pass
    print('search ended') 
    maxd = abs(max(mydeltas))
    print("max total frame delta is "+ str(maxd) + "px")
    print("film exposed movement is " + str(maxd * (min(1, context.scene.eevee.motion_blur_shutter))) + "px")
    if (maxd == 0):
        print ("no movement found")

    # print ("mydeltas: " + str(mydeltas))
        
    return(abs(max(mydeltas)))


# #################################### ###################################
#                                  CLASSES
# #################################### ###################################


# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
class RENDER_OT_render_eevee_forceblur_frame(bpy.types.Operator):
    """Render frame in eevee with motion blur"""
    bl_idname = "render.render_eevee_forceblur_frame"
    bl_label = "Render motion blur frame"

    def execute(self, context):
        frame=context.scene.frame_current
        shutter_mult = context.scene.eevee.motion_blur_shutter
        samples=context.scene.eevee.motion_blur_samples
        try: 
            renderMBx1fr(frame, shutter_mult, samples, context)
        except ExitOK:
            print("OK")
        except ExitError:
            print("Failed")

        return {'FINISHED'}

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––

class RENDER_OT_render_eevee_forceblur_sequence(bpy.types.Operator):
    """Render sequence in eevee with motion blur"""
    bl_idname = "render.render_eevee_forceblur_sequence"
    bl_label = "Render motion blur sequence"

    def execute(self, context):
        startframe = bpy.context.scene.frame_start
        endframe = bpy.context.scene.frame_end
        try: 
            renderMB_sequence(startframe, endframe, context)
        except :
            print("!!!")
        

        return {'FINISHED'}

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––

# properties group


class eeveeMotionBlur_variables(bpy.types.PropertyGroup):
    
    pixel_tolerance : bpy.props.FloatProperty(
        name="Pixel tolerance",
        description="distance in pixels an object must move to trigger another sample",
        default=5
    )
    use_adaptive : bpy.props.BoolProperty(
        name="Adaptive sampling",
        description="evaluate samples each frame based on movement",
        default=True
    )
    min_samples : bpy.props.IntProperty(
        name="minimum samples",
        description="",
        default=1
    )
    max_samples : bpy.props.IntProperty(
        name="maximum samples",
        description="",
        default=20
    )
    gamma : bpy.props.FloatProperty(
        name="Gamma",
        description="gamma to compensate for inaccurate image saving",
        default=0.454545
    )

# #################################### ###################################
#                                   PANEL
# #################################### ###################################


class RENDER_PT_force_emb_panel(bpy.types.Panel):
    """Creates a Panel in the render properties window"""
    bl_label = "Forced Eevee motion blur 0.4.1"
    bl_idname = "RENDER_PT_force_emb"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_category = "Eevee motion blur"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Create two columns, by using a split layout.
        split = layout.split()

        # RENDER BUTTONS
        row = layout.row()
        row.scale_y = 2.0
        row.operator("render.render_eevee_forceblur_frame")
        
        row.operator("render.render_eevee_forceblur_sequence")
        
        # Start / End
        row = layout.row()
        row.prop(scene, "frame_start")
        row.prop(scene, "frame_end")
        
        # Eevee native motion blur settings
        row = layout.row()
        col = layout.column(align=True)
        col.active = not (scene.eeveeMotionBlur_vars.use_adaptive)
        col.prop(scene.eevee, "motion_blur_samples")
        col = layout.column(align=True)
        col.prop(scene.eevee, "motion_blur_shutter")
        
        # adaptive sampling
        col = layout.column(align=True)
        row = layout.row()
        col.prop(scene.eeveeMotionBlur_vars, "use_adaptive")
        
        col.active = scene.eeveeMotionBlur_vars.use_adaptive
        row = layout.row()
        col.prop(scene.eeveeMotionBlur_vars, "pixel_tolerance")
        row = layout.row()
        col.prop(scene.eeveeMotionBlur_vars, "min_samples")
        col.prop(scene.eeveeMotionBlur_vars, "max_samples")
        
        # Image gamma
        row = layout.row()
        row.prop(scene.eeveeMotionBlur_vars, "gamma")
        

# #################################### ###################################
#                                REGISTRATION
# #################################### ###################################

# Properties registered
#    eeveeMotionBlur_vars.pixel_tolerance
#    eeveeMotionBlur_vars.use_adaptive
#    eeveeMotionBlur_vars.min_samples
#    eeveeMotionBlur_vars.max_samples
#    eeveeMotionBlur_vars.gamma


classes = (
    RENDER_OT_render_eevee_forceblur_frame,
    RENDER_OT_render_eevee_forceblur_sequence,
    eeveeMotionBlur_variables,
    RENDER_PT_force_emb_panel
)

def register():
    from bpy.utils import register_class
    
    for cls in classes:
        register_class(cls)        
    bpy.types.Scene.eeveeMotionBlur_vars = bpy.props.PointerProperty(type=eeveeMotionBlur_variables)
    return

        
def unregister():
    from bpy.utils import unregister_class
       
    del bpy.types.Scene.eeveeMotionBlur_vars    
    for cls in reversed(classes):
        unregister_class(cls)
    return

### register, unregister = bpy.utils.register_classes_factory(classes)

if __name__ == "__main__":
    register()
