import c4d
import maxon
import os
import sys
import ctypes


# redshift_utils 경로 추가
current_dir = os.path.dirname(__file__)
sub_dir = os.path.join(current_dir, "mw_utils")
if sub_dir not in sys.path:
    sys.path.append(sub_dir)

import redshift_utils

# --- Plugin ID ---
PLUGIN_ID = 1067297

def ask_open_filenames(title="Select Files"):
    """
    Opens a native file dialog for multi-file selection.
    Supports Windows (via ctypes) and macOS (via osascript).
    """
    if sys.platform == 'win32':
        try:
            from ctypes import wintypes
        except ImportError:
            return []

        # Constants
        OFN_ALLOWMULTISELECT = 0x00000200
        OFN_EXPLORER = 0x00080000
        OFN_FILEMUSTEXIST = 0x00001000
        
        # Structure definition
        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM),
                ("lpfnHook", wintypes.LPVOID),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", wintypes.LPVOID),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]

        # Buffer for file names (64KB should be enough for many files)
        max_file_buffer = 65536 
        file_buffer = ctypes.create_unicode_buffer(max_file_buffer)
        
        # Filter: Display Name\0Pattern\0...
        filter_str = "Image Files\0*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.hdr;*.psd;*.tga\0All Files\0*.*\0\0"
        
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = 0 
        ofn.lpstrFilter = filter_str
        ofn.lpstrFile = ctypes.cast(file_buffer, wintypes.LPWSTR)
        ofn.nMaxFile = max_file_buffer
        ofn.lpstrTitle = title
        ofn.Flags = OFN_ALLOWMULTISELECT | OFN_EXPLORER | OFN_FILEMUSTEXIST
        
        if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            # Parse the result buffer
            files = []
            current_str = ""
            i = 0
            while i < max_file_buffer:
                char = file_buffer[i]
                if char == '\0':
                    if not current_str:
                        # Double null hit (empty string after a null) -> End of list
                        break
                    files.append(current_str)
                    current_str = ""
                else:
                    current_str += char
                i += 1
                
            if not files:
                return []
                
            if len(files) == 1:
                return files # Single file full path
            else:
                # Multi-select: First element is directory, rest are filenames
                directory = files[0]
                return [os.path.join(directory, f) for f in files[1:]]

    elif sys.platform == 'darwin':
        import subprocess
        # AppleScript logic for macOS
        script = '''
        try
            set fileList to choose file with prompt "%s" of type {"png", "jpg", "jpeg", "tif", "tiff", "exr", "hdr", "psd", "tga"} with multiple selections allowed
            set outString to ""
            repeat with aFile in fileList
                set outString to outString & POSIX path of aFile & "\\n"
            end repeat
            return outString
        on error
            return ""
        end try
        ''' % (title)
        
        try:
            # Run AppleScript via osascript
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                # Split lines and clean up
                paths = result.stdout.strip().split('\\n')
                return [p.strip() for p in paths if p.strip()]
        except Exception as e:
            print(f"macOS file dialog error: {e}")
            return []
            
    return []

