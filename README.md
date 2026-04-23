# CorridorKey – Live Studio Edition 🎬

Welcome to **CorridorKey Live Studio**, a specialized, real-time fork of the original CorridorKey neural network green screen keyer. 

This version was specifically built to run **live video feeds** from a webcam or capture card, automatically extracting the foreground subject *without a green screen*, and sending the clean, professional matte directly to OBS or vMix via NDI.

## 🌟 What makes this version special?
Unlike the original CorridorKey which focuses on rendering offline video clips frame-by-frame, the **Live Studio Edition** is built for speed and real-time broadcasting:
- **No Green Screen Needed:** Uses **BiRefNet** as a real-time Alpha Hint layer to dynamically detect the subject.
- **Pre-Launch GUI:** A simple interface to select your camera, resolutions, and stream settings without touching any code.
- **Live Tuning:** OpenCV sliders on the video window let you adjust *Despeckle* (noise reduction) and *Despill* (color correction) in real-time while you're live.
- **NDI Output:** Seamlessly sends the RGBA output as a virtual camera source ("CorridorKey Live") to your broadcasting software.
- **Auto VRAM Management:** Automatically clears GPU cache to prevent crashes during long streaming sessions.

## 💻 Hardware Requirements

- **Windows PC (Production):** To run this smoothly at high resolution (1080p+), you **must** use an NVIDIA RTX GPU with at least 8GB of VRAM (e.g., RTX 3060, 4070, or better). 
- **Mac / Apple Silicon (Testing):** This app *will* run on an M1/M2/M3 Mac (using the `mps` backend), but because it runs two heavy AI models back-to-back without Tensor Cores, you will get very low framerates. Use Mac for testing and UI layout, and Windows for the actual live studio.

## 🚀 Getting Started

1. **Install NDI Tools (Optional but Recommended):** If you plan to send the video to OBS, download the free NDI Tools for your OS.
2. **Start the Studio:**
   - **On Windows:** Double-click `Start_Live_Studio_Windows.bat`
   - **On Mac/Linux:** Open terminal and run `./Start_Live_Studio_MacLinux.sh`
3. **Automated Setup:** If this is your first time, the script will automatically install `uv` (the package manager), download all required Python libraries, and fetch the heavy AI model weights (CorridorKey & BiRefNet). Just press **J/Y** when prompted.
4. **The GUI:** Select your camera, pick your resolution (lower is faster), and click "Start Studio".
5. **OBS:** Add an "NDI Source" in OBS and select `CorridorKey Live`.

## 🤝 Credits & Acknowledgements

This live-streaming architecture and GUI implementation was created by **Eivind Røsstad Skeie**.

However, none of this would be possible without the incredible open-source work of the original creators and the AI community. Huge props to:
- **Niko Pueringer & Corridor Digital:** For creating the original, groundbreaking [CorridorKey](https://github.com/CorridorDigital/CorridorKey) unmixing model and framework.
- **ZhengPeng7:** For the incredibly accurate [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) (Bilateral Reference for High-Resolution Dichotomous Image Segmentation) which powers our real-time Alpha Hints.
- **NDI (Network Device Interface):** For providing the low-latency network protocol used to beam the video frames into OBS.

## 📜 Licensing

The original CorridorKey models and code are subject to the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/). You may not repackage this tool and sell it, and any variations must remain under the same license and include the name CorridorKey.
