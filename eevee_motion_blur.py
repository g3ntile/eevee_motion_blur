bl_info = {
    "name": "Eevee Motion Blur",
    "author": "Pablo Gentile",
    "version": (0, 31, 2),
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

# FUNCTIONS
# ###################################

# mbCompositorSetup
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

# render to array
def renderToArray(subfr):
    """Takes the output of a Viewer node and dumps it to a numpy array"""
    # move playhead
    bpy.context.scene.frame_set(subfr)
    # render
    bpy.ops.render.render()
    # collect image
    pixels = bpy.data.images['Viewer Node'].pixels
    
    # buffer to numpy array for faster manipulation
    return ( np.array(pixels[:]) )



# ###################################
# fn render with MB
def renderMBx1fr(realframe, shutter_mult, samples,context):
    """Renders one frame with motion blur and saves to output folder"""
    try: 
        # timer
        startTime = datetime.now()
        C = context
        scene = C.scene
        
        # setup compositor
        mbCompositorSetup()

        print("\n\nEMB starting  configuration\n\tframe start: " + str(realframe))

        # shutter angle in magnitude format

        print("\tshutter: " + str(shutter_mult))

        # Samples / amount of subframes to actually render based on shutter angle
        
        # adaptive samples version
        if (scene.emb_addon_use_adaptive):
            # proteccion contra valores inconsistentes
            if (scene.emb_addon_max_samples < scene.emb_addon_min_samples):
                scene.emb_addon_max_samples = scene.emb_addon_min_samples
            
            maxDelta = getMaxDelta(context)
            # print("Max delta is: " + str(maxDelta))
            samples = ceil( (maxDelta) / scene.emb_addon_adaptive_blur_samples) 
            if (samples > scene.emb_addon_max_samples):
                samples = scene.emb_addon_max_samples
            if (samples < scene.emb_addon_min_samples):
                samples = scene.emb_addon_min_samples
            print ( "\tusing adaptive sampling at "+ str(samples) + " subframes")
        
        else :
            # static samples
            samples = ceil(scene.eevee.motion_blur_samples) 
        
            print("\tstatic sampling: " + str(samples) + " subframes")

        # clamp shutter to 1
        shutter_mult = min(1, shutter_mult)

        # total number of subframes including unrendered
        fr_multiplier = ceil(samples/shutter_mult) # 12
        print("total subframes interpolated: " + str(fr_multiplier))

        # contribution of each subframe to real frame
        subframe_ratio = 1/samples 
        print("samples ratio: " + str(subframe_ratio))

        # where to save the files
        myRenderFolder = bpy.context.scene.render.filepath
        print("output path: " + myRenderFolder)

        # factor to scale the size of render
        resolution_factor = bpy.context.scene.render.resolution_percentage/100
        # effective render resolution
        renderWidth = round(bpy.context.scene.render.resolution_x * resolution_factor)
        renderHeight = round(bpy.context.scene.render.resolution_y * resolution_factor)
        # gamma de la imagen final
        #mygamma = 2.2
        mygamma = 2.35
        # Rebake: true for recalculate all bakes after the insertion of subframes, for better accuracy
        # in place for future implementations
        # but now with adaptive subsampling and retiming each frame is not a good idea
        rebake = False

        # Original values backup
        origFrameStart = bpy.context.scene.frame_start
        origFrameEnd = bpy.context.scene.frame_end
        origFrameRate = bpy.context.scene.render.fps
        origMapOld = bpy.context.scene.render.frame_map_old 
        origMapNew = bpy.context.scene.render.frame_map_new 

        # Start
        # Disable camera Motion blur
        orig_mb = bpy.context.scene.eevee.use_motion_blur
        bpy.context.scene.eevee.use_motion_blur = False


        #### inicializa la imagen 
        image_name = '__motion_blur_temp__'

        if image_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[image_name])
        image_object = bpy.data.images.new(name=image_name, alpha=True, width=renderWidth, height=renderHeight)
        # image_object.use_alpha = True
        image_object.alpha_mode = 'STRAIGHT'

        image_object = bpy.data.images[image_name]
        num_pixels = len(image_object.pixels)

        # Expand the timeline to render subframes
        # bpy.context.scene.frame_end *= fr_multiplier #obsolete for 1 frame
        bpy.context.scene.render.fps *= fr_multiplier
        bpy.context.scene.render.frame_map_old = 1
        bpy.context.scene.render.frame_map_new = fr_multiplier


        # Set expanded render variables
        # obsoleto, para eliminar tambien 
        ###expFrameStart = bpy.context.scene.frame_start
        ###expFrameEnd = bpy.context.scene.frame_end
        ###expFrameRate = bpy.context.scene.render.fps
        # inicializa el array con la imagen a procesar
        #myrender_arr = np.zeros(shape=(num_pixels))
        # llena un array con el ratio para hacer average poder multiplicarlo
        # esto está obsoleto tambien 
        # ratios_array = np.full((num_pixels), subframe_ratio)

        ##########
        # re-bake all for better accuracy
        if (rebake):
            bpy.ops.ptcache.free_bake_all()
            bpy.ops.ptcache.bake_all(bake=True)


        ##########################################################
        ### RENDER

        
        expanded_frame = realframe * fr_multiplier
        # inicializa el array y renderiza el primer frame
        myrender_arr = renderToArray(expanded_frame)/samples
        print("frame: " + str(realframe) + ".0 // " + str(expanded_frame))
        
        # render remaining subframes
        for subfr in range(expanded_frame+1, expanded_frame + samples):
            print("frame: " + str(realframe) + "." + str(subfr-expanded_frame)+ " // " + str(subfr))
            
            temparray = renderToArray(subfr)
            myrender_arr += (temparray/samples)

        # assign array to image with gamma    
        image_object.pixels = myrender_arr **(1/mygamma)
        #image_object.pixels = myrender_arr **(1/(mygamma*1.1))
        
        #image_object.pixels = myrender_arr 
        
        # ––––––––––– Save the image ––––––––––––––––
        # Now respects the fileformat in render output
        image_object.file_format = bpy.context.scene.render.image_settings.file_format
        myRenderFolder
        image_object.filepath_raw = myRenderFolder + "%04d" % realframe + bpy.context.scene.render.file_extension
        image_object.save_render(bpy.path.abspath(C.scene.render.filepath) + "%04d" % realframe + bpy.context.scene.render.file_extension)
        #image_object.save()

        # Restore the timeline 
        bpy.context.scene.render.fps = origFrameRate
        bpy.context.scene.render.frame_map_old = origMapOld
        bpy.context.scene.render.frame_map_new = origMapNew
        
        # Restore camera Motion blur
        bpy.context.scene.eevee.use_motion_blur = orig_mb
        bpy.context.scene.frame_current = realframe

        print("EMB Render frame "+ str(realframe) + " completed in " + str( datetime.now() - startTime))
    except KeyboardInterrupt:
        # Restore the timeline 
        ###bpy.context.scene.frame_end /= fr_multiplier
        bpy.context.scene.render.fps /= fr_multiplier
        bpy.context.scene.render.frame_map_old = 100
        bpy.context.scene.render.frame_map_new = 100
        # Restore camera Motion blur
        bpy.context.scene.eevee.use_motion_blur = orig_mb
        bpy.context.scene.frame_current = realframe
        print(' \n\nCANCELED')
        raise

    return{'FINISHED'}


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
        
        for frame in range(startframe, endframe+1, context.scene.frame_step):
            renderMBx1fr(frame, shutter_mult, samples, context)
            
        # closing notice
        print("EMB Sequence Render completed in " + str( datetime.now() - startTime)) 
    except KeyboardInterrupt:
        print(' \n\nCANCELED')
        raise
    return



