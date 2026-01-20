import c4d
import maxon
import os
import json
import sys

# redshift_utils 경로 추가
current_dir = os.path.dirname(__file__)
sub_dir = os.path.join(current_dir, "mw_utils")
if sub_dir not in sys.path:
    sys.path.append(sub_dir)

import redshift_utils

# --- Constants & IDs ---
PLUGIN_ID = 1067298

# Dialog IDs
GRP_MAIN = 1000
GRP_TRANSFORM = 1001
GRP_SCALE = 1002
GRP_SCALE_TYPE = 1003
GRP_RADIO_SCALE_TYPE = 1004
CHK_SCALE = 1005
CHK_OFFSET = 1006
CHK_ROTATION = 1007
CHK_TRIPLANAR = 1008
CHK_PER_TEXTURE = 1009
CHK_UV_PROJECTION = 1014 # New ID

RAD_ABS = 1010
RAD_VEC_ABS = 1011
BTN_APPLY = 1012
BTN_CLOSE = 1013

# Helper Functions
def get_port(node, port_id_string):
    inputs = node.GetInputs()
    port = inputs.FindChild(port_id_string)
    if not port.IsValid():
        outputs = node.GetOutputs()
        port = outputs.FindChild(port_id_string)
    return port

def create_control_nodes(graph, params):
    scale_node = None
    offset_node = None
    rotate_node = None
    new_nodes = []
    
    # Scale Abs 노드 생성
    if params["scale"]:
        if params["scale_type_vector"]:
            scale_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_ABS_VECTOR)
        else:
            scale_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_ABS)

        if scale_node: 
            new_nodes.append(scale_node)
            if params["scale_type_vector"]: # Vector Abs
                scale_in = scale_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_ABS_VECTOR_INPUT)
                scale_in.SetPortValue(maxon.Vector(1, 1, 1))
                scale_node.SetValue("net.maxon.node.base.name", "Vector Scale Abs")
            else: # Abs
                scale_in = scale_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_ABS_INPUT)
                scale_in.SetPortValue(1.0)
                scale_node.SetValue("net.maxon.node.base.name", "Scale Abs")

    # Offset Abs 노드 생성
    if params["offset"]:
        offset_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_ABS_VECTOR)
        if offset_node: 
            new_nodes.append(offset_node)
            offset_node.SetValue("net.maxon.node.base.name", "Offset Abs")

    # Rotation Abs 노드 생성
    if params["rotation"]:
        if params["triplanar"]:
            rotate_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_ABS_VECTOR)
        else:
            rotate_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_ABS)
        
        if rotate_node: 
            new_nodes.append(rotate_node)
            rotate_node.SetValue("net.maxon.node.base.name", "Rotation Abs")
            
    return scale_node, offset_node, rotate_node, new_nodes

def create_uv_projection_node(graph, params):
    uv_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_UV_CONTEXT_PROJECTION)
    uv_node.SetValue("net.maxon.node.base.name", "UV Context Projection")
    
    if params["triplanar"]:
        proj_type_port = uv_node.GetInputs().FindChild(redshift_utils.PORT_RS_UV_CONTEXT_PROJECTION_PROJECTION)
        if proj_type_port.IsValid():
            proj_type_port.SetPortValue(2) # 002 Triplanar

    return uv_node

def validate_selection(doc):
    c4d.CallCommand(465002328) # Node Editor
    mat = doc.GetActiveMaterial()
    if not mat:
        c4d.gui.MessageDialog("Please select a Texture node in the Node Editor.")
        return None, None

    nodeMaterial = mat.GetNodeMaterialReference()
    redshiftNodeSpaceId = maxon.Id("com.redshift3d.redshift4c4d.class.nodespace")
    
    if not nodeMaterial.HasSpace(redshiftNodeSpaceId):
        c4d.gui.MessageDialog("Please select a Redshift Node Material.")
        return None, None

    graph = nodeMaterial.GetGraph(redshiftNodeSpaceId)
    if graph.IsNullValue():
        return None, None

    selected_nodes = []
    maxon.GraphModelHelper.GetSelectedNodes(graph, maxon.NODE_KIND.NODE, lambda node: selected_nodes.append(node) or True)

    texture_nodes = []
    for node in selected_nodes:
        asset_id = node.GetValue("net.maxon.node.attribute.assetid")[0]
        if asset_id == redshift_utils.ID_RS_TEXTURESAMPLER:
            texture_nodes.append(node)

    if not texture_nodes:
        c4d.gui.MessageDialog("Please select at least one Texture node.")
        return None, None
        
    return graph, texture_nodes

