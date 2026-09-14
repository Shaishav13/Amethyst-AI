"""
Amethyst Setup - installs all dependencies and verifies Ollama connection
Run once before launching: python setup.py
"""
import subprocess
import sys
import os

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(cmd, check=True):
    print(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ⚠  Error: {result.stderr.strip()}")
        return False
    return True


def install_packages():
    print("\n📦 Installing Python packages...")
    packages = [
        "ollama",
        "customtkinter",
        "Pillow",
        "SpeechRecognition",
        "pyttsx3",
        "vosk",
        "pyperclip",
        "keyboard",
        "pywin32",
        "pymupdf",
        "httpx",
        "aiofiles",
        "pygments",
    ]
    for pkg in packages:
        print(f"  Installing {pkg}...")
        run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", pkg])

    # pyaudio needs special handling on Windows
    print("  Installing pyaudio (may need Microsoft C++ Build Tools)...")
    ok = run([sys.executable, "-m", "pip", "install", "--quiet", "pyaudio"], check=False)
    if not ok:
        print("  ⚠  pyaudio failed — trying pipwin fallback...")
        run([sys.executable, "-m", "pip", "install", "--quiet", "pipwin"], check=False)
        run([sys.executable, "-m", "pipwin", "install", "pyaudio"], check=False)

    print("  ✅ Packages installed.")


def check_ollama():
    print("\n🔍 Checking Ollama...")
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ Ollama not found or not running.")
        print("     Download: https://ollama.com/download")
        print("     Then run: ollama serve")
        return False

    output = result.stdout
    print(f"  Available models:\n{output}")

    models = {"gemma3:4b": False, "qwen2.5-coder:7b": False}
    for model in models:
        if model in output:
            models[model] = True
            print(f"  ✅ {model}")
        else:
            print(f"  ❌ {model} — pull with: ollama pull {model}")

    return True


def main():
    print("=" * 50)
    print("  [*] Amethyst AI Assistant - Setup")
    print("=" * 50)

    install_packages()
    check_ollama()

    print("\n" + "=" * 50)
    print("  Setup complete! Launch with:")
    print("    python ui_main.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
