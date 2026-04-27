import time
import cv2
import numpy as np
import torch
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
        self.root.title("CorridorKey Live Setup")
        self.root.geometry("400x450")
        
        # Center the window
        self.root.eval('tk::PlaceWindow . center')
        
        self.settings = None
        
        # Title
        ttk.Label(self.root, text="CorridorKey Live Studio", font=("Arial", 16, "bold")).pack(pady=15)
        
        # UI Elements
        ttk.Label(self.root, text="Camera ID (0 for default):").pack(pady=(5, 0))
        self.camera_id = ttk.Entry(self.root, justify="center")
        self.camera_id.insert(0, "0")
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
        ttk.Button(self.root, text="Start Studio", command=self.start_app, style="Accent.TButton").pack(pady=10)
        
    def start_app(self):
        w, h = map(int, self.cam_res.get().split('x'))
        cam_id_val = self.camera_id.get()
        
        self.settings = {
            "CAMERA_ID": int(cam_id_val) if cam_id_val.isdigit() else cam_id_val,
            "CAMERA_WIDTH": w,
            "CAMERA_HEIGHT": h,
            "CAMERA_FPS": 30,
            "BIREFNET_MODEL": self.biref_model.get(),
            "CORRIDORKEY_RES": int(self.ck_res.get()),
            "NDI_ENABLED": self.ndi_var.get(),
            "COMPUTE_DEVICE": self.device_var.get()
        }
        self.root.destroy()


