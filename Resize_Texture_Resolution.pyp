import c4d
import maxon
import os
import sys
import shutil
import re

# Add utils path
current_dir = os.path.dirname(__file__)
sub_dir = os.path.join(current_dir, "mw_utils")
if sub_dir not in sys.path:
    sys.path.append(sub_dir)

# Add dependencies path
dep_dir = os.path.join(current_dir, "dependencies")
if dep_dir not in sys.path:
    sys.path.append(dep_dir)

# Try to import PIL
PIL_ERROR_MSG = None
try:
    from PIL import Image
    print("PIL loaded successfully!")
except ImportError as e:
    Image = None
    PIL_ERROR_MSG = str(e)
    print(f"Failed to import PIL: {e}")
import redshift_utils

PLUGIN_ID = 1067303

ID_TREEVIEW = 1000
ID_BTN_ORIGINAL = 1001
ID_BTN_RESIZE = 1002
ID_MENU_OPEN_TEX = 2001
ID_MENU_DELETE_UNUSED = 2002

def ResolveTexturePath(doc, path_str):
    """Resolves a texture path to an absolute path."""
    if not path_str or not doc:
        return None
    
    # Already absolute?
    if os.path.isabs(path_str):
        return path_str if os.path.exists(path_str) else None

    # Resolve relative
    doc_path = doc.GetDocumentPath()
    if not doc_path:
        return None
        
    cand1 = os.path.join(doc_path, path_str)
    if os.path.exists(cand1):
        return cand1
        
    cand2 = os.path.join(doc_path, "tex", path_str)
    if os.path.exists(cand2):
        return cand2
        
    return None

def GetRootTextureName(filename):
    """Strips sequence of '_Low' suffixes to find the root name."""
    name, ext = os.path.splitext(filename)
    while name.endswith("_Low"):
        name = name[:-4]
    return name, ext

class TextureObject(object):
    """Stores data for a single row in the TreeView."""
    def __init__(self, node, path, filename, resolution_str, size_str, is_selected=False):
        self.node = node
        self.path = path
        self.filename = filename
        self.resolution_str = resolution_str
        self.size_str = size_str
        self.selected = is_selected

    @property
    def IsSelected(self):
        """Returns selection state"""
        return self.selected

    def Select(self):
        """Select the item"""
        self.selected = True

    def Deselect(self):
        """Deselect the item"""
        self.selected = False

    def __repr__(self):
        return f"TextureObject({self.filename})"

    def __str__(self):
        return self.filename