class PBRRunnerDialog(c4d.gui.GeDialog):
    def __init__(self):
        self.texture_files = [] # initialize empty list

    def CreateLayout(self):
        self.SetTitle("PBR Texture Setup")
        if self.GroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0, "", 0):
            self.AddStaticText(1002, c4d.BFH_CENTER | c4d.BFH_SCALEFIT, name="Initializing Texture Loader...")
        self.GroupEnd()
        return True

    def InitValues(self):
        # 0 = Load Files, 1 = Create Nodes
        self.trigger_step = 0
        self.SetTimer(100) # Short delay to ensure dialog shows up before file picker
        return True

    def Command(self, id, msg):
        return True

    def Timer(self, msg):
        self.SetTimer(0)
        
        if self.trigger_step == 0:
            # Step 1: Load Files
            self.LoadTextureFiles()
            
            if self.texture_files:
                # If files loaded, wait a bit before processing (User's request)
                self.trigger_step = 1
                self.SetTimer(200) # Delay after loading
            else:
                # User cancelled or no files
                self.Close()
        
        elif self.trigger_step == 1:
            # Step 2: Create, Arrange, Close
            self.CreateMaterialNodes()
            
            # Restore Arrange Logic
            c4d.EventAdd() 
            c4d.CallCommand(465002311) # Arrange Selected Nodes
            c4d.EventAdd()
            
            self.Close()

    def LoadTextureFiles(self):
        # 0. Load Textures (Windows API Multi-Select)
        files = ask_open_filenames(title="Load Texture Files...")
        if not files:
            return

        # Logic: If 1 file selected, find others with same prefix
        if len(files) == 1:
            sel_path = files[0]
            dirname = os.path.dirname(sel_path)
            basename = os.path.basename(sel_path)

            # Use _split_into_components to get the prefix (first component)
            components = redshift_utils._split_into_components(basename)

            if components:
                target_prefix = components[0]
                # Extensions from filter_str (re-defined locally or access from outer scope if constant)
                valid_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".hdr", ".psd", ".tga"}
                
                found_files = []
                try:
                    for f in os.listdir(dirname):
                        f_path = os.path.join(dirname, f)
                        if not os.path.isfile(f_path):
                            continue

                        ext = os.path.splitext(f)[1].lower()
                        if ext in valid_exts:
                            f_comps = redshift_utils._split_into_components(f)
                            if f_comps and f_comps[0] == target_prefix:
                                found_files.append(f_path)
                    
                    if found_files:
                        files = found_files
                except Exception as e:
                    print(f"Directory scan error: {e}")
        
        self.texture_files = files
        count = len(self.texture_files)
        print(f"Loaded {count} texture files.")

    def CreateMaterialNodes(self):
        texture_files = self.texture_files
        
        if not texture_files:
            return

        # 1. Select Node Editor Redshift Material
        c4d.CallCommand(300001026) # Deselect All Materials
        c4d.CallCommand(465002328) # Select Active Material in Node Editor

        doc = c4d.documents.GetActiveDocument()
        mat = doc.GetActiveMaterial()
        if not mat:
            if c4d.gui.QuestionDialog("Please open the Material Node Editor to add textures.\nWould you like to create a new Material?"):
                c4d.CallCommand(1040264, 1012) # Materials > Redshift > Standard Material
                mat = doc.GetActiveMaterial()
                if not mat:
                    return
            else:
                return
        
        # Ensure Node Editor is Open and Focused
        c4d.CallCommand(465002211) # Node Editor
        
        nodeMaterial = mat.GetNodeMaterialReference()
        if not nodeMaterial.HasSpace(redshift_utils.ID_RS_NODESPACE):
            if c4d.gui.QuestionDialog("Please open the Material Node Editor to add textures.\nWould you like to create a new Material?"):
                c4d.CallCommand(1040264, 1012) # Materials > Redshift > Standard Material
                mat = doc.GetActiveMaterial()
                if not mat:
                    return
            else:
                return

        graph = nodeMaterial.GetGraph(redshift_utils.ID_RS_NODESPACE)
        if graph.IsNullValue():
            return

        # 2. Find Standard Material
        standard_mat, output_node = redshift_utils.find_standard_material_and_output(graph)
        if not output_node:
            c4d.gui.MessageDialog("Output Node (Redshift Material Output) not found!\nPlease select a valid Redshift Node Material.")
            return
            
        # If standard_mat is missing, we will create it inside the transaction.

        # 5. Process Textures - New Logic: Scan First, Then Connect
        
        # Data structure to hold detected MAPS: key=channel, value=list of (node, filename)
        detected_maps = {
            "base_color": [],
            "ao": [],
            "normal": [],
            "bump": [],
            "refl_roughness": [], # Roughness
            "glossiness": [],
            "metalness": [],
            "refl_weight": [], # Specular Weight
            "opacity_color": [],
            "emission_color": [],
            "displacement": [],
            "translucency": [],
            "other": []
        }
        
        created_nodes = [] # To select later

        with graph.BeginTransaction() as transaction:
            # Check/Create Standard Material
            if not standard_mat:
                c4d.gui.MessageDialog("Standard Material node not found.\nCreating a new Standard Material and connecting to Output.")
                standard_mat = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_STANDARD_MATERIAL)
                created_nodes.append(standard_mat)
                
                # Connect to Output Surface
                if output_node and standard_mat:
                    mat_out = standard_mat.GetOutputs().FindChild(redshift_utils.PORT_RS_STD_OUTCOLOR)
                    surf_in = output_node.GetInputs().FindChild(redshift_utils.PORT_RS_OUTPUT_SURFACE)
                    if mat_out and surf_in:
                        redshift_utils.remove_connections(output_node, redshift_utils.PORT_RS_OUTPUT_SURFACE)
                        mat_out.Connect(surf_in)

            # --- Phase 1: Create All Nodes & Classify ---
            for tex_path in texture_files:
                # Create Texture Node
                tex_node = redshift_utils.create_texture_node(graph, tex_path)
                created_nodes.append(tex_node)
                
                # Extract Info
                fname = os.path.basename(tex_path)
                channel = redshift_utils.GetTextureChannel(fname)
                
                # Set Node Name
                node_name = fname
                tex_node.SetValue("net.maxon.node.base.name", node_name)
                
                if channel:
                     if channel in detected_maps:
                         detected_maps[channel].append(tex_node)
                     else:
                         detected_maps["other"].append(tex_node)
                         
                     # Pre-set Raw Color Space for non-color data
                     if channel not in ["base_color", "emission_color", "opacity_color", "translucency"]:
                          redshift_utils.set_colorspace_raw(tex_node)
                else:
                    detected_maps["other"].append(tex_node)

            # --- Phase 2: Logic & Connections ---
            
            # Helper to get first node if exists
            def get_first_node(channel_key):
                nodes = detected_maps.get(channel_key)
                return nodes[0] if nodes else None

            # --- A. Base Color & AO ---
            tex_base = get_first_node("base_color")
            tex_ao = get_first_node("ao")
            
            if tex_base and tex_ao:
                # Multiply Logic
                mul_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_VECTOR_MULTIPLY)
                created_nodes.append(mul_node)
                
                # Connect Base -> Input 1
                base_out = tex_base.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mul_in1 = mul_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_VECTOR_MULTIPLY_INPUT1)
                if base_out and mul_in1: base_out.Connect(mul_in1)
                
                # Connect AO -> Input 2
                ao_out = tex_ao.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mul_in2 = mul_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_VECTOR_MULTIPLY_INPUT2)
                if ao_out and mul_in2: ao_out.Connect(mul_in2)
                
                # Create Color Correct Node
                cc_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_COLOR_CORRECT)
                created_nodes.append(cc_node)
                cc_node.SetValue("net.maxon.node.base.name", "Color Correct")

                # Connect Multiply -> Color Correct
                mul_out = mul_node.GetOutputs().FindChild(redshift_utils.PORT_RS_MATH_VECTOR_MULTIPLY_OUT)
                cc_in = cc_node.GetInputs().FindChild(redshift_utils.PORT_RS_COLOR_CORRECT_INPUT)
                if mul_out and cc_in: mul_out.Connect(cc_in)

                # Connect Color Correct -> Material Base Color
                cc_out = cc_node.GetOutputs().FindChild(redshift_utils.PORT_RS_COLOR_CORRECT_OUT)
                mat_base = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_BASE_COLOR)

                if cc_out and mat_base:
                    redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_BASE_COLOR)
                    cc_out.Connect(mat_base)
            
            elif tex_base:
                # Only Base Color
                # Create Color Correct Node
                cc_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_COLOR_CORRECT)
                created_nodes.append(cc_node)
                cc_node.SetValue("net.maxon.node.base.name", "Color Correct")

                # Connect Base -> Color Correct
                base_out = tex_base.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                cc_in = cc_node.GetInputs().FindChild(redshift_utils.PORT_RS_COLOR_CORRECT_INPUT)
                if base_out and cc_in: base_out.Connect(cc_in)

                # Connect Color Correct -> Material Base Color
                cc_out = cc_node.GetOutputs().FindChild(redshift_utils.PORT_RS_COLOR_CORRECT_OUT)
                mat_base = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_BASE_COLOR)
                
                if cc_out and mat_base:
                    redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_BASE_COLOR)
                    cc_out.Connect(mat_base)
            
            elif tex_ao:
                # Only AO (Create Multiply but don't connect to material)
                mul_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_VECTOR_MULTIPLY)
                created_nodes.append(mul_node)
                
                ao_out = tex_ao.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mul_in2 = mul_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_VECTOR_MULTIPLY_INPUT2)
                if ao_out and mul_in2: ao_out.Connect(mul_in2)


            # --- B. Normal & Bump ---
            tex_normal = get_first_node("normal")
            tex_bump = get_first_node("bump")
            
            chosen_bump_node = None
            is_normal_map = False
            
            if tex_normal and tex_bump:
                # Conflict! Ask user.
                # Yes = Normal, No = Bump
                
                result = c4d.gui.QuestionDialog("Normal and Bump maps detected.\nUse Normal Map? (Yes = Normal, No = Bump)")
                if result:
                    chosen_bump_node = tex_normal
                    is_normal_map = True
                else:
                    chosen_bump_node = tex_bump
                    is_normal_map = False
            elif tex_normal:
                chosen_bump_node = tex_normal
                is_normal_map = True
            elif tex_bump:
                chosen_bump_node = tex_bump
                is_normal_map = False
                
            if chosen_bump_node:
                # Create Bump Node
                bump_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_BUMPMAP)
                created_nodes.append(bump_node)
                
                # Set Type
                bump_type_port = bump_node.GetInputs().FindChild(redshift_utils.PORT_RS_BUMP_TYPE)
                if bump_type_port:
                    # 1 = Tangent-Space Normal, 0 = Height Field
                    bump_type_port.SetPortValue(1 if is_normal_map else 0)
                
                # Connect Texture -> Bump Node
                tex_out = chosen_bump_node.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                bump_in = bump_node.GetInputs().FindChild(redshift_utils.PORT_RS_BUMP_INPUT)
                if tex_out and bump_in: tex_out.Connect(bump_in)
                
                # Connect Bump Node -> Material
                bump_out = bump_node.GetOutputs().FindChild(redshift_utils.PORT_RS_BUMP_OUT)
                mat_bump = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_BUMP_INPUT)
                if bump_out and mat_bump:
                    redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_BUMP_INPUT)
                    bump_out.Connect(mat_bump)


            # --- C. Roughness & Glossiness ---
            tex_rough = get_first_node("refl_roughness")
            tex_gloss = get_first_node("glossiness")
            
            target_rough_node = None
            use_invert = False
            
            if tex_rough and tex_gloss:
                # Conflict!
                # Yes = Roughness, No = Glossiness
                result = c4d.gui.QuestionDialog("Roughness and Glossiness maps detected.\nUse Roughness Map? (Yes = Roughness, No = Glossiness)")
                if result:
                    target_rough_node = tex_rough
                    use_invert = False
                else:
                    target_rough_node = tex_gloss
                    use_invert = True
            elif tex_rough:
                target_rough_node = tex_rough
                use_invert = False
            elif tex_gloss:
                target_rough_node = tex_gloss
                use_invert = True
            
            if target_rough_node:
                tex_out = target_rough_node.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mat_rough = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_ROUGHNESS)
                
                if use_invert:
                    # Glossiness -> Invert -> Roughness
                    inv_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_MATH_INVERT)
                    created_nodes.append(inv_node)
                    inv_node.SetValue("net.maxon.node.base.name", "Invert Glossiness")
                    
                    inv_in = inv_node.GetInputs().FindChild(redshift_utils.PORT_RS_MATH_INVERT_INPUT)
                    if tex_out and inv_in: tex_out.Connect(inv_in)
                    
                    inv_out = inv_node.GetOutputs().FindChild(redshift_utils.PORT_RS_MATH_INVERT_OUTPUT)
                    if not inv_out: inv_out = inv_node.GetOutputs().FindChild("outColor") 

                    if inv_out and mat_rough:
                        redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_ROUGHNESS)
                        inv_out.Connect(mat_rough)
                else:
                    # Direct Roughness
                    if tex_out and mat_rough:
                        redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_ROUGHNESS)
                        tex_out.Connect(mat_rough)


            # --- D. Other Simple Channels ---
            
            # Metalness
            tex_metal = get_first_node("metalness")
            if tex_metal:
                tex_out = tex_metal.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mat_metal = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_METALNESS)
                if tex_out and mat_metal:
                    redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_METALNESS)
                    tex_out.Connect(mat_metal)

            # Specular Weight
            tex_spec = get_first_node("refl_weight")
            if tex_spec:
                tex_out = tex_spec.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mat_spec = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_SPECULAR)
                if tex_out and mat_spec:
                     redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_SPECULAR)
                     tex_out.Connect(mat_spec)
            
            # Opacity
            tex_opac = get_first_node("opacity_color")
            if tex_opac:
                tex_out = tex_opac.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mat_opac = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_OPACITY)
                if tex_out and mat_opac:
                     redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_OPACITY)
                     tex_out.Connect(mat_opac)

            # Emission
            tex_emiss = get_first_node("emission_color")
            if tex_emiss:
                tex_out = tex_emiss.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                mat_emiss = standard_mat.GetInputs().FindChild(redshift_utils.PORT_RS_STD_EMISSION)
                if tex_out and mat_emiss:
                     redshift_utils.remove_connections(standard_mat, redshift_utils.PORT_RS_STD_EMISSION)
                     tex_out.Connect(mat_emiss)
            
            # Displacement
            tex_disp = get_first_node("displacement")
            if tex_disp and output_node:
                disp_node = graph.AddChild(maxon.Id(), redshift_utils.ID_RS_DISPLACEMENT)
                created_nodes.append(disp_node)
                disp_node.SetValue("net.maxon.node.base.name", "Displacement")
                
                # Tex -> Disp
                tex_out = tex_disp.GetOutputs().FindChild(redshift_utils.PORT_RS_TEX_OUTCOLOR)
                disp_in = disp_node.GetInputs().FindChild(redshift_utils.PORT_RS_DISP_TEXMAP)
                if tex_out and disp_in: tex_out.Connect(disp_in)
                
                # Disp -> Output
                disp_out = disp_node.GetOutputs().FindChild(redshift_utils.PORT_RS_DISP_OUT)
                out_disp_in = output_node.GetInputs().FindChild(redshift_utils.PORT_RS_OUTPUT_DISPLACEMENT)
                if disp_out and out_disp_in:
                    redshift_utils.remove_connections(output_node, redshift_utils.PORT_RS_OUTPUT_DISPLACEMENT)
                    disp_out.Connect(out_disp_in)

            
            # --- Phase 3: Selection & Arrange ---
            maxon.GraphModelHelper.DeselectAll(graph, maxon.NODE_KIND.NODE)
            
            for node in created_nodes:
                if node.IsValid():
                    maxon.GraphModelHelper.SelectNode(node)
                    
            if standard_mat.IsValid(): maxon.GraphModelHelper.SelectNode(standard_mat)
            if output_node.IsValid(): maxon.GraphModelHelper.SelectNode(output_node)

            transaction.Commit()
        
        c4d.EventAdd()

class CreatePBRMaterialCommand(c4d.plugins.CommandData):
    # Hold reference to dialog to prevent garbage collection
    dialog = None

    def Execute(self, doc):
        # Create dialog instance
        self.dialog = PBRRunnerDialog()
        # Open asynchronously - this will run InitValues -> Timer -> RunPBRSetup -> Close
        return self.dialog.Open(c4d.DLG_TYPE_ASYNC_POPUPEDIT, pluginid=PLUGIN_ID, defaultw=0, defaulth=0)

if __name__ == "__main__":
    icon_path = os.path.join(os.path.dirname(__file__), "Auto_Connect_PBR_Textures.tif")
    bmp = c4d.bitmaps.BaseBitmap()
    if os.path.exists(icon_path):
        bmp.InitWith(icon_path)
    else:
        bmp = None

    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str="Auto Connect PBR Textures...",
        info=0,
        icon=bmp,
        help="Loads texture files and automatically connects them to the material.",
        dat=CreatePBRMaterialCommand()
    )