def apply_texture_controls(graph, texture_nodes, params): 
    with graph.BeginTransaction() as transaction:
        created_nodes = []
        
        common_scale_node = None
        common_offset_node = None
        common_rotate_node = None
        common_uv_node = None
        
        if not params["per_texture"]:
            if params["uv_projection"]:
                common_uv_node = create_uv_projection_node(graph, params)
                created_nodes.append(common_uv_node)
            else:
                common_scale_node, common_offset_node, common_rotate_node, new_nodes = create_control_nodes(graph, params)
                created_nodes.extend(new_nodes)
        
        for tex_node in texture_nodes:
            uv_node = None
            scale_node = None
            offset_node = None
            rotate_node = None

            if params["per_texture"]:
                if params["uv_projection"]:
                    uv_node = create_uv_projection_node(graph, params)
                    created_nodes.append(uv_node)
                else:
                    scale_node, offset_node, rotate_node, new_nodes = create_control_nodes(graph, params)
                    created_nodes.extend(new_nodes)
            else:
                if params["uv_projection"]:
                    uv_node = common_uv_node
                else:
                    scale_node = common_scale_node
                    offset_node = common_offset_node
                    rotate_node = common_rotate_node
            
            def get_node_output(node):
                if not node or not node.IsValid(): return None
                aid = node.GetValue("net.maxon.node.attribute.assetid")[0]
                if aid == redshift_utils.ID_RS_MATH_ABS:
                    return node.GetOutputs().FindChild(redshift_utils.PORT_RS_MATH_ABS_OUT)
                elif aid == redshift_utils.ID_RS_MATH_ABS_VECTOR:
                    return node.GetOutputs().FindChild(redshift_utils.PORT_RS_MATH_ABS_VECTOR_OUT)
                return None

            if params["uv_projection"]:
                 if uv_node:
                    uv_out = uv_node.GetOutputs().FindChild(redshift_utils.PORT_RS_UV_CONTEXT_PROJECTION_OUTCONTEXT)
                    tex_uv_in = tex_node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_UV_CONTEXT)
                    
                    if uv_out.IsValid() and tex_uv_in.IsValid():
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_UV_CONTEXT)
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_SCALE)
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_OFFSET)
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_ROTATE)
                        uv_out.Connect(tex_uv_in)

            elif params["triplanar"]:
                tex_out_port = tex_node.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                connections = []
                if tex_out_port.IsValid():
                    tex_out_port.GetConnections(maxon.PORT_DIR.OUTPUT, connections)
                    for target_port in connections:
                        maxon.GraphModelHelper.RemoveAllConnections(tex_node)

                triplanar_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_TRIPLANAR)
                created_nodes.append(triplanar_node)
                
                tri_image_x = triplanar_node.GetInputs().FindChild(redshift_utils.PORT_RS_TRI_IMAGE_X)
                if tex_out_port.IsValid() and tri_image_x.IsValid():
                    tex_out_port.Connect(tri_image_x)
                
                if scale_node:
                    scale_out = get_node_output(scale_node)
                    tri_scale = triplanar_node.GetInputs().FindChild(redshift_utils.PORT_RS_TRI_SCALE)
                    if scale_out and scale_out.IsValid() and tri_scale.IsValid():
                        scale_out.Connect(tri_scale)

                if offset_node:
                    offset_out = get_node_output(offset_node)
                    tri_offset = triplanar_node.GetInputs().FindChild(redshift_utils.PORT_RS_TRI_OFFSET)
                    if offset_out and offset_out.IsValid() and tri_offset.IsValid():
                        offset_out.Connect(tri_offset)
                        
                if rotate_node:
                    rotate_out = get_node_output(rotate_node)
                    tri_rotate = triplanar_node.GetInputs().FindChild(redshift_utils.PORT_RS_TRI_ROTATE)
                    if rotate_out and rotate_out.IsValid() and tri_rotate.IsValid():
                        rotate_out.Connect(tri_rotate)

                tri_out_port = triplanar_node.GetOutputs().FindChild(redshift_utils.PORT_RS_TRI_OUTCOLOR)
                if tri_out_port.IsValid():
                    for connection in connections:
                        target_port = connection[0]
                        tri_out_port.Connect(target_port)

            else: # Direct connection
                if scale_node:
                    scale_out = get_node_output(scale_node)
                    tex_scale = tex_node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_SCALE)
                    if scale_out and scale_out.IsValid() and tex_scale.IsValid():
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_SCALE)
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_UV_CONTEXT)
                        scale_out.Connect(tex_scale)
                        
                if offset_node:
                    offset_out = get_node_output(offset_node)
                    tex_offset = tex_node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_OFFSET)
                    if offset_out and offset_out.IsValid() and tex_offset.IsValid():
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_OFFSET)
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_UV_CONTEXT)
                        offset_out.Connect(tex_offset)
                        
                if rotate_node:
                    rotate_out = get_node_output(rotate_node)
                    tex_rotate = tex_node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_ROTATE)
                    if rotate_out and rotate_out.IsValid() and tex_rotate.IsValid():
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_ROTATE)
                        redshift_utils.remove_connections(tex_node, redshift_utils.PORT_RS_TEX_UV_CONTEXT)
                        rotate_out.Connect(tex_rotate)

        for node in created_nodes:
            if node.IsValid():
                maxon.GraphModelHelper.SelectNode(node)

        transaction.Commit()

    c4d.CallCommand(465002311) # Arrange Selected Nodes
    c4d.EventAdd()
    return True