class TextureTreeViewFunctions(c4d.gui.TreeViewFunctions):
    """Handles rendering and interaction for the TreeView."""

    def __init__(self, texture_list):
        self.texture_list = texture_list
        # Color settings
        self.color_item_normal = c4d.COLOR_TEXT
        self.color_item_selected = c4d.COLOR_TEXT_SELECTED
        self.color_background_normal = c4d.COLOR_BG_DARK2
        self.color_background_alternate = c4d.COLOR_BG_DARK1
        self.color_background_selected = c4d.COLOR_BG_HIGHLIGHT
        
        self.col_padding = 10
        self.text_offset_x = 5

    def SetTextureList(self, texture_list):
        self.texture_list = texture_list

    def GetFirst(self, root, userdata):
        if not self.texture_list:
            return None
        return self.texture_list[0]

    def GetDown(self, root, userdata, obj):
        return None

    def GetNext(self, root, userdata, obj):
        try:
            idx = self.texture_list.index(obj)
            if idx < len(self.texture_list) - 1:
                return self.texture_list[idx + 1]
        except ValueError:
            return None
        return None

    def GetPred(self, root, userdata, obj):
        try:
            idx = self.texture_list.index(obj)
            if idx > 0:
                return self.texture_list[idx - 1]
        except ValueError:
            return None
        return None

    def IsSelected(self, root, userdata, obj):
        return obj.IsSelected

    def Select(self, root, userdata, obj, mode):
        # Update internal state and Graph Selection
        
        graph = None
        if obj and obj.node.IsValid():
            graph = obj.node.GetGraph()
        elif self.texture_list:
             # Try to find a valid node to get the graph
             for t in self.texture_list:
                 if t.node.IsValid():
                     graph = t.node.GetGraph()
                     break
        
        if not graph:
             return

        with graph.BeginTransaction() as transaction:
            if mode == c4d.SELECTION_NEW:
                # Deselect all in internal list
                maxon.GraphModelHelper.DeselectAll(graph, maxon.NODE_KIND.NODE)

                # Select target
                obj.Select()
                if obj.node.IsValid():
                    maxon.GraphModelHelper.SelectNode(obj.node)
                    
            elif mode == c4d.SELECTION_ADD:
                obj.Select()
                if obj.node.IsValid():
                    maxon.GraphModelHelper.SelectNode(obj.node)
                    
            elif mode == c4d.SELECTION_SUB:
                obj.Deselect()
                if obj.node.IsValid():
                    maxon.GraphModelHelper.DeselectNode(obj.node)
            
            transaction.Commit()
        
        # Trigger Event to update Node Editor
        c4d.EventAdd()

    # def GetName(self, root, userdata, obj):
    #     return str(obj)
    
    # def SetName(self, root, userdata, obj, name):
    #     pass

    def GetId(self, root, userdata, obj):
        return hash(obj)

    def GetColumnWidth(self, root, userdata, obj, col, area):
        if col == 1: # Filename
            if obj:
                 return area.DrawGetTextWidth(obj.filename) + self.col_padding
            return 100
        elif col == 2: # Resolution
            if obj:
                 return area.DrawGetTextWidth(obj.resolution_str) + self.col_padding
            return 50
        elif col == 3: # File Size
            if obj:
                 return area.DrawGetTextWidth(obj.size_str) + self.col_padding
            return 50
        return 50

    def GetHeaderColumnWidth(self, root, userdata, col, area):
         return self.GetColumnWidth(root, userdata, None, col, area)

    def DrawCell(self, root, userdata, obj, col, drawinfo, bgColor):
        if not obj: return
        
        canvas = drawinfo["frame"]
        xpos = drawinfo["xpos"]
        ypos = drawinfo["ypos"]
        
        text = ""
        if col == 1:
            text = obj.filename
        elif col == 2:
            text = obj.resolution_str
        elif col == 3:
            text = obj.size_str
            
        if obj.IsSelected:
            txtColorDict = canvas.GetColorRGB(self.color_item_selected)
        else:
            txtColorDict = canvas.GetColorRGB(self.color_item_normal)
            
        txtColorVector = c4d.Vector(
            txtColorDict["r"] / 255.0,
            txtColorDict["g"] / 255.0,
            txtColorDict["b"] / 255.0
        )
        
        canvas.DrawSetTextCol(txtColorVector, bgColor)
        canvas.DrawText(text, xpos + self.text_offset_x, ypos + 2)

    def GetLineHeight(self, root, userdata, obj, col, area):
        return 18 

    def IsResizeColAllowed(self, root, userdata, lColID):
        return True

    def IsTristate(self, root, userdata):
        return False

    def IsOpened(self, root, userdata, obj):
        return False

    def Open(self, root, userdata, obj, onoff):
        pass

    def GetDragType(self, root, userdata, obj):
        return c4d.NOTOK

    def DragStart(self, root, userdata, obj):
        return c4d.NOTOK

    def AcceptDragObject(self, root, userdata, obj, dragtype, dragobject):
        return c4d.INSERT_NONE

    def InsertObject(self, root, userdata, obj, dragtype, dragobject, insertmode, bCopy):
        pass

    def DoubleClick(self, root, userdata, obj, col, mouseinfo):
        return False

    def DeletePressed(self, root, userdata):
        pass

    def GetBackgroundColor(self, root, userdata, obj, line, col):
        if not obj: return None
        if obj.IsSelected:
            return self.color_background_selected
        return None

