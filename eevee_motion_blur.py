bl_info = {
    "name": "Eevee Motion Blur",
    "author": "Pablo Gentile",
    "version": (0, 1),
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
from mathutils import *; from math import *


C = bpy.context
D = bpy.data

# exec time


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
    
    # store the socket linked to output
    fromSocket = tree.nodes["Composite"].inputs[0].links[0].from_socket
    outSocket = tree.nodes["Composite"].inputs[0]
    # bpy.data.node_groups["Compositing Nodetree"].nodes["Composite"].use_alpha = False
    # create output node
    v = tree.nodes.new('CompositorNodeViewer')  
    v.location[0] = tree.nodes["Composite"].viewLocation[0]
    v.location[1] = tree.nodes["Composite"].viewLocation[1]-150
    #v.location = 750,210
    v.use_alpha = False
    
    # create Reroute node 
    l = tree.nodes.new('NodeReroute')
    l.location[0] = tree.nodes["Composite"].viewLocation[0] -20
    l.location[1] = tree.nodes["Composite"].viewLocation[1]-150
    
    # links both Nodes via reroute to share input
    links.new(fromSocket, l.inputs[0])  # link Image output to Viewer input
    links.new(l.outputs[0], v.inputs[0]) 
    links.new(l.outputs[0], outSocket) 
    return

# render to array
def renderToArray(subfr):
    """Takes the output of a Viewer node and dumps it to a numpy array"""
    # move playhead
    bpy.context.scene.frame_set(subfr)
    # print(bpy.context.scene.frame_current)
    # render
    bpy.ops.render.render()
    # collect image
    pixels = bpy.data.images['Viewer Node'].pixels
    
    # buffer to numpy array for faster manipulation
    return ( np.array(pixels[:]) )



# ###################################
# fn render with MB
def renderMBx1fr(realframe, shutter_mult, samples):
    """Renders one frame with motion blur and saves to output folder"""
    # timer
    startTime = datetime.now()
    
    # setup compositor
    mbCompositorSetup()

    print("EMB starting  configuration\nframe start: " + str(realframe))

    # shutter angle in magnitude format

    print("shutter: " + str(shutter_mult))

    # Samples / amount of subframes to actually render based on shutter angle
    effective_subframes = int(samples) # ceil(fr_multiplier*shutter_mult)
    print("samples: " + str(effective_subframes))

    # total number of subframes including unrendered
    fr_multiplier = int(effective_subframes/shutter_mult) # 12
    print("total subframes interpolated: " + str(fr_multiplier))

    # contribution of each subframe to real frame
    subframe_ratio = 1/effective_subframes #1/fr_multiplier
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
    mygamma = 2.2
    # Rebake: true for recalculate all bakes after the insertion of subframes, for better accuracy
    rebake = False

    # Original values backup
    origFrameStart = bpy.context.scene.frame_start
    origFrameEnd = bpy.context.scene.frame_end
    origFrameRate = bpy.context.scene.render.fps

    # Start
    # Disable camera Motion blur
    orig_mb = bpy.context.scene.eevee.use_motion_blur
    bpy.context.scene.eevee.use_motion_blur = False


    #### inicializa la imagen 
    image_name = '__motion_blur_temp__'

    if image_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[image_name])
    image_object = bpy.data.images.new(name=image_name, width=renderWidth, height=renderHeight)
    image_object = bpy.data.images[image_name]
    num_pixels = len(image_object.pixels)

    # Expand the timeline to render subframes
    # bpy.context.scene.frame_end *= fr_multiplier #obsolete for 1 frame
    bpy.context.scene.render.fps *= fr_multiplier
    bpy.context.scene.render.frame_map_old = 1
    bpy.context.scene.render.frame_map_new = fr_multiplier

    # Set expanded render variables
    ###expFrameStart = bpy.context.scene.frame_start
    ###expFrameEnd = bpy.context.scene.frame_end
    ###expFrameRate = bpy.context.scene.render.fps
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

    
    expanded_frame = realframe * fr_multiplier
    # inicializa el array y renderiza el primer frame
    myrender_arr = renderToArray(expanded_frame)/effective_subframes
    print("frame: " + str(realframe) + ".0 // " + str(expanded_frame))
    
    # render remaining subframes
    for subfr in range(expanded_frame+1, expanded_frame + effective_subframes):
        print("frame: " + str(realframe) + "." + str(subfr-expanded_frame)+ " // " + str(subfr))
        
        temparray = renderToArray(subfr)
        myrender_arr += (temparray/effective_subframes)

    # assign array to image with gamma    
    image_object.pixels = myrender_arr **(1/mygamma)

    # image_object.filepath_raw = myRenderFolder+ "" + "%04d" % realframe + ".exr"
    image_object.filepath_raw = myRenderFolder + "%04d" % realframe + ".exr"
    image_object.file_format = 'OPEN_EXR'
    #image_object.filepath_raw = "//__testBlenbpy.data.png"
    #image_object.file_format = 'PNG'
    image_object.save()


    ## To frame 1
    ## render + save to temp
    ## advance frame and repeat until effective_subframes
    ## open all rendered subframes and average
    ## save to render folder as frame 1
    ## advance 1*fr_multiplier frames and repeat


    # revert to previous values
    #bpy.context.scene.frame_end /= fr_multiplier
    #bpy.context.scene.render.fps /= fr_multiplier


    # Restore the timeline 
    ###bpy.context.scene.frame_end /= fr_multiplier
    bpy.context.scene.render.fps /= fr_multiplier
    bpy.context.scene.render.frame_map_old = 100
    bpy.context.scene.render.frame_map_new = 100
    # Restore camera Motion blur
    bpy.context.scene.eevee.use_motion_blur = orig_mb
    bpy.context.scene.frame_current = realframe

    print("EMB Render frame "+ str(realframe) + " completed in " + str( datetime.now() - startTime)) 
    return{'FINISHED'}


