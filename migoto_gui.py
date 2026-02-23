"""
3DMigoto Converter GUI - VERSION ULTIME
Visionneuse 3D integree + export OBJ/glTF/FBX
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import os, sys, threading, subprocess, struct, math, json

# ── Couleurs ──────────────────────────────────────────────────────────────────
BG      = "#0d0d1a"
BG2     = "#13132a"
BG3     = "#1a1a3a"
PANEL   = "#111128"
ACCENT  = "#7c5cfc"
ACCENT2 = "#e94560"
GREEN   = "#00e5a0"
YELLOW  = "#ffd700"
TEXT    = "#e8e8f0"
TEXT2   = "#7070a0"
BORDER  = "#2a2a50"
MESH_C  = "#7c5cfc"
GRID_C  = "#1e1e3a"


# =============================================================================
# MINI VISIONNEUSE 3D (Canvas tkinter - projection perspective)
# =============================================================================

class Viewer3D(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, **kw)
        self.meshes     = []   # liste de {'verts':[(x,y,z)], 'tris':[(a,b,c)], 'color':str}
        self.rot_x      = 20.0
        self.rot_y      = 0.0
        self.zoom       = 1.0
        self.pan_x      = 0.0
        self.pan_y      = 0.0
        self._drag      = None
        self._last      = None
        self.bind('<ButtonPress-1>',   self._on_press)
        self.bind('<B1-Motion>',       self._on_drag)
        self.bind('<ButtonPress-3>',   self._on_rpress)
        self.bind('<B3-Motion>',       self._on_rdrag)
        self.bind('<MouseWheel>',      self._on_wheel)
        self.bind('<Configure>',       lambda e: self._draw())
        self._colors = [ACCENT, ACCENT2, GREEN, YELLOW,
                        "#ff8c42","#44cfcb","#f038ff","#00b4d8"]

    def load_obj(self, path):
        """Charge un fichier OBJ dans la visionneuse."""
        self.meshes = []
        verts, tris = [], []
        try:
            with open(path, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('o ') or line.startswith('g '):
                        if tris:
                            self.meshes.append({'verts': verts, 'tris': tris,
                                                'color': self._colors[len(self.meshes)%len(self._colors)]})
                            verts, tris = list(verts), []
                    elif line.startswith('v '):
                        p = line.split()
                        verts.append((float(p[1]), float(p[2]), float(p[3])))
                    elif line.startswith('f '):
                        p = line.split()[1:]
                        def idx(s): return int(s.split('/')[0]) - 1
                        if len(p) >= 3:
                            tris.append((idx(p[0]), idx(p[1]), idx(p[2])))
            if tris:
                self.meshes.append({'verts': verts, 'tris': tris,
                                    'color': self._colors[len(self.meshes)%len(self._colors)]})
        except Exception as e:
            print(f"Viewer: {e}")

        # Normalise
        all_v = [v for m in self.meshes for v in m['verts']]
        if all_v:
            cx = sum(v[0] for v in all_v)/len(all_v)
            cy = sum(v[1] for v in all_v)/len(all_v)
            cz = sum(v[2] for v in all_v)/len(all_v)
            maxd = max(abs(v[i]-[cx,cy,cz][i]) for v in all_v for i in range(3)) or 1
            scale = 1.0/maxd
            for m in self.meshes:
                m['verts'] = [((v[0]-cx)*scale, (v[1]-cy)*scale, (v[2]-cz)*scale)
                              for v in m['verts']]
        self.rot_x, self.rot_y = 20.0, 0.0
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self._draw()

    def _project(self, x, y, z, w, h, fov=600):
        # Rotation X
        rx = math.radians(self.rot_x)
        y2 = y*math.cos(rx) - z*math.sin(rx)
        z2 = y*math.sin(rx) + z*math.cos(rx)
        # Rotation Y
        ry = math.radians(self.rot_y)
        x2 = x*math.cos(ry) + z2*math.sin(ry)
        z3 = -x*math.sin(ry) + z2*math.cos(ry)
        # Projection perspective
        d  = fov * self.zoom
        pz = z3 + 3.0
        if pz < 0.01: pz = 0.01
        px = x2*d/pz + w/2 + self.pan_x
        py = -y2*d/pz + h/2 + self.pan_y
        return px, py, pz

    def _draw(self):
        self.delete('all')
        w = self.winfo_width()  or 400
        h = self.winfo_height() or 400

        # Grille de fond
        for i in range(0, w, 40):
            self.create_line(i, 0, i, h, fill=GRID_C)
        for i in range(0, h, 40):
            self.create_line(0, i, w, i, fill=GRID_C)

        if not self.meshes:
            self.create_text(w//2, h//2, text="Aucun mesh charge\nConvertis d'abord un mod",
                             fill=TEXT2, font=("Segoe UI",12), justify='center')
            return

        # Collecte tous les triangles avec profondeur
        all_tris = []
        for mesh in self.meshes:
            verts = mesh['verts']
            color = mesh['color']
            for a, b, c in mesh['tris']:
                if a>=len(verts) or b>=len(verts) or c>=len(verts): continue
                va, vb, vc = verts[a], verts[b], verts[c]
                pax,pay,paz = self._project(va[0],va[1],va[2],w,h)
                pbx,pby,pbz = self._project(vb[0],vb[1],vb[2],w,h)
                pcx,pcy,pcz = self._project(vc[0],vc[1],vc[2],w,h)
                depth = (paz+pbz+pcz)/3
                # Normale pour backface culling + shading
                ex,ey = pbx-pax, pby-pay
                fx,fy = pcx-pax, pcy-pay
                cross = ex*fy - ey*fx
                if cross > 0: continue  # backface
                # Shading simple
                n3d = ((vb[0]-va[0])*(vc[1]-va[1])-(vb[1]-va[1])*(vc[0]-va[0]),
                       (vb[1]-va[1])*(vc[2]-va[2])-(vb[2]-va[2])*(vc[1]-va[1]),
                       (vb[2]-va[2])*(vc[0]-va[0])-(vb[0]-va[0])*(vc[2]-va[2]))
                nlen = math.sqrt(sum(x*x for x in n3d)) or 1
                n3d  = tuple(x/nlen for x in n3d)
                light = (0.5, 0.8, 0.3)
                diff  = max(0, sum(n3d[i]*light[i] for i in range(3)))
                shade = 0.2 + 0.8*diff
                # Applique shade sur la couleur hex
                r = int(int(color[1:3],16)*shade)
                g = int(int(color[3:5],16)*shade)
                b_ = int(int(color[5:7],16)*shade)
                c_str = f'#{min(r,255):02x}{min(g,255):02x}{min(b_,255):02x}'
                all_tris.append((depth, pax,pay,pbx,pby,pcx,pcy,c_str))

        # Trie par profondeur (painter's algorithm)
        all_tris.sort(key=lambda x: -x[0])
        for t in all_tris:
            _,ax,ay,bx,by,cx,cy,col = t
            self.create_polygon(ax,ay,bx,by,cx,cy, fill=col, outline='', width=0)

        # Info
        n_tris = sum(len(m['tris']) for m in self.meshes)
        n_v    = sum(len(m['verts']) for m in self.meshes)
        self.create_text(8, 8, anchor='nw',
                         text=f"{len(self.meshes)} mesh  |  {n_v} verts  |  {n_tris} tris",
                         fill=TEXT2, font=("Consolas",8))
        self.create_text(8, h-16, anchor='nw',
                         text="Clic gauche: rotation  |  Clic droit: pan  |  Molette: zoom",
                         fill=TEXT2, font=("Consolas",8))

    def _on_press(self,  e): self._drag='rot';  self._last=(e.x,e.y)
    def _on_rpress(self, e): self._drag='pan';  self._last=(e.x,e.y)
    def _on_drag(self,   e):
        if self._last:
            dx,dy = e.x-self._last[0], e.y-self._last[1]
            self.rot_y += dx*0.5; self.rot_x += dy*0.5
            self._last=(e.x,e.y); self._draw()
    def _on_rdrag(self, e):
        if self._last:
            dx,dy = e.x-self._last[0], e.y-self._last[1]
            self.pan_x += dx; self.pan_y += dy
            self._last=(e.x,e.y); self._draw()
    def _on_wheel(self, e):
        factor = 1.1 if e.delta > 0 else 0.9
        self.zoom = max(0.05, min(20.0, self.zoom*factor))
        self._draw()


# =============================================================================
# GUI PRINCIPAL
# =============================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("3DMigoto Converter — ULTIMATE")
        self.geometry("1100x720")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(800, 600)

        self.buffers_var = tk.StringVar()
        self.output_var  = tk.StringVar()
        self.stride_var  = tk.StringVar(value="auto")
        self.format_var  = tk.StringVar(value="all")
        self.script_var  = tk.StringVar()
        self.running     = False
        self._last_objs  = []  # fichiers OBJ generes
        self._stride_cache = {}  # dossier -> stride

        self._build_ui()

    # ── Construction UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg="#0a0a1f", pady=10)
        hdr.pack(fill='x')
        tk.Label(hdr, text="3DMigoto  ·  OBJ / glTF / FBX  ·  Viewer 3D",
                 font=("Segoe UI",16,"bold"), fg=ACCENT, bg="#0a0a1f").pack(side='left',padx=16)
        tk.Label(hdr, text="ULTIMATE v4",
                 font=("Segoe UI",9), fg=TEXT2, bg="#0a0a1f").pack(side='left')

        # Contenu principal = gauche (controles) + droite (viewer)
        main = tk.Frame(self, bg=BG)
        main.pack(fill='both', expand=True)

        # ── Panneau gauche ──
        left = tk.Frame(main, bg=PANEL, width=400)
        left.pack(side='left', fill='y', padx=(8,4), pady=8)
        left.pack_propagate(False)

        self._build_controls(left)

        # ── Panneau droite (viewer) ──
        right = tk.Frame(main, bg=BG)
        right.pack(side='left', fill='both', expand=True, padx=(4,8), pady=8)

        # Header viewer
        vh = tk.Frame(right, bg=BG3, pady=6)
        vh.pack(fill='x')
        tk.Label(vh, text="Visionneuse 3D", font=("Segoe UI",11,"bold"),
                 fg=ACCENT, bg=BG3).pack(side='left', padx=10)
        self.lbl_mesh = tk.Label(vh, text="", font=("Segoe UI",9),
                                  fg=TEXT2, bg=BG3)
        self.lbl_mesh.pack(side='left', padx=6)

        # Boutons viewer
        vbtns = tk.Frame(vh, bg=BG3)
        vbtns.pack(side='right', padx=8)
        self._vbtn(vbtns, "Recharger", self._reload_viewer)
        self._vbtn(vbtns, "Reset vue", self._reset_view)

        # Selector mesh
        sel_frame = tk.Frame(right, bg=BG2, pady=4)
        sel_frame.pack(fill='x')
        tk.Label(sel_frame, text="Mesh:", fg=TEXT2, bg=BG2,
                 font=("Segoe UI",9)).pack(side='left', padx=(10,4))
        self.mesh_selector = ttk.Combobox(sel_frame, state='readonly', width=30)
        self.mesh_selector.pack(side='left')
        self.mesh_selector.bind('<<ComboboxSelected>>', self._on_mesh_select)

        # Canvas 3D
        self.viewer = Viewer3D(right)
        self.viewer.pack(fill='both', expand=True, padx=2, pady=2)

    def _build_controls(self, parent):
        pad = {'padx': 10, 'pady': (0,2)}

        def section(txt):
            f = tk.Frame(parent, bg=PANEL)
            f.pack(fill='x', padx=10, pady=(10,2))
            tk.Label(f, text=txt, font=("Segoe UI",9,"bold"),
                     fg=ACCENT, bg=PANEL).pack(anchor='w')
            tk.Frame(parent, bg=BORDER, height=1).pack(fill='x', padx=10)

        section("Dossier du mod (buffers)")
        self._path_row(parent, self.buffers_var, self._browse_buffers,
                       "(dossier contenant les .ib et .buf)")

        section("Dossier de sortie")
        self._path_row(parent, self.output_var, self._browse_output,
                       "(meme dossier par defaut)")

        section("Script migoto_to_fbx.py")
        self._path_row(parent, self.script_var, self._browse_script,
                       "Chemin vers migoto_to_fbx.py")

        section("Options")
        opt = tk.Frame(parent, bg=PANEL)
        opt.pack(fill='x', **pad)

        tk.Label(opt, text="Stride:", fg=TEXT2, bg=PANEL,
                 font=("Segoe UI",9)).grid(row=0,column=0,sticky='w',padx=(0,4))
        cb = ttk.Combobox(opt, textvariable=self.stride_var, width=6,
                          values=["auto","12","16","20","24","28","32","40","48","52","64"])
        cb.grid(row=0,column=1,sticky='w',padx=(0,16))

        tk.Label(opt, text="Format:", fg=TEXT2, bg=PANEL,
                 font=("Segoe UI",9)).grid(row=0,column=2,sticky='w',padx=(0,4))
        for i,(v,l) in enumerate([("all","Tout"),("obj","OBJ"),("gltf","glTF"),("fbx","FBX")]):
            tk.Radiobutton(opt, text=l, variable=self.format_var, value=v,
                           bg=PANEL, fg=TEXT, selectcolor=BG3,
                           activebackground=PANEL, activeforeground=ACCENT,
                           font=("Segoe UI",9)).grid(row=0,column=3+i,sticky='w',padx=2)

        # Bouton convert
        self.btn_conv = tk.Button(parent, text="  CONVERTIR",
                                   font=("Segoe UI",13,"bold"),
                                   bg=ACCENT, fg="white", relief='flat',
                                   padx=16, pady=10, cursor="hand2",
                                   command=self._run,
                                   activebackground=ACCENT2, activeforeground="white")
        self.btn_conv.pack(fill='x', padx=10, pady=10)

        section("Console")
        self.console = scrolledtext.ScrolledText(
            parent, height=14, bg="#08081a", fg=GREEN,
            font=("Consolas",8), relief='flat', state='disabled',
            insertbackground=GREEN)
        self.console.pack(fill='both', expand=True, padx=10, pady=(4,10))
        self.console.tag_config('err',  foreground=ACCENT2)
        self.console.tag_config('ok',   foreground=GREEN)
        self.console.tag_config('warn', foreground=YELLOW)
        self.console.tag_config('info', foreground=TEXT2)

        self._log("Pret. Selectionne un dossier de mod.", 'info')

    def _path_row(self, parent, var, cmd, placeholder):
        f = tk.Frame(parent, bg=PANEL)
        f.pack(fill='x', padx=10, pady=(2,0))
        e = tk.Entry(f, textvariable=var, bg=BG2, fg=TEXT2,
                     insertbackground=TEXT, relief='flat',
                     font=("Segoe UI",9), bd=4)
        e.configure(highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT)
        if not var.get():
            e.insert(0, placeholder)
        e.pack(side='left', fill='x', expand=True)
        tk.Button(f, text="...", command=cmd, bg=BG3, fg=TEXT,
                  relief='flat', padx=6, pady=3, cursor="hand2",
                  font=("Segoe UI",9),
                  activebackground=ACCENT).pack(side='left', padx=(4,0))
        return e

    def _vbtn(self, parent, text, cmd):
        tk.Button(parent, text=text, command=cmd, bg=BG3, fg=TEXT,
                  relief='flat', padx=8, pady=3, cursor="hand2",
                  font=("Segoe UI",9),
                  activebackground=ACCENT).pack(side='left', padx=2)

    # ── Browsing ─────────────────────────────────────────────────────────────

    def _browse_buffers(self):
        d = filedialog.askdirectory(title="Dossier des buffers")
        if d:
            self.buffers_var.set(d)
            if not self.output_var.get() or \
               self.output_var.get() == "(meme dossier par defaut)":
                self.output_var.set(d)
            self._log(f"Buffers : {d}", 'info')

    def _browse_output(self):
        d = filedialog.askdirectory(title="Dossier de sortie")
        if d: self.output_var.set(d)

    def _browse_script(self):
        f = filedialog.askopenfilename(
            title="migoto_to_fbx.py",
            filetypes=[("Python","*.py"),("Tous","*.*")])
        if f: self.script_var.set(f)

    # ── Viewer ───────────────────────────────────────────────────────────────

    def _reload_viewer(self):
        if not self._last_objs:
            self._log("Pas de fichier OBJ disponible.", 'warn'); return
        self._load_obj_in_viewer(self._last_objs[0])

    def _reset_view(self):
        self.viewer.rot_x = 20.0
        self.viewer.rot_y = 0.0
        self.viewer.zoom  = 1.0
        self.viewer.pan_x = self.viewer.pan_y = 0.0
        self.viewer._draw()

    def _load_obj_in_viewer(self, path):
        if not os.path.isfile(path):
            self._log(f"Fichier introuvable : {path}", 'err'); return
        self._log(f"Chargement viewer : {os.path.basename(path)}", 'info')
        self.viewer.load_obj(path)
        n = len(self.viewer.meshes)
        self.lbl_mesh.configure(text=f"{os.path.basename(path)}  ({n} mesh)")

    def _on_mesh_select(self, e):
        val = self.mesh_selector.get()
        if val and val in [os.path.basename(p) for p in self._last_objs]:
            for p in self._last_objs:
                if os.path.basename(p) == val:
                    self._load_obj_in_viewer(p)
                    break

    # ── Conversion ───────────────────────────────────────────────────────────

    def _log(self, msg, tag=''):
        self.console.configure(state='normal')
        self.console.insert('end', msg+'\n', tag)
        self.console.see('end')
        self.console.configure(state='disabled')

    def _run(self):
        if self.running: return

        buffers = self.buffers_var.get().strip()
        output  = self.output_var.get().strip()
        script  = self.script_var.get().strip()
        stride  = self.stride_var.get().strip()
        fmt     = self.format_var.get()

        placeholders = ["(dossier contenant les .ib et .buf)",
                        "(meme dossier par defaut)",
                        "Chemin vers migoto_to_fbx.py"]

        if not buffers or buffers in placeholders or not os.path.isdir(buffers):
            self._log("[ERR] Dossier de buffers invalide !", 'err'); return
        if not script or script in placeholders or not os.path.isfile(script):
            self._log("[ERR] Script introuvable !", 'err'); return

        if not output or output in placeholders:
            output = buffers

        out_file = os.path.join(output, "output.obj")
        cmd = [sys.executable, script,
               "--buffers", buffers,
               "--output",  out_file,
               "--format",  fmt]
        if stride != "auto":
            cmd += ["--stride", stride]

        self._log(f"\n{'─'*40}", 'info')
        self._log(f"Lancement : {os.path.basename(script)}", 'info')
        self._log(f"Buffers   : {buffers}", 'info')
        self._log(f"Sortie    : {output}", 'info')
        self._log(f"{'─'*40}\n", 'info')

        self.running = True
        self._last_objs = []
        self.btn_conv.configure(text="  En cours...", state='disabled', bg=BG3)
        threading.Thread(target=self._run_thread,
                         args=(cmd, output), daemon=True).start()

    def _run_thread(self, cmd, out_dir):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='replace')
            for line in proc.stdout:
                line = line.rstrip()
                if not line: continue
                tag = 'err'  if '[ERR]'  in line or 'Error' in line else \
                      'ok'   if '[OK]'   in line or 'Termine' in line else \
                      'warn' if '[WARN]' in line or 'SKIP'   in line else ''
                self.after(0, self._log, line, tag)
            proc.wait()

            if proc.returncode == 0:
                # Trouve les OBJ generes
                objs = [os.path.join(out_dir, f)
                        for f in os.listdir(out_dir) if f.endswith('.obj')]
                objs.sort()
                self.after(0, self._on_conversion_done, objs)
                self.after(0, self._log, "\nConversion terminee !", 'ok')
            else:
                self.after(0, self._log, "\nErreur lors de la conversion.", 'err')
        except Exception as e:
            self.after(0, self._log, f"[ERR] {e}", 'err')
        finally:
            self.after(0, self._reset_btn)

    def _on_conversion_done(self, objs):
        self._last_objs = objs
        names = [os.path.basename(p) for p in objs]
        self.mesh_selector['values'] = names
        if names: self.mesh_selector.set(names[0])
        if objs:
            self._log(f"Chargement dans la visionneuse...", 'info')
            self._load_obj_in_viewer(objs[0])

    def _reset_btn(self):
        self.running = False
        self.btn_conv.configure(text="  CONVERTIR", state='normal', bg=ACCENT)


if __name__ == '__main__':
    app = App()
    app.mainloop()