class ResizeTextureDialog(c4d.gui.GeDialog):
    """Main Dialog for the plugin."""

    def __init__(self):
        self.treegui = None
        self.texture_list = []
        self.tree_funcs = TextureTreeViewFunctions([]) # Initialize with empty list

    def CreateLayout(self):
        self.SetTitle("Resize Texture Resolution")
        
        # Menu
        self.MenuFlushAll()
        self.MenuSubBegin("Options")
        self.MenuAddString(ID_MENU_OPEN_TEX, "Open tex Folder...")
        self.MenuAddString(ID_MENU_DELETE_UNUSED, "Delete Unused Textures(Selected Only)")
        self.MenuSubEnd()
        self.MenuFinished()

        # TreeView
        settings = c4d.BaseContainer()
        settings.SetBool(c4d.TREEVIEW_BORDER, True)
        settings.SetBool(c4d.TREEVIEW_HAS_HEADER, True)
        settings.SetBool(c4d.TREEVIEW_HIDE_LINES, False)
        settings.SetBool(c4d.TREEVIEW_MOVE_COLUMN, True)
        settings.SetBool(c4d.TREEVIEW_RESIZE_HEADER, True)
        settings.SetBool(c4d.TREEVIEW_FIXED_LAYOUT, True)
        settings.SetBool(c4d.TREEVIEW_ALTERNATE_BG, True)
        settings.SetBool(c4d.TREEVIEW_NOENTERRENAME, True)
        settings.SetBool(c4d.TREEVIEW_NO_DELETE, True)
        settings.SetBool(c4d.TREEVIEW_NO_BACK_DELETE, True)

        self.treegui = self.AddCustomGui(ID_TREEVIEW, c4d.CUSTOMGUI_TREEVIEW, "", c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 0, 0, settings)

        # Buttons
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0, "", 0)
        self.GroupBorderSpace(5, 5, 5, 5) # Added Border Space
        self.AddButton(ID_BTN_ORIGINAL, c4d.BFH_SCALEFIT, 0, 0, "Original")
        self.AddButton(ID_BTN_RESIZE, c4d.BFH_SCALEFIT, 0, 0, "Resize to 50%")
        self.GroupEnd()

        if self.treegui:
            # Set Root ONCE. Use self.treegui as a dummy root object.
            # The Functions.GetFirst will simply return the first item from the list, ignoring the root argument.
            self.treegui.SetRoot(self.treegui, self.tree_funcs, None)

        return True

    def InitValues(self):
        # Setup Columns
        layout = c4d.BaseContainer()
        
        # Column IDs
        COL_FILENAME = 1
        COL_RESOLUTION = 2
        COL_SIZE = 3
        
        # Column 1: Filename
        layout.SetLong(COL_FILENAME, c4d.LV_USER)
        
        # Column 2: Resolution
        layout.SetLong(COL_RESOLUTION, c4d.LV_USER)

        # Column 3: File Size
        layout.SetLong(COL_SIZE, c4d.LV_USER)
        
        self.treegui.SetLayout(3, layout)
        
        # Explicitly set headers (redundant but safe)
        self.treegui.SetHeaderText(COL_FILENAME, "Filename")
        self.treegui.SetHeaderText(COL_RESOLUTION, "Resolution")
        self.treegui.SetHeaderText(COL_SIZE, "File Size")
        
        # Refresh Data
        self.RefreshTextureList()
        return True

    def CoreMessage(self, id, msg):
        if id == c4d.EVMSG_CHANGE:
            self.RefreshTextureList()
        return c4d.gui.GeDialog.CoreMessage(self, id, msg)

    def RefreshTextureList(self):
        doc = c4d.documents.GetActiveDocument()
        if not doc: return

        # Get Materials
        mat = doc.GetActiveMaterials()
        if not mat: return
        mat = mat[0]

        nodes_found = []
        
        nodeMaterial = mat.GetNodeMaterialReference()
        if nodeMaterial.HasSpace(redshift_utils.ID_RS_NODESPACE):
            graph = nodeMaterial.GetGraph(redshift_utils.ID_RS_NODESPACE)
            if not graph.IsNullValue():
                # 1. Collect ALL Texture Nodes
                root = graph.GetViewRoot()
                children = []
                root.GetChildren(children, maxon.NODE_KIND.NODE)
                
                all_texture_nodes = []
                for node in children:
                    if not node.IsValid(): continue
                    try:
                        asset_id = node.GetValue("net.maxon.node.attribute.assetid")[0]
                        if asset_id == redshift_utils.ID_RS_TEXTURESAMPLER:
                            all_texture_nodes.append(node)
                    except:
                        pass

                # 2. Identify Selected Nodes
                selected_nodes_list = []
                maxon.GraphModelHelper.GetSelectedNodes(graph, maxon.NODE_KIND.NODE, lambda node: selected_nodes_list.append(node) or True)
                
                nodes_found = all_texture_nodes

        # Build Texture Objects
        new_list = []
        for node in nodes_found:
            # Check selection
            is_selected = False
            for sel_node in selected_nodes_list:
                if sel_node == node:
                    is_selected = True
                    break

            path_port = node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_PATH).FindChild("path")
            current_path = ""
            if path_port.IsValid():
                val = path_port.GetPortValue()
                if val:
                    current_path = str(val) if not isinstance(val, maxon.Url) else val.GetSystemPath()
            
            # Use Helper
            abs_path = ResolveTexturePath(doc, current_path)
            
            # Default values
            filename = os.path.basename(current_path) if current_path else "No Path"
            res_str = "Unknown"
            size_str = "Unknown"

            # Load validation info if file exists
            if abs_path:
                # Calculate file size
                try:
                    size_bytes = os.path.getsize(abs_path)
                    size_mb = size_bytes / (1024 * 1024)
                    size_str = f"{size_mb:.2f} MB"
                except Exception as e:
                    print(f"Error getting file size for {filename}: {e}")
                    size_str = "Error"

                res_found = False
                if Image:
                    try:
                        with Image.open(abs_path) as img:
                            res_str = f"{img.width}x{img.height}"
                            res_found = True
                    except Exception as e:
                        print(f"PIL failed for {filename}: {e}")
                
                if not res_found:
                    # Fallback removed as per Refactoring Plan (EXR/HDR treated as Unsupported)
                    filename = "Unsupported Format"
                    res_str = "Load Failed"
                    if not Image:
                            res_str = "PIL Missing"
            
            new_list.append(TextureObject(node, current_path, filename, res_str, size_str, is_selected))

        # Update data in existing functions object
        self.texture_list = new_list
        self.tree_funcs.SetTextureList(self.texture_list)
        self.treegui.Refresh()

    def Command(self, id, msg):
        if id == ID_BTN_RESIZE:
            self.ResizeTo50percent()
        elif id == ID_BTN_ORIGINAL:
            self.Original()
        elif id == ID_MENU_OPEN_TEX:
            self.OpenTexFolder()
        elif id == ID_MENU_DELETE_UNUSED:
            self.DeleteUnusedResizedTextures()
        return True

    def ResizeTo50percent(self):
        doc = c4d.documents.GetActiveDocument()
        doc_path = doc.GetDocumentPath()
        if not doc_path:
             c4d.gui.MessageDialog("Please save project first.")
             return
             
        tex_folder = os.path.join(doc_path, "tex")
        if not os.path.exists(tex_folder):
            try:
                os.makedirs(tex_folder)
            except:
                pass

        selected_objs = [obj for obj in self.texture_list if obj.selected]
        if not selected_objs:
             selected_objs = self.texture_list # Process ALL if none selected

        if not selected_objs:
             c4d.gui.MessageDialog("No textures to resize.")
             return

        processed = 0
        
        for obj in selected_objs:
             # Use Helper
             abs_path = ResolveTexturePath(doc, obj.path)

             if not abs_path:
                 print(f"File not found: {obj.path}")
                 continue

             filename = os.path.basename(abs_path)
             name, ext = os.path.splitext(filename)
             
             new_filename = f"{name}_Low{ext}"
             target_path = os.path.join(tex_folder, new_filename)
             
             # Copy original backup
             original_in_tex = os.path.join(tex_folder, filename)
             if os.path.abspath(abs_path) != os.path.abspath(original_in_tex):
                 if not os.path.exists(original_in_tex):
                     try:
                         shutil.copy2(abs_path, original_in_tex)
                         print(f"Copied original to: {original_in_tex}")
                     except Exception as e:
                         print(f"Failed to copy original: {e}")

             try:
                 # Check if target already exists
                 if os.path.exists(target_path):
                     print(f"Resized file already exists, skipping resize: {target_path}")
                 else:
                     resize_and_strip_metadata(abs_path, target_path)
                 
                 # Set Port
                 graph = obj.node.GetGraph()
                 with graph.BeginTransaction() as t:
                     path_port = obj.node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_PATH).FindChild("path")
                     path_port.SetPortValue(target_path)
                     t.Commit()
                 
                 processed += 1
             except Exception as e:
                 print(f"Failed to resize {filename}: {e}")

        if processed > 0:
            self.RefreshTextureList()
            c4d.EventAdd()

    def Original(self):
        doc = c4d.documents.GetActiveDocument()
        
        selected_objs = [obj for obj in self.texture_list if obj.selected]
        if not selected_objs:
             selected_objs = self.texture_list
             
        processed = 0
        
        for obj in selected_objs:
            current_path = obj.path
            filename = os.path.basename(current_path)
            
            # Use Helper to find root name
            base_name, ext = GetRootTextureName(filename)
            original_name = base_name + ext
                
            # Assume original is in same dir as current (often 'tex') or doc root
            # Only change the name in the path
            dir_path = os.path.dirname(current_path)
            new_path_str = os.path.join(dir_path, original_name)
            
            # Update Graph
            graph = obj.node.GetGraph()
            with graph.BeginTransaction() as t:
                 path_port = obj.node.GetInputs().FindChild(redshift_utils.PORT_RS_TEX_PATH).FindChild("path")
                 path_port.SetPortValue(new_path_str)
                 t.Commit()
            processed += 1

        if processed > 0:
            self.RefreshTextureList()
            c4d.EventAdd()

    def OpenTexFolder(self):
        doc = c4d.documents.GetActiveDocument()
        if not doc: return
        doc_path = doc.GetDocumentPath()
        if not doc_path: return
        
        tex_folder = os.path.join(doc_path, "tex")
        if not os.path.exists(tex_folder):
            # Fallback to doc path if tex doesn't exist
            tex_folder = doc_path

        # Use os.startfile on Windows to open the folder content itself
        if sys.platform == 'win32':
            try:
                os.startfile(tex_folder)
            except Exception as e:
                print(f"Failed to open folder: {e}")
                c4d.storage.ShowInFinder(tex_folder)
        else:
            c4d.storage.ShowInFinder(tex_folder)


    def DeleteUnusedResizedTextures(self):
        import re
        
        doc = c4d.documents.GetActiveDocument()
        doc_path = doc.GetDocumentPath()
        
        selected_objs = [obj for obj in self.texture_list if obj.selected]
        if not selected_objs:
             c4d.gui.MessageDialog("No textures selected.")
             return
             
        # Confirm dialog
        if not c4d.gui.QuestionDialog("Delete unused resized textures for selected textures?\nThis cannot be undone."):
            return

        deleted_files = []
        
        for obj in selected_objs:
            current_path = obj.path
            if not current_path: continue
            
            # Use Helper
            abs_path = ResolveTexturePath(doc, current_path)
            
            # Need a valid directory path
            if not abs_path:
                continue
                
            dir_path = os.path.dirname(abs_path)
            filename = os.path.basename(abs_path)
            
            # Use Helper
            base_name, ext = GetRootTextureName(filename)
            
            # 2. Scan directory
            try:
                files = os.listdir(dir_path)
            except Exception as e:
                print(f"Failed to list directory {dir_path}: {e}")
                continue
                
            # Regex pattern: base_name + at least one "_Low" + ext
            pattern_str = f"^{re.escape(base_name)}(_Low)+{re.escape(ext)}$"
            pattern = re.compile(pattern_str, re.IGNORECASE)
            
            for f in files:
                if pattern.match(f):
                    full_path = os.path.join(dir_path, f)
                    
                    # Verify it's not the currently used file
                    if os.path.abspath(full_path).lower() != os.path.abspath(abs_path).lower():
                        try:
                            os.remove(full_path)
                            print(f"Deleted unused: {f}")
                            deleted_files.append(f)
                        except Exception as e:
                            print(f"Failed to delete {f}: {e}")
        
        if len(deleted_files) > 0:
            msg = f"Deleted {len(deleted_files)} unused files:\n\n"
            msg += "\n".join(deleted_files)
            c4d.gui.MessageDialog(msg)
        else:
            c4d.gui.MessageDialog("No unused resized textures found to delete.")