# fn render sequence
def renderMB_sequence(startframe, endframe, context):
    # exec time
    startTime = datetime.now()

    startframe = context.scene.frame_start
    endframe = context.scene.frame_end
    shutter_mult = context.scene.eevee.motion_blur_shutter
    samples=context.scene.eevee.motion_blur_samples

    for frame in range(startframe, endframe+1, context.scene.frame_step):
        renderMBx1fr(frame, shutter_mult, samples)
        
    # closing notice
    print("EMB Render completed in " + str( datetime.now() - startTime)) 
    return

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
        renderMBx1fr(frame, shutter_mult, samples)

        return {'FINISHED'}
    
class RENDER_OT_render_eevee_forceblur_sequence(bpy.types.Operator):
    """Render sequence in eevee with motion blur"""
    bl_idname = "render.render_eevee_forceblur_sequence"
    bl_label = "Render motion blur sequence"

    def execute(self, context):
        startframe = bpy.context.scene.frame_start
        endframe = bpy.context.scene.frame_end
        renderMB_sequence(startframe, endframe, context)

        return {'FINISHED'}
    
#########################################################
############            PANEL                  ##########

class RENDER_PT_force_emb_panel(bpy.types.Panel):
    """Creates a Panel in the render properties window"""
    bl_label = "Forced Eevee motion blur"
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

        row = layout.row()
        row.scale_y = 2.0
        row.operator("render.render_eevee_forceblur_frame")
        
        row.operator("render.render_eevee_forceblur_sequence")
        
        row = layout.row()
        row.prop(scene, "frame_start")
        row.prop(scene, "frame_end")
        row = layout.row()
        row.prop(scene.eevee, "motion_blur_samples")
        row.prop(scene.eevee, "motion_blur_shutter")


# Registration

def register():
    bpy.utils.register_class(RENDER_OT_render_eevee_forceblur_frame)
    bpy.utils.register_class(RENDER_OT_render_eevee_forceblur_sequence)
    bpy.utils.register_class(RENDER_PT_force_emb_panel)


def unregister():
    bpy.utils.unregister_class(RENDER_OT_render_eevee_forceblur_frame)
    bpy.utils.unregister_class(RENDER_OT_render_eevee_forceblur_sequence)
    bpy.utils.unregister_class(RENDER_PT_force_emb_panel)

if __name__ == "__main__":
    register()
