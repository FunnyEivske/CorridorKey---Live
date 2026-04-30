import os
import zipfile

def create_zip():
    zip_name = "CorridorKey_Live_Installer.zip"
    
    # Folders and files to exclude from the zip to keep it lightweight
    exclude_dirs = {'.venv', '.git', '__pycache__', 'checkpoints', 'build', 'dist', '.github'}
    exclude_files = {zip_name, 'studio_log.txt', 'build_exe.py', 'autostart_config.json'}
    
    print("Gathering files for distribution...")
    
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('.'):
            # Mutate dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file in exclude_files or file.endswith('.pyc'):
                    continue
                
                file_path = os.path.join(root, file)
                # Ensure the path in the zip is relative to the root folder
                arcname = "CorridorKey_Live_Studio/" + os.path.relpath(file_path, '.')
                zipf.write(file_path, arcname)
                
    # Get file size in MB
    size_mb = os.path.getsize(zip_name) / (1024 * 1024)
    print(f"\n[SUCCESS] Created {zip_name}")
    print(f"[INFO] File Size: {size_mb:.2f} MB")
    print("\nSend this ZIP file to other users. All they need to do is unzip it and run 'Start_Live_Studio_Windows.bat'.")

if __name__ == "__main__":
    create_zip()
