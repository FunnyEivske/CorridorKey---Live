# 🚀 CorridorKey Live Studio: Full User Guide

This guide covers everything from the first installation to streaming your perfect green-screen key directly into OBS.

---

## 🛠 1. First-Time Installation

I have designed the installation to be as automated as possible. Follow these steps:

### Prerequisites
1.  **NVIDIA GPU**: Ensure you have an NVIDIA GPU (RTX series recommended).
2.  **NVIDIA Drivers**: Make sure your drivers are up to date.

### Installation Steps
1.  **Clone/Download this Folder**: Get the project files onto your PC.
2.  **Run the Starter**: Double-click the file named:
    `▶ Start_Live_Studio_Windows.bat`
3.  **Automatic Setup**: 
    - The script will check for everything you need: Python, dependencies, and AI models.
    - **NDI Auto-Install**: It will even check if you have the **NDI Runtime** installed. If not, it will ask to download and install it for you!
    - **Note**: On the first run, it might take 5-10 minutes to download everything (AI models + libraries).

---

## 🎥 2. Linking to OBS (The NDI Way)
 
This is the professional way to get your video into OBS with full transparency (alpha channel).

### In CorridorKey Live Studio:
1.  Run the `.bat` file.
2.  In the setup window, ensure **"Enable NDI Stream"** is checked.
3.  Select **CUDA** as your Compute Device for maximum speed.
4.  Click **Start Studio**.

### In OBS Studio:
1.  **Install NDI Plugin**: Ensure you have the "OBS-NDI" plugin installed in OBS. (Download it [here](https://github.com/obs-ndi/obs-ndi/releases) if you don't have it).
2.  **Add Source**: Click the `+` icon in your Sources and select **NDI™ Source**.
3.  **Select Source**: In the dropdown, look for **"CorridorKey Live"**.
4.  **Set Mode**: Set the "Bandwidth" to **Highest** and "Allow Hardware Acceleration" to **On**.
5.  **Done!** Your key will now appear in OBS with a transparent background. You can move yourself around like any other source.

---

## 🎛 3. How to Use & Get a Perfect Key

Once the studio is running, use the sliders on the top of the window to tune your image:

*   **View: Grid(1)/Res(0)**: Switch to **0** if you just want to see yourself, or **1** to see the AI's "thought process".
*   **Scale %**: If the window is taking up too much of your screen, slide this down to 50%.
*   **Erode/Dilate**: **This is your most important tool.** If you see "ghosts" or background blobs, slide this to the **left** (below 10) to tighten the mask around you.
*   **Despeckle**: If there are small dots or "islands" floating in the background, slide this to the **right** to delete them.
*   **Despill**: Adjust this if you see green reflections on your skin or clothes.
*   **Refiner Strength**: If the edges of your hair look too sharp or weird, lower this value.

---

## ❓ Troubleshooting

*   **"Running on CPU" warning**: If you see a big warning in the console, your GPU isn't being used. Make sure you select **CUDA** in the setup window and that your NVIDIA drivers are installed.
*   **NDI Source not showing in OBS**: Restart OBS *after* starting the Live Studio. Ensure both are on the same local network (usually not an issue on a single PC).
*   **Slow Frame Rate**: Ensure you aren't running other heavy games or apps on the GPU at the same time. The A1000 is a great chip, but AI keying is demanding!

---

**Enjoy your perfect keys!** 🎬