#############################
# FOR ADAPTIVE SAMPLING

# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠
# fn convert bounding box to camera space
#           returns bounding box in camera space
def obBoxToCamera(obj, context):
    # print("\n\n2 . obBoxToCamera")
    scene = bpy.context.scene
    bb_vertices = [Vector(v) for v in obj.bound_box]
    mat = obj.matrix_world
    world_bb_vertices = [mat @ v for v in bb_vertices]

    co_2d = [world_to_camera_view(scene, scene.camera, v) for v in world_bb_vertices]  # from 0 to 1
    
    # devuelve una lista de las coordenadas 2D de los 8 vertices de la bounding box
    return(co_2d)
    
# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠

#fn get object delta in camera
# returns a list with the max delta
# result must be in pixels not camera space
def getObCameraDelta(obj, context):
    # print("\n\n3 . getObCameraDelta")
    C = bpy.context
    # print (C.scene.frame_current)
    
    #get next frame
    C.scene.frame_set (C.scene.frame_current + 1)
    # pasa los 8 vertices del bounding box a camera space (redundante esto se puede optimizar)
    ob_next = obBoxToCamera(obj, context)
    
    #get cur frame
    C.scene.frame_set (C.scene.frame_current - 1)
    # print (C.scene.frame_current)
    # pasa los 8 vertices del bounding box a camera space
    ob_current = obBoxToCamera(obj, context)
    
    # vertices usables 0 y 6:
    v1 = (ob_current[0])
    v2 = (ob_next[0])
    # print("v1: " + str(v1))
    
    # Pythagoras
    c1 = ((v2[0]-v1[0]) ** 2 )
    c2 = ((v2[1]-v1[1]) ** 2 )
    h = math.sqrt(c1+c2)
    #print(str(c1) + "  --:-- " + str(c2))
    #print (h)
    h = math.sqrt(h)
    # print (h)
    
    delta_a = get_2d_delta(ob_current[0], ob_next[0])
    delta_b = get_2d_delta(ob_current[6], ob_next[6])
    
    return (max(delta_a,delta_b))

# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠
# fn get_2d_delta
# calculate 2D deltas 
# gets input in cam space, result is in pixels
def get_2d_delta(v1,v2):
    v1 = camSpaceToPixels(v1)
    v2 = camSpaceToPixels(v2)
    # Pythagoras
    c1 = ((v2[0]-v1[0]) ** 2 )
    c2 = ((v2[1]-v1[1]) ** 2 )
    return( math.sqrt(c1+c2) )
     
# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠
#fn guess if obj is inside camera, return delta in pixels
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

    return()

# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠
# fn convierte camera space a pixels toma un list [x,y]
def camSpaceToPixels(pos):
    scene = bpy.context.scene
    render_scale = scene.render.resolution_percentage / 100
    render_size = list(int(res) * render_scale for res in [scene.render.resolution_x, scene.render.resolution_y])
    pixel_coords = arr.array('f')
    pix_x = pos[0] * render_size[0]
    pix_y = pos[1] * render_size[1]
    
    return([pix_x, pix_y] )

# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠
# ≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠≠
#––––––––––––––––––––––––––––––––––––––––––––––––––
# check all objs in scene

def getMaxDelta(context):    
    C = context
    mydeltas = [0]

    for obj in C.scene.objects:
        if ((obj.hide_render == False) and (obj.type == 'MESH') ):
            delta = isObInCamera(obj, C)
        try:
            if (delta):
                mydeltas.append(delta)
        except:
            pass
    if (mydeltas):
        print (mydeltas)
        print ("\n\t" + str(len(mydeltas)) + " objects in camera")
        print("\tmaximum delta in px is: ")
        print(max(mydeltas))
    return(abs(max(mydeltas)))

# ÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷÷
#                      CLASSES 

class RENDER_OT_render_eevee_forceblur_frame(bpy.types.Operator):
    """Render frame in eevee with motion blur"""
    bl_idname = "render.render_eevee_forceblur_frame"
    bl_label = "Render motion blur frame"

    def execute(self, context):
        frame=context.scene.frame_current
        shutter_mult = context.scene.eevee.motion_blur_shutter
        samples=context.scene.eevee.motion_blur_samples
        renderMBx1fr(frame, shutter_mult, samples, context)

        return {'FINISHED'}
    
class RENDER_OT_render_eevee_forceblur_sequence(bpy.types.Operator):
    """Render sequence in eevee with motion blur"""
    bl_idname = "render.render_eevee_forceblur_sequence"
    bl_label = "Render motion blur sequence"

    def execute(self, context):
        startframe = bpy.context.scene.frame_start
        endframe = bpy.context.scene.frame_end
        try: 
            renderMB_sequence(startframe, endframe, context)
        except ExitOK:
            print("OK")
        except ExitError:
            print("Failed")

        return {'FINISHED'}
    
#########################################################
############            PANEL                  ##########

class RENDER_PT_force_emb_panel(bpy.types.Panel):
    """Creates a Panel in the render properties window"""
    bl_label = "Forced Eevee motion blur 0.31.2"
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
        col.active = not (scene.emb_addon_use_adaptive)
        col.prop(scene.eevee, "motion_blur_samples")
        col = layout.column(align=True)
        col.prop(scene.eevee, "motion_blur_shutter")
        
        # adaptive sampling
        col = layout.column(align=True)
        row = layout.row()
        col.prop(scene, "emb_addon_use_adaptive")
        
        col.active = scene.emb_addon_use_adaptive
        row = layout.row()
        col.prop(scene, "emb_addon_adaptive_blur_samples")
        row = layout.row()
        col.prop(scene, "emb_addon_min_samples")
        col.prop(scene, "emb_addon_max_samples")
        
# Registration

def register():
    bpy.utils.register_class(RENDER_OT_render_eevee_forceblur_frame)
    bpy.utils.register_class(RENDER_OT_render_eevee_forceblur_sequence)
    bpy.utils.register_class(RENDER_PT_force_emb_panel)
    
    # custom properties
    # adaptive samples distance trigger
    bpy.types.Scene.emb_addon_adaptive_blur_samples = FloatProperty(
    default=10,
    name="Pixel tolerance",
    description = "distance in pixels an object must move to trigger another sample")
    # use adaptive or not
    bpy.types.Scene.emb_addon_use_adaptive = BoolProperty(
    default=True,
    name="Adaptive sampling",
    description = "evaluate samples each frame based on movement")
    
    # min samples
    bpy.types.Scene.emb_addon_min_samples = IntProperty(
    default=1,
    name="minimum samples",
    description = "",
    min=1)
    
    # max samples
    bpy.types.Scene.emb_addon_max_samples = IntProperty(
    default=20,
    name="maximum samples",
    description = "")

def unregister():
    del bpy.types.Scene.emb_addon_adaptive_blur_samples
    del bpy.types.Scene.emb_addon_use_adaptive
    del bpy.types.Scene.emb_addon_min_samples
    del bpy.types.Scene.emb_addon_max_samples
    
    bpy.utils.unregister_class(RENDER_OT_render_eevee_forceblur_frame)
    bpy.utils.unregister_class(RENDER_OT_render_eevee_forceblur_sequence)
    bpy.utils.unregister_class(RENDER_PT_force_emb_panel)

if __name__ == "__main__":
    register()