def get_gpu_temperature_and_load():
    """Simple check of GPU temp and load using nvidia-smi."""
    try:
        # Get temperature and util.gpu for all GPUs
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
            encoding='utf-8'
        ).strip()
        if not output:
            return 0, 0
        
        # Take the first line (primary GPU)
        first_gpu = output.split('\n')[0]
        temp, load = first_gpu.split(',')
        return int(temp), int(load)
    except Exception:
        return 0, 0

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
    
    # Camera Capture
    cap = cv2.VideoCapture(cfg["CAMERA_ID"])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["CAMERA_WIDTH"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["CAMERA_HEIGHT"])
    cap.set(cv2.CAP_PROP_FPS, cfg["CAMERA_FPS"])
    
    cap_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logging.info(f"Capture started at {cap_width}x{cap_height}")
    
    # 3. Setup OpenCV Window and Live Controls
    cv2.namedWindow("CorridorKey Live Studio", cv2.WINDOW_NORMAL)
    
    def noop(x): pass
    cv2.createTrackbar("Despill (0-100)", "CorridorKey Live Studio", 100, 100, noop)
    cv2.createTrackbar("Despeckle", "CorridorKey Live Studio", 400, 1000, noop)
    cv2.createTrackbar("Erode/Dilate", "CorridorKey Live Studio", 10, 20, noop) # 10 = neutral
    cv2.createTrackbar("Refiner Strength", "CorridorKey Live Studio", 100, 200, noop) # 100 = 1.0
    cv2.createTrackbar("View: Grid(1)/Res(0)", "CorridorKey Live Studio", 1, 1, noop)
    cv2.createTrackbar("Scale %", "CorridorKey Live Studio", 50, 100, noop)
    
    frame_count = 0
    last_vram_clear = time.time()
    
    logging.info("Starting Main Loop... Press 'q' to quit.")
    
    while cap.isOpened():
        start_time = time.time()
        
        # GPU Monitoring & Skipping logic (only if critical temp)
        temp, load = get_gpu_temperature_and_load()
        if temp > 85:
            logging.warning(f"CRITICAL: GPU too hot ({temp}C)! Skipping frame.")
            # Clear buffer slightly
            cap.read() 
            time.sleep(0.1)
            continue
            
        # Optional: Warn if load is pinned but don't skip unless user wants to
        if load > 99:
             # Just a small delay to prevent complete system hang on some laptops
             time.sleep(0.005)
            
        ret, frame = cap.read()
        if not ret:
            logging.error("Failed to grab frame.")
            break
            
        # Get live slider values
        despill_val = cv2.getTrackbarPos("Despill (0-100)", "CorridorKey Live Studio") / 100.0
        despeckle_val = cv2.getTrackbarPos("Despeckle", "CorridorKey Live Studio")
        erode_val = cv2.getTrackbarPos("Erode/Dilate", "CorridorKey Live Studio") - 10
        refine_scale = cv2.getTrackbarPos("Refiner Strength", "CorridorKey Live Studio") / 100.0
            
        # Ensure BGR to RGB for processing
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Alpha Hint Layer (BiRefNet)
        pil_image = Image.fromarray(frame_rgb)
        
        # We need to account for dynamic models if resolution is none
        res = birefnet_handler.resolution
        if res is None:
            res = [int(int(r) // 32 * 32) for r in pil_image.size]
            birefnet_preprocessor = ImagePreprocessor(resolution=tuple(res))
            
        image_proc = birefnet_preprocessor.proc(pil_image).unsqueeze(0).to(device)
        if half_precision:
            image_proc = image_proc.half()
            
        with torch.no_grad():
            preds = birefnet_model(image_proc)[-1].sigmoid().cpu()
            
        pred = preds[0].squeeze()
        pred_pil = transforms.ToPILImage()(pred.float())
        
        # Resize alpha to original frame size
        mask = pred_pil.resize((frame_rgb.shape[1], frame_rgb.shape[0]))
        mask_np_255 = np.array(mask)
        
        # Apply Erode/Dilate to the hint mask
        if erode_val != 0:
            k_size = abs(erode_val) * 2 + 1
            kernel = np.ones((k_size, k_size), np.uint8)
            if erode_val < 0:
                mask_np_255 = cv2.erode(mask_np_255, kernel, iterations=1)
            else:
                mask_np_255 = cv2.dilate(mask_np_255, kernel, iterations=1)
        
        # Refinement Layer expects linear mask 0.0 - 1.0
        mask_linear = mask_np_255.astype(np.float32) / 255.0
        
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
            rgb_srgb = np.power(np.maximum(rgb_lin, 0), 1.0/2.2)
            
            # 3. Recombine and convert to uint8
            rgba_srgb = np.concatenate([rgb_srgb, alpha], axis=-1)
            rgba_out = (rgba_srgb * 255.0).clip(0, 255).astype(np.uint8)
            
            # 4. Send to NDI (ensure memory is contiguous)
            send_ndi_frame(ndi_sender, np.ascontiguousarray(rgba_out))
            
        # Latency Meter
        latency_ms = (time.time() - start_time) * 1000
        
        # VRAM Management
        frame_count += 1
        if time.time() - last_vram_clear > 10.0: # Clear cache every 10 seconds
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                torch.mps.empty_cache()
            gc.collect()
            last_vram_clear = time.time()
            
        # Visualization Modes
        view_mode = cv2.getTrackbarPos("View: Grid(1)/Res(0)", "CorridorKey Live Studio")
        scale_val = cv2.getTrackbarPos("Scale %", "CorridorKey Live Studio") / 100.0
        if scale_val < 0.1: scale_val = 0.1 # Minimum scale

        vis_res = (res_comp_srgb * 255.0).clip(0, 255).astype(np.uint8)
        vis_res = cv2.cvtColor(vis_res, cv2.COLOR_RGB2BGR)
        
        if view_mode == 1:
            # Side by side (Grid)
            vis_orig = frame
            vis_mask = cv2.cvtColor(mask_np_255, cv2.COLOR_GRAY2BGR)
            
            # Add labels
            cv2.putText(vis_orig, f"Original ({cap_width}x{cap_height})", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(vis_mask, "BiRefNet Alpha", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(vis_res, "CorridorKey Refined", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            grid = np.hstack((vis_orig, vis_mask, vis_res))
        else:
            # Result only
            cv2.putText(vis_res, "Live Output", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            grid = vis_res

        # Add Latency and Load info to the top right
        info_text = f"{latency_ms:.1f}ms | GPU: {load}% {temp}C"
        cv2.putText(grid, info_text, (grid.shape[1] - 300, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

        # Draw Message Log Overlay
        grid = message_log.draw(grid)

        # Apply Scaling
        if scale_val != 1.0:
            h, w = grid.shape[:2]
            grid = cv2.resize(grid, (int(w * scale_val), int(h * scale_val)))
            
        cv2.imshow("CorridorKey Live Studio", grid)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

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
