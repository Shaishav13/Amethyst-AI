import os

filepath = r"d:\project2.0\AI_Assistant\ui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

replacements = {
    # Message bubbles
    '"👤", "You"': '"USR", "GUEST_USER"',
    '"⚡", "Qwen Coder"': '"[X]", "QWEN_CORE"',
    '"✦", "Amethyst"': '"::", "AMETHYST_SYS"',
    'icon = "⚡" if "qwen"': 'icon = "[X]" if "qwen"',
    'icon = "✦"': 'icon = "::"',
    'name = "Qwen Coder" if "qwen"': 'name = "QWEN_CORE" if "qwen"',
    'name = "Amethyst"': 'name = "AMETHYST_SYS"',

    # Topbar
    'text="🗑 Clear"': 'text="[WIPE]"',
    'text="IDE 🔗"': 'text="[IDE]"',
    'text="⚙️"': 'text="[CFG]"',
    'text="📸"': 'text="[VIS]"',
    'text="💻"': 'text="[SYS]"',
    'text="⚙️ AI Parameters"': 'text=":: SYSTEM PARAMETERS ::"',

    # Input bar
    'text="📎"': 'text="[+]"',
    'text="🎤"': 'text="[MIC]"',
    'text="🔊"': 'text="[SND_ON]"',
    'text="🔇"': 'text="[SND_OFF]"',
    'text="Send  ➤"': 'text="EXEC //"',
    '"📄 " + doc["name"]': '"[DOC] " + doc["name"]',
    
    # Welcome screen
    '"✦ Amethyst"': '":: AMETHYST_OS ::"',
    '"⚡ Code & Debug"': '"[X] CODE_EXEC"',
    '"💬 Chat & Explain"': '"[~] NLP_CHAT"',
    '"🎤 Voice Input"': '"[MIC] AUDIO_IN"',
    '"🔗 IDE Bridge"': '"[IDE] SYS_BRIDGE"',
    '"📚 Knowledge Base"': '"[DB] VECTOR_STORE"',
    '"📸 Screenshot"': '"[VIS] OPTIC_SENSOR"',
    '"💻 System Status"': '"[SYS] DIAGNOSTICS"',

    # Status messages
    '"📸 Capturing screenshot..."': '"[SYS.VIS] Capturing optic feed..."',
    '"📸 Analyzing with {self._vision.model_name}..."': '"[SYS.VIS] Processing via {self._vision.model_name}..."',
    '"📸 Screenshot analysis complete."': '"[SYS.VIS] Optic analysis complete."',
    '"⚡ Generating response..."': '"[SYS.CORE] Computing response..."',
    '"📚 Answering with knowledge base context..."': '"[SYS.DB] Retrieving vector data..."',
    'f"✦ Response via {model_label}"': 'f"[SYS.CORE] Output via {model_label}"',
    '"🎤 Listening..."': '"[SYS.MIC] Awaiting audio input..."',
    '"⚙️ Processing speech..."': '"[SYS.MIC] Decoding waveform..."',
    '"❌ Voice error"': '"[SYS.ERR] Audio failure"',
    '"✦ Ready"': '"[SYS.IDLE] Awaiting input."',
    '"🎤 No speech detected. Try again."': '"[SYS.MIC] Zero amplitude detected."',
    '"🔇 Voice muted"': '"[SYS.SND] Output suppressed."',
    '"🔊 Voice enabled"': '"[SYS.SND] Output active."',
    '"🔗 IDE Bridge Active"': '"[SYS.IDE] Bridge Established"',
    '"⚠️ SYSTEM:"': '"[SYS.WARN]"',
    '"⚠️  No models found': '"[SYS.ERR] Core models missing',
    '"⚠️  qwen2.5-coder:7b not found': '"[SYS.ERR] qwen2.5-coder:7b missing',
    '"⚠️  gemma3:4b not found': '"[SYS.ERR] gemma3:4b missing',
    '"✅ All models online"': '"[SYS.INIT] Core models online"',
    '"👁 Vision:"': '"[VIS]:"',
    '"📚 Knowledge base: {rag_count} chunks ready"': '"[SYS.DB] Vector store online ({rag_count} objects)"',
    '"🔍 Searching the web for real-time information..."': '"[SYS.NET] Querying external networks..."',
    '"📎 Ingesting into Vector DB (this may take a moment)..."': '"[SYS.DB] Ingesting documents into vector space..."',
    '"✅ Indexed {len(paths)} docs': '"[SYS.DB] Vectorized {len(paths)} docs',
    '"Amethyst ready"': '"[SYS.INIT] System nominal. Ready."',
    
    # Miscellaneous
    'text="📋 Copy"': 'text="[COPY]"',
    'text="✓ Copied!"': 'text="[OK]"',
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("UI updated for sci-fi theme.")
