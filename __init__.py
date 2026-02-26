import bpy
import numpy as np

try:
    import cv2
    _CV2_AVAILABLE = True
except Exception:
    cv2 = None
    _CV2_AVAILABLE = False


bl_info = {
    "name": "Webcam UV Texture Stream",
    "author": "Lucas Lugarinho & Mauricio van der Maesen de Sombreff",
    "version": (1, 0, 0),
    "blender": (2, 93, 0),
    "location": "View3D > Sidebar > Webcam",
    "description": "Stream a live webcam feed into an image texture and save it as PNG",
    "category": "Image",
}


IMAGE_DEFAULT = "Webcam_Feed"
FRAME_INTERVAL = 0.03  # ~30 FPS
DEFAULT_MATERIAL_NAME = "Webcam_Material"


class _WebcamState:
    def __init__(self):
        self.running = False
        self.last_error = ""
        self.operator = None

    def set_error(self, msg: str):
        self.last_error = msg
        print("[Webcam UV Stream]", msg)


STATE = _WebcamState()


def _ensure_material_for_object(context, obj):
    if obj is None:
        STATE.set_error("No target object selected.")
        return None, None

    if obj.type != 'MESH':
        STATE.set_error("Target object must be a mesh.")
        return None, None

    img_base = context.scene.webcam_image_name.strip() or IMAGE_DEFAULT
    img_name = f"{img_base}_{obj.name}"
    img = bpy.data.images.get(img_name)
    if img is None:
        w = int(context.scene.webcam_image_width)
        h = int(context.scene.webcam_image_height)
        if w <= 0 or h <= 0:
            STATE.set_error("Invalid image size.")
            return None, None
        img = bpy.data.images.new(img_name, width=w, height=h, alpha=True, float_buffer=False)

    mat_base = context.scene.webcam_material_name.strip() or DEFAULT_MATERIAL_NAME
    mat_name = f"{mat_base}_{obj.name}"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    tex_node = nodes.get("Webcam Image")
    if tex_node is None:
        tex_node = nodes.new("ShaderNodeTexImage")
        tex_node.name = "Webcam Image"
        tex_node.label = "Webcam Image"
        tex_node.location = (-400, 300)
    tex_node.image = img

    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 300)

    output = nodes.get("Material Output")
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 300)

    def ensure_link(out_socket, in_socket):
        for link in links:
            if link.from_socket == out_socket and link.to_socket == in_socket:
                return
        links.new(out_socket, in_socket)

    ensure_link(tex_node.outputs.get("Color"), bsdf.inputs.get("Base Color"))
    ensure_link(bsdf.outputs.get("BSDF"), output.inputs.get("Surface"))

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return img, mat


def _on_target_object_update(self, context):
    obj = context.scene.webcam_target_object
    if obj is None:
        return
    _ensure_material_for_object(context, obj)

class WM_OT_webcam_stream_start(bpy.types.Operator):
    """Start live webcam feed as texture"""
    bl_idname = "wm.webcam_stream_start"
    bl_label = "Start Webcam Stream"

    _timer = None
    _cap = None
    _img = None
    _size = None
    _obj = None

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            # If target object changed, update to its image/material
            current_obj = context.scene.webcam_target_object
            if current_obj is None:
                return {'PASS_THROUGH'}
            if self._obj is None or current_obj.name != self._obj.name:
                img, _mat = _ensure_material_for_object(context, current_obj)
                if img is None:
                    return {'PASS_THROUGH'}
                self._obj = current_obj
                self._img = img
                self._size = tuple(self._img.size)

            # Grab frame from webcam
            ret, frame = self._cap.read()
            if ret:
                # Resize to match our image texture dimensions
                resized = cv2.resize(frame, self._size, interpolation=cv2.INTER_AREA)
                
                # OpenCV uses BGR, Blender needs RGB
                # Also flip vertically if needed (webcams often need this)
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                
                # Convert to RGBA (add alpha channel) and normalize to 0-1 range
                rgba = np.ones((self._size[1], self._size[0], 4), dtype=np.float32)
                rgba[:,:,:3] = rgb.astype(np.float32) / 255.0

                # Update the Blender image
                self._img.pixels = rgba.flatten()

                # Force viewport refresh
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return {'PASS_THROUGH'}

    def execute(self, context):
        if STATE.running:
            return {'FINISHED'}

        if not _CV2_AVAILABLE:
            STATE.set_error("OpenCV (cv2) is not available. Install it in Blender's Python environment.")
            return {'CANCELLED'}

        obj = context.scene.webcam_target_object
        img, _mat = _ensure_material_for_object(context, obj)
        if img is None:
            return {'CANCELLED'}

        # Initialize webcam (0 is default camera, change if you have multiple)
        self._cap = cv2.VideoCapture(0)

        # Set desired resolution (optional)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Get reference to image texture
        self._obj = obj
        self._img = img
        self._size = tuple(self._img.size)

        # Set up timer for updates
        wm = context.window_manager
        self._timer = wm.event_timer_add(FRAME_INTERVAL, window=context.window)

        STATE.running = True
        STATE.last_error = ""
        STATE.operator = self

        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        # Clean up
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)

        if self._cap:
            self._cap.release()

        STATE.running = False
        STATE.operator = None

        # Optional: reset the image to something else
        # self._img.pixels = [0.0] * (self._size[0] * self._size[1] * 4)


