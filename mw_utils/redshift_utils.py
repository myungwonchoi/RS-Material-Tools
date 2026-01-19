import c4d # 모듈이여도 c4d는 항상 필요
import maxon
import os
import re

# --- Constants & Node IDs ---
ID_RS_NODESPACE = maxon.Id("com.redshift3d.redshift4c4d.class.nodespace")
ID_RS_STANDARD_MATERIAL = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.standardmaterial")
ID_RS_OUTPUT = maxon.Id("com.redshift3d.redshift4c4d.node.output")
ID_RS_TEXTURESAMPLER = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.texturesampler")
ID_RS_BUMPMAP = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.bumpmap")
ID_RS_DISPLACEMENT = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.displacement")
ID_RS_UV_CONTEXT_PROJECTION = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.uvcontextprojection")
ID_RS_MATH_VECTOR_MULTIPLY = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathmulvector")

ID_RS_MATH_ABS = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathabs")
ID_RS_MATH_ABS_VECTOR = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathabsvector")
ID_RS_TRIPLANAR = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.triplanar")
ID_RS_MATH_INVERT = maxon.Id("com.redshift3d.redshift4c4d.nodes.core.rsmathinv")

# Port IDs
PORT_RS_STD_BASE_COLOR = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.base_color"
PORT_RS_STD_METALNESS = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.metalness"
PORT_RS_STD_ROUGHNESS = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.refl_roughness"
PORT_RS_STD_SPECULAR = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.refl_weight"
PORT_RS_STD_OPACITY = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.opacity_color"
PORT_RS_STD_EMISSION = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.emission_color"
PORT_RS_STD_BUMP_INPUT = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.bump_input"

PORT_RS_TEX_PATH = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.tex0" # This is the group, path is child
PORT_RS_TEX_SCALE = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.scale"
PORT_RS_TEX_OFFSET = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.offset"
PORT_RS_TEX_ROTATE = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.rotate"
PORT_RS_TEX_OUTCOLOR = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.outcolor"
PORT_RS_TEX_UV_CONTEXT = "com.redshift3d.redshift4c4d.nodes.core.texturesampler.uv_context"

PORT_RS_TRI_IMAGE_X = "com.redshift3d.redshift4c4d.nodes.core.triplanar.imagex"
PORT_RS_TRI_SCALE = "com.redshift3d.redshift4c4d.nodes.core.triplanar.scale"
PORT_RS_TRI_OFFSET = "com.redshift3d.redshift4c4d.nodes.core.triplanar.offset"
PORT_RS_TRI_ROTATE = "com.redshift3d.redshift4c4d.nodes.core.triplanar.rotation"
PORT_RS_TRI_OUTCOLOR = "com.redshift3d.redshift4c4d.nodes.core.triplanar.outcolor"

PORT_RS_BUMP_INPUT = "com.redshift3d.redshift4c4d.nodes.core.bumpmap.input"
PORT_RS_BUMP_OUT = "com.redshift3d.redshift4c4d.nodes.core.bumpmap.out"
PORT_RS_BUMP_TYPE = "com.redshift3d.redshift4c4d.nodes.core.bumpmap.inputtype"
PORT_RS_MATH_VECTOR_MULTIPLY_INPUT1 = "com.redshift3d.redshift4c4d.nodes.core.rsmathmulvector.input1"
PORT_RS_MATH_VECTOR_MULTIPLY_INPUT2 = "com.redshift3d.redshift4c4d.nodes.core.rsmathmulvector.input2"
PORT_RS_MATH_VECTOR_MULTIPLY_OUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathmulvector.out"

PORT_RS_MATH_INVERT_INPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathinv.input"
PORT_RS_MATH_INVERT_OUTPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathinv.out"

PORT_RS_UV_CONTEXT_PROJECTION_OUTCONTEXT = "com.redshift3d.redshift4c4d.nodes.core.uvcontextprojection.outcontext"
PORT_RS_UV_CONTEXT_PROJECTION_PROJECTION = "com.redshift3d.redshift4c4d.nodes.core.uvcontextprojection.proj_type"
# 000 Passthrough, # 001 UV Channel, # 002 Triplanar

PORT_RS_MATH_ABS_INPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabs.input"
PORT_RS_MATH_ABS_OUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabs.out"

PORT_RS_MATH_ABS_VECTOR_INPUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabsvector.input"
PORT_RS_MATH_ABS_VECTOR_OUT = "com.redshift3d.redshift4c4d.nodes.core.rsmathabsvector.out"

PORT_RS_DISP_TEXMAP = "com.redshift3d.redshift4c4d.nodes.core.displacement.texmap"
PORT_RS_DISP_OUT = "com.redshift3d.redshift4c4d.nodes.core.displacement.out"
PORT_RS_OUTPUT_DISPLACEMENT = "com.redshift3d.redshift4c4d.node.output.displacement"

# Colorspace
RS_INPUT_COLORSPACE_RAW = "RS_INPUT_COLORSPACE_RAW"