def resize_and_strip_metadata(input_path, output_path):
    # EXR / HDR Check -> Unsupported
    ext = os.path.splitext(input_path)[1].lower()
    if ext in ['.exr', '.hdr']:
        raise Exception(f"Unsupported format: {ext}")

    if not Image:
        raise ImportError("PIL not loaded")
    
    with Image.open(input_path) as img:
        new_size = (img.width // 2, img.height // 2)
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Strip metadata
        clean_img = Image.new(resized_img.mode, resized_img.size)
        clean_img.putdata(list(resized_img.getdata()))
        
        ext = os.path.splitext(output_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            clean_img.save(output_path, "JPEG", optimize=True, quality=85)
        elif ext in ['.png']:
             clean_img.save(output_path, "PNG", optimize=True)
        elif ext in ['.tif', '.tiff']:
             clean_img.save(output_path, "TIFF")
        else:
             clean_img.save(output_path)


class ResizeTextureCommand(c4d.plugins.CommandData):
    dialog = None

    def Execute(self, doc):
        if self.dialog is None:
            self.dialog = ResizeTextureDialog()
        
        # Open NON-Modally
        return self.dialog.Open(dlgtype=c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=500, defaulth=300)

    def RestoreLayout(self, sec_ref):
        if self.dialog is None:
            self.dialog = ResizeTextureDialog()
        return self.dialog.Restore(PLUGIN_ID, sec_ref)

if __name__ == "__main__":
    bmp = None
    c4d.plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str="Resize Texture Resolution...",
        info=0,
        icon=bmp,
        help="Manage texture resolutions",
        dat=ResizeTextureCommand()
    )