class WM_OT_webcam_stream_stop(bpy.types.Operator):
    """Stop live webcam feed"""
    bl_idname = "wm.webcam_stream_stop"
    bl_label = "Stop Webcam Stream"

    def execute(self, context):
        if STATE.operator:
            STATE.operator.cancel(context)
        STATE.running = False
        return {'FINISHED'}


class WM_OT_webcam_save_png(bpy.types.Operator):
    """Save current webcam texture as PNG"""
    bl_idname = "wm.webcam_save_png"
    bl_label = "Save Webcam Texture as PNG"

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        obj = context.scene.webcam_target_object
        if obj is None:
            STATE.set_error("No target object selected.")
            return {'CANCELLED'}
        img_base = context.scene.webcam_image_name.strip() or IMAGE_DEFAULT
        img_name = f"{img_base}_{obj.name}"
        img = bpy.data.images.get(img_name)
        if img is None:
            STATE.set_error(f"Image not found: {img_name}")
            return {'CANCELLED'}

        path = self.filepath.strip()
        if not path:
            STATE.set_error("No file path selected.")
            return {'CANCELLED'}

        if not path.lower().endswith(".png"):
            path = f"{path}.png"

        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.abspath("//webcam_texture.png")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class WM_OT_webcam_setup_object(bpy.types.Operator):
    """Create a material and image texture for the selected object"""
    bl_idname = "wm.webcam_setup_object"
    bl_label = "Setup Webcam Material"

    def execute(self, context):
        obj = context.scene.webcam_target_object
        img, mat = _ensure_material_for_object(context, obj)
        if img is None or mat is None:
            return {'CANCELLED'}
        return {'FINISHED'}


class VIEW3D_PT_webcam_stream(bpy.types.Panel):
    bl_label = "Webcam UV Stream"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Webcam"

    def draw(self, context):
        layout = self.layout

        layout.prop(context.scene, "webcam_image_name", text="Image")
        layout.prop(context.scene, "webcam_target_object", text="Target")

        status = "Running" if STATE.running else "Stopped"
        row = layout.row()
        row.label(text=f"Status: {status}")

        if STATE.last_error:
            box = layout.box()
            box.label(text="Last error:")
            box.label(text=STATE.last_error[:120])

        row = layout.row()
        row.enabled = not STATE.running
        row.operator("wm.webcam_stream_start", text="Start")

        row = layout.row()
        row.enabled = STATE.running
        row.operator("wm.webcam_stream_stop", text="Stop")

        layout.separator()
        layout.prop(context.scene, "webcam_material_name", text="Material")
        row = layout.row()
        row.prop(context.scene, "webcam_image_width", text="Width")
        row.prop(context.scene, "webcam_image_height", text="Height")
        layout.separator()
        layout.operator("wm.webcam_save_png", text="Save PNG")


def register():
    bpy.utils.register_class(WM_OT_webcam_stream_start)
    bpy.utils.register_class(WM_OT_webcam_stream_stop)
    bpy.utils.register_class(WM_OT_webcam_save_png)
    bpy.utils.register_class(WM_OT_webcam_setup_object)
    bpy.utils.register_class(VIEW3D_PT_webcam_stream)

    bpy.types.Scene.webcam_image_name = bpy.props.StringProperty(
        name="Webcam Image",
        default=IMAGE_DEFAULT,
    )
    bpy.types.Scene.webcam_material_name = bpy.props.StringProperty(
        name="Webcam Material",
        default=DEFAULT_MATERIAL_NAME,
    )
    bpy.types.Scene.webcam_target_object = bpy.props.PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        update=_on_target_object_update,
    )
    bpy.types.Scene.webcam_image_width = bpy.props.IntProperty(
        name="Image Width",
        default=1024,
        min=1,
    )
    bpy.types.Scene.webcam_image_height = bpy.props.IntProperty(
        name="Image Height",
        default=1024,
        min=1,
    )


def unregister():
    del bpy.types.Scene.webcam_image_name
    del bpy.types.Scene.webcam_material_name
    del bpy.types.Scene.webcam_target_object
    del bpy.types.Scene.webcam_image_width
    del bpy.types.Scene.webcam_image_height

    bpy.utils.unregister_class(VIEW3D_PT_webcam_stream)
    bpy.utils.unregister_class(WM_OT_webcam_setup_object)
    bpy.utils.unregister_class(WM_OT_webcam_save_png)
    bpy.utils.unregister_class(WM_OT_webcam_stream_stop)
    bpy.utils.unregister_class(WM_OT_webcam_stream_start)


if __name__ == "__main__":
    register()