class TextureTransformDialog(c4d.gui.GeDialog):
    def __init__(self):
        self.params = {
            "uv_projection": False,
            "scale": True,
            "offset": False,
            "rotation": False,
            "triplanar": True,
            "scale_type_vector": False,
            "per_texture": False
        }
        self.settings_file = os.path.join(os.path.dirname(__file__), "mw_utils", "settings.json")

    def load_settings(self):
        if not os.path.exists(self.settings_file):
            return

        try:
            with open(self.settings_file, 'r') as f:
                all_settings = json.load(f)
            if "QuickTextureTransform" in all_settings:
                saved_params = all_settings["QuickTextureTransform"]
                for key, value in saved_params.items():
                    if key in self.params:
                        self.params[key] = value
        except Exception as e:
            print(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            all_settings = {}
            if os.path.exists(self.settings_file):
                 try:
                    with open(self.settings_file, 'r') as f:
                        all_settings = json.load(f)
                 except:
                     pass

            all_settings["QuickTextureTransform"] = self.params
            with open(self.settings_file, 'w') as f:
                json.dump(all_settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def CreateLayout(self):
        self.SetTitle("Quick Texture Transform")

        self.GroupBegin(GRP_MAIN, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0, "Controls", 0)
        self.GroupBorderSpace(10, 5, 10, 5)

        self.AddCheckbox(CHK_UV_PROJECTION, c4d.BFH_LEFT, 0, 0, "Use UV Context Projection(2026.1)")

        self.AddSeparatorH(c4d.BFH_SCALEFIT)

        self.AddCheckbox(CHK_SCALE, c4d.BFH_LEFT, 0, 0, "Scale")
        
        self.GroupBegin(GRP_SCALE_TYPE, c4d.BFH_SCALEFIT | c4d.BFV_TOP, 2, 0, "Scale Type", 0)
        self.GroupBorderSpace(15, 0, 0, 0)
        self.AddRadioGroup(GRP_RADIO_SCALE_TYPE, c4d.BFH_LEFT | c4d.BFV_TOP, 2, 0)
        self.AddChild(GRP_RADIO_SCALE_TYPE, RAD_ABS, "Abs")
        self.AddChild(GRP_RADIO_SCALE_TYPE, RAD_VEC_ABS, "Vector Abs")
        self.GroupEnd()
        
        self.AddCheckbox(CHK_OFFSET, c4d.BFH_LEFT | c4d.BFV_TOP, 0, 0, "Offset")
        self.AddCheckbox(CHK_ROTATION, c4d.BFH_LEFT | c4d.BFV_TOP, 0, 0, "Rotation")
        
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        
        self.AddCheckbox(CHK_TRIPLANAR, c4d.BFH_LEFT | c4d.BFV_TOP, 0, 0, "Use Triplanar")
        self.AddCheckbox(CHK_PER_TEXTURE, c4d.BFH_LEFT | c4d.BFV_TOP, 0, 0, "Create Node per Texture")
        
        if self.GroupBegin(0, c4d.BFH_CENTER, 2, 0, "", 0):
            self.GroupBorderSpace(0, 10, 0, 0)
            self.AddButton(BTN_APPLY, c4d.BFH_SCALEFIT, 100, 0, "Apply")
            self.AddButton(BTN_CLOSE, c4d.BFH_SCALEFIT, 100, 0, "Close")
        self.GroupEnd()
    
        self.GroupEnd() # GRP_MAIN
        return True

    def InitValues(self):
        self.load_settings()

        self.SetBool(CHK_UV_PROJECTION, self.params["uv_projection"])
        self.SetBool(CHK_SCALE, self.params["scale"])
        self.SetBool(CHK_OFFSET, self.params["offset"])
        self.SetBool(CHK_ROTATION, self.params["rotation"])
        self.SetBool(CHK_TRIPLANAR, self.params["triplanar"])
        self.SetBool(CHK_PER_TEXTURE, self.params["per_texture"])

        # Enable/Disable logic based on initial values
        is_uv = self.params["uv_projection"]
        self.Enable(CHK_SCALE, not is_uv)
        self.Enable(CHK_OFFSET, not is_uv)
        self.Enable(CHK_ROTATION, not is_uv)
        self.Enable(GRP_RADIO_SCALE_TYPE, not is_uv)
        
        # Scale Type logic
        if self.params["scale_type_vector"]:
            self.SetInt32(GRP_RADIO_SCALE_TYPE, RAD_VEC_ABS)
        else:
            self.SetInt32(GRP_RADIO_SCALE_TYPE, RAD_ABS)
            
        self.Enable(RAD_ABS, self.params["scale"] and not is_uv)
        self.Enable(RAD_VEC_ABS, self.params["scale"] and not is_uv)
        
        return True

    def Command(self, id, msg):
        if id == CHK_UV_PROJECTION:
            is_uv = self.GetBool(CHK_UV_PROJECTION)
            self.Enable(CHK_SCALE, not is_uv)
            self.Enable(CHK_OFFSET, not is_uv)
            self.Enable(CHK_ROTATION, not is_uv)
            self.Enable(GRP_RADIO_SCALE_TYPE, not is_uv)
            
            # Re-evaluate scale enable state
            if not is_uv:
                 self.Enable(RAD_ABS, self.GetBool(CHK_SCALE))
                 self.Enable(RAD_VEC_ABS, self.GetBool(CHK_SCALE))

        if id == CHK_SCALE:
            is_uv = self.GetBool(CHK_UV_PROJECTION)
            if not is_uv:
                self.Enable(RAD_ABS, self.GetBool(CHK_SCALE))
                self.Enable(RAD_VEC_ABS, self.GetBool(CHK_SCALE))

        if id == BTN_CLOSE:
            self.Close()
            return True
            
        elif id == BTN_APPLY:
            self.params["uv_projection"] = self.GetBool(CHK_UV_PROJECTION)
            self.params["scale"] = self.GetBool(CHK_SCALE)
            self.params["offset"] = self.GetBool(CHK_OFFSET)
            self.params["rotation"] = self.GetBool(CHK_ROTATION)
            self.params["triplanar"] = self.GetBool(CHK_TRIPLANAR)
            self.params["per_texture"] = self.GetBool(CHK_PER_TEXTURE)
            
            scale_type = self.GetInt32(GRP_RADIO_SCALE_TYPE)
            self.params["scale_type_vector"] = (scale_type == RAD_VEC_ABS)
            
            self.save_settings()
            
            graph, texture_nodes = validate_selection(c4d.documents.GetActiveDocument())
            if not graph:
                return True

            apply_texture_controls(graph, texture_nodes, self.params)
            return True
            
        return True


class QuickTextureTransformCommand(c4d.plugins.CommandData):
    dialog = None

    def Execute(self, doc):
        if self.dialog is None:
            self.dialog = TextureTransformDialog()
        return self.dialog.Open(c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=250, defaulth=200)

    def RestoreLayout(self, sec_ref):
        if self.dialog is None:
            self.dialog = TextureTransformDialog()
        return self.dialog.Restore(pluginid=PLUGIN_ID, secret=sec_ref)


if __name__ == "__main__":
    icon_path = os.path.join(os.path.dirname(__file__), "IMfine_Quick_Texture_Transform.tif")
    bmp = c4d.bitmaps.BaseBitmap()
    if os.path.exists(icon_path):
        bmp.InitWith(icon_path)
    else:
        bmp = None

    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str="Quick Texture Transform...",
        info=0,
        icon=bmp,
        help="Quickly creates nodes to control the selected texture nodes.",
        dat=QuickTextureTransformCommand()
    )
