import time
import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms
import NDIlib as ndi
import subprocess
import gc
import sys
import tkinter as tk
from tkinter import ttk

# CorridorKey and BiRefNet imports
from CorridorKeyModule.inference_engine import CorridorKeyEngine
from BiRefNetModule.wrapper import BiRefNetHandler, ImagePreprocessor


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
        
        self.ndi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.root, text="Enable NDI Stream", variable=self.ndi_var).pack(pady=20)
        
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
            "NDI_ENABLED": self.ndi_var.get()
        }
        self.root.destroy()


def get_gpu_temperature_and_load():
    """Simple check of GPU temp and load using nvidia-smi."""
    try:
        # Get temperature and util.gpu
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
            encoding='utf-8'
        )
        temp, load = output.strip().split(',')
        return int(temp), int(load)
    except Exception:
        return 0, 0

def create_ndi_sender(name="CorridorKey Live"):
    """Create NDI Video Sender."""
    if not ndi.initialize():
        print("Cannot run NDI.")
        return None
    ndi_send_create_desc = ndi.SendCreate()
    ndi_send_create_desc.ndi_name = name
    ndi_send = ndi.send_create(ndi_send_create_desc)
    if ndi_send is None:
        print("Error creating NDI sender")
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
        print("Setup cancelled. Exiting.")
        return
        
    cfg = launcher.settings

    print("Initialize CorridorKey Live Studio...")
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
        
    half_precision = True if device != "cpu" else False
    
    # 2. Model Loader
    print(f"Loading Models onto {device} in FP16...")
    
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
    
    print("Models Loaded.")
    
    # NDI Integration
    ndi_sender = create_ndi_sender("CorridorKey Live") if cfg["NDI_ENABLED"] else None
    
    # Camera Capture
    cap = cv2.VideoCapture(cfg["CAMERA_ID"])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["CAMERA_WIDTH"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["CAMERA_HEIGHT"])
    cap.set(cv2.CAP_PROP_FPS, cfg["CAMERA_FPS"])
    
    cap_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Capture started at {cap_width}x{cap_height}")
    
    # 3. Setup OpenCV Window and Live Controls
    cv2.namedWindow("CorridorKey Live Studio", cv2.WINDOW_NORMAL)
    
    def noop(x): pass
    cv2.createTrackbar("Despill (0-100)", "CorridorKey Live Studio", 100, 100, noop)
    cv2.createTrackbar("Despeckle", "CorridorKey Live Studio", 400, 1000, noop)
    
    frame_count = 0
    last_vram_clear = time.time()
    
    print("Starting Main Loop... Press 'q' to quit.")
    
    while cap.isOpened():
        start_time = time.time()
        
        # GPU Monitoring & Skipping logic
        temp, load = get_gpu_temperature_and_load()
        if temp > 85 or load > 95:
            print(f"WARNING: GPU too hot ({temp}C) or overloaded ({load}%). Skipping frame.")
            # Clear buffer slightly
            cap.read() 
            time.sleep(0.05)
            continue
            
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break
            
        # Get live slider values
        despill_val = cv2.getTrackbarPos("Despill (0-100)", "CorridorKey Live Studio") / 100.0
        despeckle_val = cv2.getTrackbarPos("Despeckle", "CorridorKey Live Studio")
            
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
        
        # Refinement Layer expects linear mask 0.0 - 1.0
        mask_linear = mask_np_255.astype(np.float32) / 255.0
        
        # Refinement Layer (CorridorKey)
        ck_out = ck_engine.process_frame(
            image=frame_rgb,
            mask_linear=mask_linear,
            generate_comp=True,
            auto_despeckle=(despeckle_val > 0),
            despeckle_size=despeckle_val,
            despill_strength=despill_val,
            post_process_on_gpu=True
        )
        
        # The result includes: alpha, fg, comp, processed (RGBA)
        res_comp_srgb = ck_out['comp'] # 0.0 - 1.0 composite on checkboard
        res_processed_rgba = ck_out['processed'] # 0.0 - 1.0 linear RGBA
        
        # NDI Output (requires 0-255 RGBA uint8)
        if ndi_sender:
            rgba_out = (res_processed_rgba * 255.0).clip(0, 255).astype(np.uint8)
            send_ndi_frame(ndi_sender, rgba_out)
            
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
            
        # Visualization (Side by side)
        vis_orig = frame
        vis_mask = cv2.cvtColor(mask_np_255, cv2.COLOR_GRAY2BGR)
        vis_ck = (res_comp_srgb * 255.0).clip(0, 255).astype(np.uint8)
        vis_ck = cv2.cvtColor(vis_ck, cv2.COLOR_RGB2BGR)
        
        # Resize to fit on screen if 1080p is too big
        h, w = vis_orig.shape[:2]
        scale = 0.5 if w > 1280 else 1.0
        new_w, new_h = int(w * scale), int(h * scale)
        
        vis_orig = cv2.resize(vis_orig, (new_w, new_h))
        vis_mask = cv2.resize(vis_mask, (new_w, new_h))
        vis_ck = cv2.resize(vis_ck, (new_w, new_h))
        
        # Add text overlays
        cv2.putText(vis_orig, f"Latency: {latency_ms:.1f} ms", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(vis_mask, "BiRefNet Alpha", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(vis_ck, "CorridorKey Refined", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        grid = np.hstack((vis_orig, vis_mask, vis_ck))
        
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
    main()