def create_texture_node(graph, texture_path):
    """Creates a Texture Sampler node and sets the path."""
    tex_node = graph.AddChild(maxon.Id(), ID_RS_TEXTURESAMPLER)
    
    # Set Texture Path
    path_port = tex_node.GetInputs().FindChild(PORT_RS_TEX_PATH).FindChild("path")
    if path_port.IsValid():
        path_port.SetPortValue(texture_path)
    
    return tex_node

def find_standard_material_and_output(graph):
    """Finds the Standard Material and Output node in the graph."""
    standard_mat = None
    output_node = None
    
    root = graph.GetRoot()
    for node in root.GetInnerNodes(mask=maxon.NODE_KIND.NODE, includeThis=False):
        asset_id = node.GetValue("net.maxon.node.attribute.assetid")[0]
        if asset_id == ID_RS_STANDARD_MATERIAL:
            standard_mat = node
        elif asset_id == ID_RS_OUTPUT:
            output_node = node
            
    return standard_mat, output_node

def remove_connections(node, port_id):
    """
    특정 노드의 특정 포트에 연결된 모든 연결을 제거합니다.
    """
    if not node or not node.IsValid():
        return

    input_ports = node.GetInputs().GetChildren() # 입력 포트 리스트
    for input_port in input_ports:
        port_name = input_port.GetId().ToString()
        if port_name == port_id:
            # 각 포트에 연결된 선(Connection) 가져오기
            connections = []
            input_port.GetConnections(maxon.PORT_DIR.INPUT, connections)
            for connection in connections:
                source_port = connection[0] # 연결된 소스 포트 (출력 포트)
                # RemoveConnection(source, destination)
                maxon.GraphModelHelper.RemoveConnection(source_port, input_port)
            break # 포트를 찾았으므로 루프 종료


# --- Channel Suffixes ---
# CHANNEL_SUFFIXES = {
#     "diffuse_color": "BaseColor", # RS Material
#     "base_color": "BaseColor", # Standard Material
#     "normal": "Normal",
#     "ao": "AO",
#     "refl_metalness": "Metalic", # RS Material    
#     "metalness": "Metalic", # Standard Material
#     "refl_roughness": "Roughness",
#     "refl_weight": "Specular",
#     "glossiness": "Glossiness",
#     "opacity_color": "Opacity",
#     "translucency": "Translucency",
#     "bump" : "Bump",
#     "displacement" : "Displacement",
#     "emission_color" : "Emissive"
# }

TEXTURE_CHANNELS = {
    "base_color":        [
        "basecolor", "base", "color", "albedo", "diffuse", "diff", 
        "col", "bc", "alb", "rgb" , "d", "dif"
    ],
    "normal":       [
        "normal", "norm", "nrm", "nml", "nrml", "n" 
    ],
    "bump":         [
        "bump", "b"
    ],
    "ao":           [
        "ao", "ambient", "occlusion", "occ", "amb"
    ],
    "metalness":    [
        "metallic", "metalness", "metal", "mtl", "met", "m"
    ],
    "refl_roughness":    [
        "roughness", "rough", "rgh", "r"
    ],
    "refl_weight":     [
        "specular", "spec", "s", "refl", "reflection"
    ],
    "glossiness":   [
        "glossiness", "gloss", "g"
    ],
    "opacity_color":      [
        "opacity", "opac", "alpha", "o", "a", "cutout" # 알파 마스크용 용어 추가
    ],
    "translucency": [
        "translucency", "transmission", "trans", 
        "sss", "subsurface", "scatter", "scattering" # SSS 관련 용어 보강
    ],
    "displacement": [
        "displacement", "disp", "dsp",
        "height", "h"
    ],
    "emission_color":     [
        "emissive", "emission", "emit", "illu", "illumination", "selfillum", "e"
    ]
}

def _split_into_components(fname):
    """
    Split filename into components for channel detection.
    Removes digits, replaces separators with '_', and splits by '_'.
    Does NOT split CamelCase.
    """
    # Remove extension
    fname = os.path.splitext(fname)[0]

    # Remove digits
    fname = "".join(i for i in fname if not i.isdigit())

    # Replace common separators with UNDERSCORE
    separators = [" ", ".", "-", "__", "--", "#"]
    for sep in separators:
        fname = fname.replace(sep, "_")

    components = fname.split("_")
    components = [c.lower() for c in components if c.strip()]
    return components

def GetTextureChannel(fname):
    """
    Determines the texture channel by analyzing filename components.
    Checks components in reverse order against known channel keywords.
    """
    components = _split_into_components(fname)
    
    # Check in reverse order
    for component in reversed(components):
        for channel, keywords in TEXTURE_CHANNELS.items():
            if component in keywords:
                return channel
            
    return None

def set_colorspace_raw(node):
    """
    Sets the colorspace of a texture node to RAW.
    """
    tex0_port = node.GetInputs().FindChild(PORT_RS_TEX_PATH)
    if tex0_port.IsValid():
        colorspace_port = tex0_port.FindChild("colorspace")
        if colorspace_port.IsValid():
            colorspace_port.SetPortValue(RS_INPUT_COLORSPACE_RAW)
