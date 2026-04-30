import time
import cv2
import numpy as np
import torch
import argparse
import json
import os
from PIL import Image
from torchvision import transforms
try:
    import NDIlib as ndi
    NDI_AVAILABLE = True
except ImportError:
    ndi = None
    NDI_AVAILABLE = False
    
import subprocess
import gc
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import logging
import traceback

# Sett opp logging til fil
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("studio_log.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# CorridorKey and BiRefNet imports
from CorridorKeyModule.inference_engine import CorridorKeyEngine
from BiRefNetModule.wrapper import BiRefNetHandler, ImagePreprocessor

def get_windows_cameras():
    """Tries to get a list of active camera names using PowerShell."""
    try:
        # Use PowerShell to get device names
        cmd = ["powershell", "-Command", "Get-PnpDevice -Class Camera -Status OK | Select-Object -ExpandProperty FriendlyName"]
        output = subprocess.check_output(cmd, encoding='utf-8', startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW)).strip()
        if output:
            names = output.split('\n')
            return [n.strip() for n in names if n.strip()]
    except Exception:
        pass
    return []

class MessageLog:
    def __init__(self, max_messages=8):
        self.messages = []
        self.max_messages = max_messages
    
    def add(self, msg):
        self.messages.append((msg, time.time()))
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)
            
    def draw(self, frame):
        # Draw semi-transparent background for messages
        h, w = frame.shape[:2]
        overlay = frame.copy()
        
        y_start = h - 20
        active_msgs = []
        for msg, t in reversed(self.messages):
            age = time.time() - t
            if age > 10: continue
            active_msgs.append((msg, age))
            
        if not active_msgs:
            return frame
            
        rect_h = len(active_msgs) * 25 + 10
        cv2.rectangle(overlay, (5, h - rect_h - 10), (min(w-5, 500), h - 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        y = h - 25
        for msg, age in active_msgs:
            alpha = max(0, min(1, 1 - (age - 8) / 2)) # Fade out last 2 seconds
            color = (0, 255, 0)
            # Simple fade by darkening color (OpenCV putText doesn't support alpha)
            c = tuple(int(channel * alpha) for channel in color)
            cv2.putText(frame, msg, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)
            y -= 25
        return frame

class GUILogHandler(logging.Handler):
    def __init__(self, message_log):
        super().__init__()
        self.message_log = message_log
    def emit(self, record):
        try:
            msg = self.format(record)
            self.message_log.add(msg)
        except Exception:
            self.handleError(record)


class StudioLauncher:
    """A simple pre-launch GUI for setting up the Studio without touching the code."""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CorridorKey Live Studio Setup v1.2.0")
        self.root.geometry("450x650")
        
        # Center the window
        self.root.eval('tk::PlaceWindow . center')
        
        self.settings = None
        
        # Title
        ttk.Label(self.root, text="CorridorKey Live Studio", font=("Arial", 16, "bold")).pack(pady=15)
        
        # UI Elements
        ttk.Label(self.root, text="Select Camera:").pack(pady=(5, 0))
        
        # Get list of cameras, fall back to indices if names can't be fetched
        camera_list = get_windows_cameras()
        cam_values = []
        for i in range(10): # Offer up to 10 cameras
            name = camera_list[i] if i < len(camera_list) else f"Camera {i}"
            cam_values.append(f"{i}: {name}")
            
        self.camera_id = ttk.Combobox(self.root, values=cam_values, state="readonly", justify="center", width=30)
        self.camera_id.set(cam_values[0])
        self.camera_id.pack()
        
        ttk.Label(self.root, text="Camera Resolution:").pack(pady=(15, 0))
        self.cam_res = ttk.Combobox(self.root, values=["1920x1080", "1280x720", "3840x2160"], state="readonly", justify="center")
        self.cam_res.set("1920x1080")
        self.cam_res.pack()
        
        ttk.Label(self.root, text="BiRefNet Model (Alpha Hint):").pack(pady=(15, 0))
        self.biref_model = ttk.Combobox(self.root, values=["General-Lite", "General-reso_512", "General"], state="readonly", justify="center")
        self.biref_model.set("General-reso_512")
        self.biref_model.pack()
        
        ttk.Label(self.root, text="CorridorKey Resolution:").pack(pady=(15, 0))
        self.ck_res = ttk.Combobox(self.root, values=["512", "1024", "2048"], state="readonly", justify="center")
        self.ck_res.set("1024")
        self.ck_res.pack()
        
        self.ndi_var = tk.BooleanVar(value=NDI_AVAILABLE)
        cb = ttk.Checkbutton(self.root, text="Enable NDI Stream", variable=self.ndi_var)
        cb.pack(pady=10)
        if not NDI_AVAILABLE:
            cb.config(state="disabled", text="NDI Not Installed (Disabled)")
            
        # Device Selector
        ttk.Label(self.root, text="Compute Device:").pack(pady=(5, 0))
        self.device_var = ttk.Combobox(self.root, values=["Auto (Recommended)", "CUDA", "CPU"], state="readonly", justify="center")
        self.device_var.set("Auto (Recommended)")
        self.device_var.pack()
        
        # CUDA Status Label
        cuda_available = torch.cuda.is_available()
        cuda_status = "Available" if cuda_available else "NOT FOUND (Running on CPU)"
        status_color = "green" if cuda_available else "red"
        status_label = tk.Label(self.root, text=f"CUDA Status: {cuda_status}", fg=status_color, font=("Arial", 9, "bold"))
        status_label.pack(pady=(5, 0))
        
        # Start button
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 12, "bold"))
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)
        
        start_btn = ttk.Button(button_frame, text="Start Studio", command=self.start_app, width=15)
        start_btn.grid(row=0, column=0, padx=5)
        
        save_btn = ttk.Button(button_frame, text="Save Autostart", command=self.save_autostart, width=15)
        save_btn.grid(row=0, column=1, padx=5)
        
    def _update_cuda_status(self):
        try:
            pass
        except Exception:
            pass

    def get_current_settings(self):
        w, h = map(int, self.cam_res.get().split('x'))
        cam_id_str = self.camera_id.get()
        # Extract the integer ID from "0: Name"
        cam_id_val = int(cam_id_str.split(':')[0])
        
        return {
            "CAMERA_ID": cam_id_val,
            "CAMERA_WIDTH": w,
            "CAMERA_HEIGHT": h,
            "CAMERA_FPS": 60,
            "BIREFNET_MODEL": self.biref_model.get(),
            "CORRIDORKEY_RES": int(self.ck_res.get()),
            "NDI_ENABLED": self.ndi_var.get(),
            "COMPUTE_DEVICE": self.device_var.get()
        }

    def save_autostart(self):
        cfg = self.get_current_settings()
        try:
            with open("autostart_config.json", "w") as f:
                json.dump(cfg, f, indent=4)
            messagebox.showinfo("Saved", "Autostart settings saved to autostart_config.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def start_app(self):
        self.settings = self.get_current_settings()
        self.root.destroy()

def create_ndi_sender(name="CorridorKey Live"):
    """Create NDI Video Sender."""
    if not ndi.initialize():
        logging.error("Cannot run NDI.")
        return None
    ndi_send_create_desc = ndi.SendCreate()
    ndi_send_create_desc.ndi_name = name
    ndi_send = ndi.send_create(ndi_send_create_desc)
    if ndi_send is None:
        logging.error("Error creating NDI sender")
        return None
    return ndi_send

def send_ndi_frame(ndi_send, rgba_frame):
    """Send an RGBA numpy frame to NDI."""
    h, w, _ = rgba_frame.shape
    
    # NDI expects BGRA or RGBA depending on FOURCC
    # CorridorKey output might be RGBA, we ensure uint8
    if rgba_frame.dtype != np.uint8:
        rgba_frame = (rgba_frame * 255).astype(np.uint8)
        
    video_frame = ndi.VideoFrameV2()
    video_frame.data = rgba_frame
    video_frame.FourCC = ndi.FOURCC_VIDEO_TYPE_RGBA
    video_frame.xres = w
    video_frame.yres = h
    # We set 30fps typical broadcast
    video_frame.frame_rate_N = 30000
    video_frame.frame_rate_D = 1000
    video_frame.picture_aspect_ratio = w / h
    
    ndi.send_send_video_v2(ndi_send, video_frame)

def main():
    parser = argparse.ArgumentParser(description="CorridorKey Live Studio")
    parser.add_argument("--autostart", action="store_true", help="Bypass GUI and use saved settings")
    args = parser.parse_args()
    
    cfg = None
    if args.autostart:
        try:
            with open("autostart_config.json", "r") as f:
                cfg = json.load(f)
            logging.info("Autostart activated. Loaded config from autostart_config.json")
        except Exception as e:
            logging.error(f"Failed to load autostart config: {e}")
            logging.info("Falling back to GUI.")
            
    if not cfg:
        # 1. Launch GUI to get settings
        launcher = StudioLauncher()
        launcher.root.mainloop()
        
        if not launcher.settings:
            logging.info("Setup cancelled. Exiting.")
            return
            
        cfg = launcher.settings

    logging.info("Initialize CorridorKey Live Studio...")
    
    # Device selection based on GUI choice
    requested_device = cfg["COMPUTE_DEVICE"]
    if "CUDA" in requested_device:
        device = "cuda"
    elif "CPU" in requested_device:
        device = "cpu"
    else: # Auto
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        
    # Check if a GPU is present but not used
    if device == "cpu":
        try:
            # Check for NVIDIA GPU
            if subprocess.call(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                logging.warning("="*60)
                logging.warning("!!! KRAFTIG ADVARSEL: NVIDIA GPU FUNNET, MEN BRUKES IKKE !!!")
                logging.warning("Programmet kjører på CPU, noe som vil være ekstremt tregt.")
                logging.warning("Vennligst kjør Start_Live_Studio_Windows.bat for å reparere miljøet.")
                logging.warning("="*60)
        except Exception:
            pass
        
    half_precision = True if device != "cpu" else False
    
    # 2. Model Loader
    logging.info(f"Loading Models onto {device} in FP16...")
    
    # BiRefNet setup
    birefnet_handler = BiRefNetHandler(device=device, usage=cfg["BIREFNET_MODEL"])
    birefnet_model = birefnet_handler.birefnet
    birefnet_preprocessor = ImagePreprocessor(resolution=tuple(birefnet_handler.resolution))
    
    # CorridorKey setup
    ck_engine = CorridorKeyEngine(
        checkpoint_path="CorridorKeyModule/checkpoints/CorridorKey.safetensors",
        img_size=cfg["CORRIDORKEY_RES"],
        device=device,
        model_precision=torch.float16 if half_precision else torch.float32,
        mixed_precision=half_precision if device == "cuda" else False,
    )
    
    logging.info("Models Loaded.")
    
    # GUI Logging Integration
    message_log = MessageLog()
    gui_handler = GUILogHandler(message_log)
    gui_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(gui_handler)
    
    # NDI Integration
    ndi_sender = create_ndi_sender("CorridorKey Live") if cfg["NDI_ENABLED"] else None
    
    # Camera Capture - Use DSHOW on Windows for best performance
    cap = cv2.VideoCapture(cfg["CAMERA_ID"], cv2.CAP_DSHOW) if sys.platform.startswith('win') else cv2.VideoCapture(cfg["CAMERA_ID"])
    # Force MJPG codec which supports 60fps at high resolutions on most webcams
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["CAMERA_WIDTH"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["CAMERA_HEIGHT"])
    cap.set(cv2.CAP_PROP_FPS, cfg["CAMERA_FPS"])
    
    cap_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logging.info(f"Capture started at {cap_width}x{cap_height}")
    
    # 3. Setup OpenCV Window and Live Controls
    window_name = "CorridorKey Live Studio v1.2.0"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    
    def noop(x): pass
    cv2.createTrackbar("1. Clean Edge", window_name, 10, 20, noop) # Erode/Dilate
    cv2.createTrackbar("2. Remove Dots", window_name, 400, 1000, noop) # Despeckle
    cv2.createTrackbar("3. Soften Hair", window_name, 100, 200, noop) # Refiner
    cv2.createTrackbar("4. Remove Green", window_name, 100, 100, noop) # Despill
    cv2.createTrackbar("Window Scale %", window_name, 50, 100, noop)
    
    frame_count = 0
    view_mode = 0 # 0=Result, 1=Grid
    
    # FPS tracking
    fps_history = []
    
    # Pre-allocate ImageNet normalization tensors on GPU
    imgnet_mean = torch.tensor([0.485, 0.456, 0.406], device=device).view(3, 1, 1)
    imgnet_std = torch.tensor([0.229, 0.224, 0.225], device=device).view(3, 1, 1)
    
    import torch.nn.functional as F
    
    logging.info("Starting Main Loop...")
    logging.info("Press 'V' to toggle view mode (Grid vs Output).")
    logging.info("Press 'Q' to quit.")
    
    while cap.isOpened():
        loop_start_time = time.time()
        
        # Measure camera time
        cam_start = time.time()
        ret, frame = cap.read()
        cam_time = (time.time() - cam_start) * 1000
        
        if not ret:
            logging.error("Failed to grab frame.")
            break
            
        # Read GUI Controls
        despill_val = cv2.getTrackbarPos("4. Remove Green", window_name) / 100.0
        despeckle_val = cv2.getTrackbarPos("2. Remove Dots", window_name)
        erode_val = cv2.getTrackbarPos("1. Clean Edge", window_name) - 10
        refine_scale = cv2.getTrackbarPos("3. Soften Hair", window_name) / 100.0
        
        # 1. Image Preprocessing
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Fast GPU Preprocessing for BiRefNet
        res = birefnet_handler.resolution
        if res is None:
            res = (int(frame_rgb.shape[1] // 32 * 32), int(frame_rgb.shape[0] // 32 * 32))
            
        frame_resized = cv2.resize(frame_rgb, tuple(res), interpolation=cv2.INTER_LINEAR)
        
        # Convert to tensor and move to GPU
        image_proc = torch.from_numpy(frame_resized).to(device, non_blocking=True).permute(2, 0, 1).float()
        
        # Normalize (ImageNet stats)
        image_proc.div_(255.0).sub_(imgnet_mean).div_(imgnet_std).unsqueeze_(0)
            
        if half_precision:
            image_proc = image_proc.half()
            
        t1 = time.time()
        with torch.no_grad():
            preds = birefnet_model(image_proc)[-1].sigmoid() # Keep on GPU
            
        # Fast GPU Postprocessing
        target_h, target_w = frame_rgb.shape[:2]
        preds_resized = F.interpolate(preds, size=(target_h, target_w), mode='bilinear', align_corners=False)
        
        # Apply Erode/Dilate directly on the GPU tensor! (This fixes the massive OpenCV float32 bug)
        if erode_val != 0:
            k_size = abs(erode_val) * 2 + 1
            padding = k_size // 2
            if erode_val < 0: # Erode = MinPool
                preds_resized = -F.max_pool2d(-preds_resized, kernel_size=k_size, stride=1, padding=padding)
            else: # Dilate = MaxPool
                preds_resized = F.max_pool2d(preds_resized, kernel_size=k_size, stride=1, padding=padding)
                
        # Move to CPU as 0.0-1.0 float32 numpy array
        mask_linear = preds_resized[0, 0].float().cpu().numpy()
        t2 = time.time()
        
        # Refinement Layer (CorridorKey)
        ck_out = ck_engine.process_frame(
            image=frame_rgb,
            mask_linear=mask_linear,
            refiner_scale=refine_scale,
            generate_comp=True,
            auto_despeckle=(despeckle_val > 0),
            despeckle_size=despeckle_val,
            despill_strength=despill_val,
            post_process_on_gpu=True
        )
        t3 = time.time()
        
        # The result includes: alpha, fg, comp, processed (RGBA)
        res_comp_srgb = ck_out['comp'] # 0.0 - 1.0 composite on checkboard
        res_processed_rgba = ck_out['processed'] # 0.0 - 1.0 linear RGBA
        
        # NDI Output (requires 0-255 RGBA uint8 in sRGB color space)
        if ndi_sender:
            # 1. Split Alpha
            rgb_lin = res_processed_rgba[:, :, :3]
            alpha = res_processed_rgba[:, :, 3:]
            
            # 2. Convert RGB from Linear to sRGB (so it's not dark)
            # Simple 2.2 gamma approximation for speed, or use a proper curve
            rgb_srgb = cv2.pow(cv2.max(rgb_lin, 0.0), 1.0/2.2)
            
            # 3. Recombine and convert to uint8
            rgba_srgb = np.concatenate([rgb_srgb, alpha], axis=-1)
            rgba_out = cv2.convertScaleAbs(rgba_srgb, alpha=255.0)
            
            # 4. Send to NDI (ensure memory is contiguous)
            send_ndi_frame(ndi_sender, np.ascontiguousarray(rgba_out))
            
        t4 = time.time()
        
        # Latency Meter
        latency_ms = (t4 - loop_start_time) * 1000
        prep_ms = (t1 - loop_start_time) * 1000
        biref_ms = (t2 - t1) * 1000
        ck_ms = (t3 - t2) * 1000
        post_ms = (t4 - t3) * 1000
        
        # VRAM Management
        frame_count += 1
        
        # FPS Calculation
        loop_time = time.time() - loop_start_time
        fps = 1.0 / loop_time if loop_time > 0 else 0
        fps_history.append(fps)
        if len(fps_history) > 30:
            fps_history.pop(0)
        avg_fps = sum(fps_history) / len(fps_history)
            
        # Visualization Modes
        scale_val = cv2.getTrackbarPos("Window Scale %", window_name) / 100.0
        if scale_val < 0.1: scale_val = 0.1 # Minimum scale

        vis_res = cv2.convertScaleAbs(res_comp_srgb, alpha=255.0)
        vis_res = cv2.cvtColor(vis_res, cv2.COLOR_RGB2BGR)
        
        if view_mode == 1:
            # Side by side (Grid)
            vis_orig = frame
            # mask_linear is 0.0 - 1.0, convert back to 0-255 uint8 for display
            vis_mask_8u = cv2.convertScaleAbs(mask_linear, alpha=255.0)
            vis_mask = cv2.cvtColor(vis_mask_8u, cv2.COLOR_GRAY2BGR)
            
            # Add labels
            cv2.putText(vis_orig, f"Original ({cap_width}x{cap_height})", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(vis_mask, "BiRefNet Alpha", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(vis_res, "CorridorKey Refined", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            grid = np.hstack((vis_orig, vis_mask, vis_res))
        else:
            # Result only
            cv2.putText(vis_res, "Live Output", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            grid = vis_res

        # Determine actual device strings for debugging
        biref_dev = str(birefnet_model.device).upper()
        ck_dev = str(ck_engine.device).upper()

        # Add Latency, FPS, and Camera Info to the top right
        info_text = f"FPS:{avg_fps:.0f} | Lat:{latency_ms:.0f}ms (P:{prep_ms:.0f}|B:{biref_ms:.0f}|C:{ck_ms:.0f}|N:{post_ms:.0f}) | {ck_dev}"
        cv2.putText(grid, info_text, (grid.shape[1] - 580, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

        # Draw Message Log Overlay
        grid = message_log.draw(grid)

        # Apply Scaling
        if scale_val != 1.0:
            h, w = grid.shape[:2]
            grid = cv2.resize(grid, (int(w * scale_val), int(h * scale_val)))
            
        cv2.imshow(window_name, grid)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('v'):
            view_mode = 1 - view_mode # Toggle 0 and 1

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    if ndi_sender:
        ndi.send_destroy(ndi_sender)
        ndi.destroy()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error("Programmet krasjet med en uventet feil:")
        logging.error(traceback.format_exc())
        print("Sjekk studio_log.txt for detaljer om feilen.")
        sys.exit(1)
