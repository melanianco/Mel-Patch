import struct
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess

# Set your FFmpeg bin directory here
FFMPEG_BIN = r"C:\ffmpeg-8.0-full_build\bin"
FFPROBE_PATH = f"{FFMPEG_BIN}\\ffprobe.exe"

def parse_number(txt: str):
    txt = re.sub('[^0-9.,]', '', txt).replace(',', '.')
    try:
        return float(txt)
    except:
        return None

def detect_original_fps(filename):
    """
    Automatically detect original FPS using ffprobe (requires FFmpeg installed).
    """
    try:
        result = subprocess.run(
            [FFPROBE_PATH, '-v', '0', '-of', 'csv=p=0', '-select_streams', 'v:0',
             '-show_entries', 'stream=r_frame_rate', filename],
            capture_output=True, text=True, check=True
        )
        fps_text = result.stdout.strip()  # e.g., "30000/1001"
        if '/' in fps_text:
            num, denom = fps_text.split('/')
            return float(num) / float(denom)
        else:
            return float(fps_text)
    except Exception as e:
        print("FFprobe error:", e)
        return None

def patch_atom(atom_name, data, scale_factor=None):
    """
    Patch the timescale/duration in mvhd or mdhd atoms
    """
    atom_bytes = atom_name.encode('utf-8')
    count = 0
    start = 0

    while True:
        found = data.find(atom_bytes, start)
        if found == -1:
            break

        # Size of atom (4 bytes before the name)
        size_offset = found - 4
        if size_offset < 0:
            start = found + len(atom_bytes)
            continue
        size_bytes = data[size_offset:size_offset + 4]
        atom_size = struct.unpack(">I", size_bytes)[0]

        # Offsets for timescale and duration (version 0)
        timescale_offset = found + 12
        duration_offset = found + 16

        if scale_factor:
            # Patch timescale
            orig_timescale = struct.unpack(">I", data[timescale_offset:timescale_offset+4])[0]
            new_timescale = int(orig_timescale * scale_factor)
            data[timescale_offset:timescale_offset+4] = struct.pack(">I", new_timescale)

            # Patch duration
            orig_duration = struct.unpack(">I", data[duration_offset:duration_offset+4])[0]
            new_duration = int(orig_duration * scale_factor)
            data[duration_offset:duration_offset+4] = struct.pack(">I", new_duration)

        count += 1
        start = found + len(atom_bytes)
    return count

def patch_mp4(input_filename, output_filename, scale_factor=None):
    with open(input_filename, 'rb') as f:
        data = bytearray(f.read())
    patched_mvhd = patch_atom('mvhd', data, scale_factor)
    patched_mdhd = patch_atom('mdhd', data, scale_factor)
    total_patched = patched_mvhd + patched_mdhd
    print(f'\nTotal patched atoms: {total_patched}')
    with open(output_filename, 'wb') as f:
        f.write(data)
    print(f'Patched file written to: {output_filename}')

def browse_in(var, fps_var):
    path = filedialog.askopenfilename(filetypes=[('MP4', '*.mp4')])
    if path:
        var.set(path)
        # Auto-detect FPS and fill the box
        fps = detect_original_fps(path)
        if fps:
            fps_var.set(f"{fps:.3f}")
        else:
            messagebox.showwarning("Warning", "Could not detect original FPS.")

def browse_out(var):
    path = filedialog.asksaveasfilename(defaultextension='.mp4', filetypes=[('MP4', '*.mp4')])
    if path:
        var.set(path)

def on_apply(in_var, out_var, fps_var):
    inp = in_var.get().strip()
    outp = out_var.get().strip()
    fps_txt = fps_var.get().strip()

    if not inp or not outp or not fps_txt:
        messagebox.showerror('Error', 'Please fill all fields.')
        return

    fps = parse_number(fps_txt)
    if not fps or fps <= 0:
        messagebox.showerror('Error', 'Invalid FPS value.')
        return

    # Detect original FPS automatically
    orig_fps = detect_original_fps(inp)
    if not orig_fps:
        messagebox.showerror('Error', 'Could not detect original FPS. Make sure FFmpeg is installed.')
        return

    scale_factor = orig_fps / fps
    patch_mp4(inp, outp, scale_factor)
    messagebox.showinfo('Success', f'File patched successfully:\n{outp}')

def build_gui():
    root = tk.Tk()
    root.title('MP4 Patcher by Mel .co')
    root.geometry('480x260')
    root.configure(bg='#1a1b1e')

    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background='#1a1b1e')
    style.configure('TLabel', background='#1a1b1e', foreground='#e8e8e8', font=('Segoe UI', 10))
    style.configure('TButton', background='#2b2d31', foreground='#ffffff', font=('Segoe UI', 10, 'bold'), relief='flat', padding=6)
    style.map('TButton', background=[('active', '#3a3d42')], relief=[('pressed', 'sunken')])
    style.configure('TEntry', fieldbackground='#2b2d31', foreground='#e8e8e8', insertcolor='#ffffff')

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill='both', expand=True)

    in_var, out_var, fps_var = tk.StringVar(), tk.StringVar(), tk.StringVar()

    ttk.Label(frame, text='Input video:').grid(row=0, column=0, sticky='w', pady=(0, 2))
    ttk.Entry(frame, textvariable=in_var, width=55).grid(row=1, column=0, sticky='we')
    ttk.Button(frame, text='...', command=lambda: browse_in(in_var, fps_var)).grid(row=1, column=1, padx=(5, 0))

    ttk.Label(frame, text='Save as:').grid(row=2, column=0, sticky='w', pady=(10, 2))
    ttk.Entry(frame, textvariable=out_var, width=55).grid(row=3, column=0, sticky='we')
    ttk.Button(frame, text='...', command=lambda: browse_out(out_var)).grid(row=3, column=1, padx=(5, 0))

    ttk.Label(frame, text='Desired FPS (any number):').grid(row=4, column=0, sticky='w', pady=(10, 2))
    ttk.Entry(frame, textvariable=fps_var, width=12).grid(row=5, column=0, sticky='w')

    ttk.Button(frame, text='Apply Patch', command=lambda: on_apply(in_var, out_var, fps_var)).grid(row=6, column=0, pady=18)

    frame.grid_columnconfigure(0, weight=1)
    root.resizable(False, False)
    return root

if __name__ == '__main__':
    app = build_gui()
    app.mainloop()