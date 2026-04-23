#!/usr/bin/env bash
echo "==================================================="
echo "    CorridorKey Live Studio - Starter"
echo "==================================================="
echo ""

# Sørg for at uv kan bli funnet selv om det nettopp er installert
export PATH="$HOME/.local/bin:$PATH"

prompt_install() {
    echo "[Advarsel] Det ser ut til at nødvendige verktøy, pakker eller AI-modeller mangler."
    echo "Dette kan være uv (pakkebehandler), biblioteker eller CorridorKey-modellen."
    read -p "Vil du laste ned og installere alt som mangler nå? (J/N): " DO_INSTALL

    if [[ "$DO_INSTALL" =~ ^[JjYy]$ ]]; then
        echo ""
        echo "Starter oppsett..."

        # 1. Installer uv hvis det mangler
        if ! command -v uv &> /dev/null; then
            echo "[INFO] Laster ned og installerer pakkebehandleren 'uv'..."
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi

        # 2. Installer Python-pakker
        echo "[INFO] Installerer avhengigheter (OpenCV, NDI, PyTorch, osv.)..."
        if [ "$(uname)" == "Darwin" ]; then
            uv sync --extra live --extra mlx
        else
            uv sync --extra live --extra cuda
        fi
        if [ $? -ne 0 ]; then
            echo "[FEIL] Installasjon av avhengigheter feilet."
            exit 1
        fi

        # 3. Last ned CorridorKey-vekter hvis de mangler
        echo "[INFO] Sjekker AI-modeller..."
        mkdir -p CorridorKeyModule/checkpoints
        CKPT_DIR="CorridorKeyModule/checkpoints"
        SAFETENSORS_PATH="$CKPT_DIR/CorridorKey.safetensors"
        PTH_PATH="$CKPT_DIR/CorridorKey_v1.0.pth"
        HF_BASE="https://huggingface.co/nikopueringer/CorridorKey_v1.0/resolve/main"

        if [ -f "$SAFETENSORS_PATH" ] || [ -f "$PTH_PATH" ]; then
            echo "CorridorKey modell funnet."
        else
            echo "[INFO] Laster ned CorridorKey modell (dette kan ta litt tid)..."
            curl -L -f -o "$SAFETENSORS_PATH" "$HF_BASE/CorridorKey_v1.0.safetensors"
            if [ $? -ne 0 ]; then
                rm -f "$SAFETENSORS_PATH"
                curl -L -o "$PTH_PATH" "$HF_BASE/CorridorKey_v1.0.pth"
            fi
        fi

        echo ""
        echo "[INFO] Oppsett fullført!"
        echo ""
    else
        echo ""
        echo "Avbryter oppstarten. Du må ha disse filene for å kunne kjøre programmet."
        exit 1
    fi
}

# Sjekk for uv
if ! command -v uv &> /dev/null; then
    prompt_install
# Sjekk for virtuelt miljø
elif [ ! -d ".venv" ]; then
    prompt_install
# Sjekk for modell-vekter
elif [ ! -f "CorridorKeyModule/checkpoints/CorridorKey_v1.0.pth" ] && [ ! -f "CorridorKeyModule/checkpoints/CorridorKey.safetensors" ] && [ ! -f "CorridorKeyModule/checkpoints/CorridorKey.pth" ]; then
    prompt_install
fi

echo "==================================================="
echo "    Starter Live Studio..."
echo "==================================================="
uv run live_studio.py
if [ $? -ne 0 ]; then
    echo ""
    echo "[FEIL] Programmet avsluttet med en feil."
fi
