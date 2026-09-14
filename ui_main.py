"""
Amethyst AI Assistant — Main UI
Framework: CustomTkinter (dark glassmorphism theme)
"""

import asyncio
import threading
import time
import re
import sys
import os
import queue
import logging
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import tkinter as tk
from tkinter import scrolledtext

from ai_engine import AmethystEngine, ModelType, RouterDecision
from voice_engine import VoiceManager, VoiceState
from ide_bridge import IDEBridge
from memory_manager import MemoryManager, StoredSession, StoredMessage

log = logging.getLogger("amethyst.ui")
logging.basicConfig(level=logging.INFO)

# ── Theme Constants ───────────────────────────────────────────────────────────
C = {
    "bg_deep":      "#1E1E1E",   # VSCode background
    "bg_panel":     "#252526",   # VSCode sidebar
    "bg_card":      "#2D2D30",   # VSCode widget background
    "bg_input":     "#3C3C3C",   # VSCode input box
    "bg_hover":     "#2A2D2E",   # VSCode hover
    "accent":       "#007ACC",   # VSCode Blue
    "accent_dim":   "#005C99",
    "accent_glow":  "#3794FF",
    "qwen_color":   "#4EC9B0",   # Class Green
    "gemma_color":  "#DCDCAA",   # Function Yellow
    "user_color":   "#CE9178",   # String Orange
    "text_primary": "#CCCCCC",
    "text_muted":   "#858585",
    "text_dim":     "#6B6B6B",
    "border":       "#454545",
    "border_accent":"#007ACC",
    "success":      "#89D185",
    "warning":      "#CCA700",
    "error":        "#F14C4C",
    "code_bg":      "#1E1E1E",
    "sidebar_w":    260,
}

FONT_FAMILY = "Segoe UI"


# ── Async Bridge ─────────────────────────────────────────────────────────────
class AsyncBridge:
    """Runs asyncio event loop in a background thread; lets UI post coroutines safely."""

    def __init__(self):
        self._loop   = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="async-bridge")
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self):
        self._loop.call_soon_threadsafe(self._loop.stop)


# ── Chat Session ─────────────────────────────────────────────────────────────
class ChatSession:
    def __init__(self, title: str = "New Chat"):
        self.title     = title
        self.created   = datetime.now()
        self.messages  = []  # list of (role, text, model_label)

    def add(self, role: str, text: str, model_label: str = ""):
        self.messages.append((role, text, model_label))

    @property
    def preview(self) -> str:
        for role, text, _ in self.messages:
            if role == "user":
                return text[:40] + "..." if len(text) > 40 else text
        return "Empty chat"


# ── Sidebar Widget ────────────────────────────────────────────────────────────
class Sidebar(ctk.CTkFrame):
    def __init__(self, master, on_new_chat, on_select_session, on_clear_all,
                 on_resume_session=None, on_delete_session=None, **kw):
        super().__init__(master, width=C["sidebar_w"], fg_color=C["bg_panel"],
                         corner_radius=0, **kw)
        self.on_new_chat        = on_new_chat
        self.on_select_session  = on_select_session
        self.on_clear_all       = on_clear_all
        self.on_resume_session  = on_resume_session
        self.on_delete_session  = on_delete_session  # NEW

        self._session_frames    = []
        self._model_labels      = {}
        self._mem_panel         = None
        self._build()

    def _build(self):
        self.grid_propagate(False)
        self.configure(width=C["sidebar_w"])

        # Logo area
        logo_frame = ctk.CTkFrame(self, fg_color="transparent")
        logo_frame.pack(fill="x", padx=12, pady=(16, 8))

        ctk.CTkLabel(logo_frame, text="SYS_AMETHYST",
                     font=(FONT_FAMILY, 18, "bold"),
                     text_color=C["accent_glow"]).pack(anchor="w")
        ctk.CTkLabel(logo_frame, text="Local AI Assistant",
                     font=(FONT_FAMILY, 10),
                     text_color=C["text_dim"]).pack(anchor="w")

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).pack(fill="x", padx=12, pady=4)

        # New Chat button
        ctk.CTkButton(self, text="[ + ]  NEW TERMINAL",
                      font=(FONT_FAMILY, 12, "bold"),
                      fg_color="transparent", hover_color=C["bg_card"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_primary"], corner_radius=2, height=36,
                      command=self.on_new_chat).pack(fill="x", padx=12, pady=6)

        # Model status
        status_frame = ctk.CTkFrame(self, fg_color=C["bg_card"], corner_radius=10)
        status_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(status_frame, text="MODEL STATUS",
                     font=(FONT_FAMILY, 9, "bold"),
                     text_color=C["text_dim"]).pack(anchor="w", padx=10, pady=(8,2))

        self._model_dropdowns = {}
        for key, default_text, color in [
            ("coder", "qwen2.5-coder:7b", C["qwen_color"]),
            ("chat",  "gemma3:4b",         C["gemma_color"]),
        ]:
            row = ctk.CTkFrame(status_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            dot = ctk.CTkLabel(row, text="●", font=(FONT_FAMILY, 10),
                               text_color=color, width=14)
            dot.pack(side="left")
            
            def _on_switch(val, k=key):
                if k == "coder": self.master._engine.resolved_coder = val
                else: self.master._engine.resolved_chat = val
                
            dropdown = ctk.CTkOptionMenu(row, values=[default_text],
                                         font=(FONT_FAMILY, 10),
                                         fg_color=C["bg_panel"],
                                         button_color=C["accent"],
                                         button_hover_color=C["accent_dim"],
                                         text_color=C["text_primary"],
                                         height=24, width=140,
                                         command=_on_switch)
            dropdown.set(default_text)
            dropdown.pack(side="left", padx=4)
            self._model_dropdowns[key] = dropdown

        ctk.CTkFrame(status_frame, height=8, fg_color="transparent").pack()

        # Chat history label
        ctk.CTkLabel(self, text="RECENT CHATS",
                     font=(FONT_FAMILY, 9, "bold"),
                     text_color=C["text_dim"]).pack(anchor="w", padx=16, pady=(12, 4))

        # Scrollable session list
        self.session_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=C["border"])
        self.session_scroll.pack(fill="both", expand=True, padx=8)

        # Bottom controls
        btm = ctk.CTkFrame(self, fg_color="transparent")
        btm.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(btm, text="Clear All", font=(FONT_FAMILY, 11),
                      fg_color=C["bg_card"], hover_color=C["bg_hover"],
                      text_color=C["text_muted"], corner_radius=8, height=30,
                      command=self.on_clear_all).pack(fill="x")

    def update_model_status(self, coder_ok: bool, chat_ok: bool):
        for key, ok in [("coder", coder_ok), ("chat", chat_ok)]:
            lbl = self._model_labels.get(key)
            if lbl:
                lbl.configure(text_color=C["success"] if ok else C["error"])

    def add_session_button(self, session, idx: int):
        title        = getattr(session, "title", "New Chat")
        is_resumable = getattr(session, "is_resumable", False)
        container    = ctk.CTkFrame(self.session_scroll, fg_color="transparent")
        container.pack(fill="x", pady=1)
        container.grid_columnconfigure(0, weight=1)
        
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkButton(
            btn_frame, text="Chat: " + title[:20],
            font=(FONT_FAMILY, 11), fg_color="transparent",
            hover_color=C["bg_hover"], text_color=C["text_muted"],
            anchor="w", corner_radius=8, height=28,
            command=lambda i=idx: self.on_select_session(i)
        ).grid(row=0, column=0, sticky="ew")
        
        if self.on_delete_session:
            ctk.CTkButton(
                btn_frame, text="❌", width=28,
                font=(FONT_FAMILY, 10), fg_color="transparent",
                hover_color=C["error"], text_color=C["text_muted"],
                anchor="center", corner_radius=8, height=28,
                command=lambda i=idx: self.on_delete_session(i)
            ).grid(row=0, column=1, padx=(2, 0))
            
        self._session_frames.append(container)
        if is_resumable and self.on_resume_session:
            ctk.CTkButton(
                container, text="Resume",
                font=(FONT_FAMILY, 10, "bold"),
                fg_color=C["accent"], hover_color=C["accent_dim"],
                text_color="white", corner_radius=6, height=22,
                command=lambda i=idx: self.on_resume_session(i)
            ).grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 3))

    def clear_sessions(self):
        for w in self._session_frames:
            w.destroy()
        self._session_frames.clear()

    def show_memory_panel(self, memory_lines: list):
        if hasattr(self, "_mem_panel") and self._mem_panel:
            try:
                self._mem_panel.destroy()
            except Exception:
                pass
        if not memory_lines:
            return
        self._mem_panel = ctk.CTkFrame(self, fg_color=C["bg_card"], corner_radius=10)
        self._mem_panel.pack(fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(self._mem_panel, text="MEMORY",
                     font=(FONT_FAMILY, 9, "bold"),
                     text_color=C["accent"]).pack(anchor="w", padx=10, pady=(6, 2))
        icons = {"fact": "F", "pref": "*", "project": "P"}
        for kind, text in memory_lines[:6]:
            row = ctk.CTkFrame(self._mem_panel, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=1)
            ctk.CTkLabel(row, text=icons.get(kind, "*") + " " + text[:34],
                         font=(FONT_FAMILY, 9), text_color=C["text_muted"],
                         anchor="w", wraplength=200).pack(side="left", padx=4)
        ctk.CTkFrame(self._mem_panel, height=6, fg_color="transparent").pack()


# ── Message Bubble ────────────────────────────────────────────────────────────
class MessageBubble(ctk.CTkFrame):
    """A single chat message — user or AI — with optional code block rendering."""

    def __init__(self, master, role: str, text: str, model_label: str = "", **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.role        = role
        self.full_text   = text
        self.model_label = model_label
        self._build(role, text, model_label)

    def _build(self, role: str, text: str, model_label: str):
        self.grid_columnconfigure(0, weight=1)

        # Header row
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(8, 2))

        if role == "user":
            icon, name, name_color = "USR", "GUEST_USER", C["user_color"]
        elif "qwen" in model_label.lower() or role == "coder":
            icon, name, name_color = "[X]", "QWEN_CORE", C["qwen_color"]
        else:
            icon, name, name_color = "::", "AMETHYST_SYS", C["accent_glow"]

        ctk.CTkLabel(hdr, text=f"{icon} {name}",
                     font=(FONT_FAMILY, 12, "bold"),
                     text_color=name_color).pack(side="left", padx=14)

        ts = datetime.now().strftime("%H:%M")
        ctk.CTkLabel(hdr, text=ts, font=(FONT_FAMILY, 10),
                     text_color=C["text_dim"]).pack(side="left", padx=4)

        if model_label and role != "user":
            ctk.CTkLabel(hdr, text=f"via {model_label}",
                         font=(FONT_FAMILY, 9),
                         text_color=C["text_dim"]).pack(side="right", padx=14)

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).grid(
            row=1, column=0, sticky="ew", padx=10)

        # Content — split code blocks from prose
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=2, column=0, sticky="ew")
        content_frame.grid_columnconfigure(0, weight=1)

        self._render_content(content_frame, text, role)

    def _render_content(self, parent, text: str, role: str):
        """Parse and render prose + code blocks separately."""
        CODE_PAT = re.compile(r"```(\w*)\n?([\s\S]*?)```", re.MULTILINE)
        parts    = []
        last_end = 0

        for m in CODE_PAT.finditer(text):
            if m.start() > last_end:
                parts.append(("prose", text[last_end:m.start()]))
            parts.append(("code", m.group(2), m.group(1) or "text"))
            last_end = m.end()
        if last_end < len(text):
            parts.append(("prose", text[last_end:]))

        row_idx = 0
        bg = C["bg_card"] if role == "user" else C["bg_panel"]

        for part in parts:
            if part[0] == "prose" and part[1].strip():
                prose_frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=2, border_width=1, border_color=C["border"])
                prose_frame.grid(row=row_idx, column=0, sticky="ew",
                                 padx=12, pady=4)
                prose_frame.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(
                    prose_frame, text=part[1].strip(),
                    font=(FONT_FAMILY, 13), text_color=C["text_primary"],
                    wraplength=680, justify="left", anchor="w"
                ).grid(row=0, column=0, sticky="ew", padx=14, pady=10)
                row_idx += 1

            elif part[0] == "code":
                lang     = part[2]
                code_txt = part[1].strip()
                self._render_code_block(parent, row_idx, code_txt, lang)
                row_idx += 1

    def _render_code_block(self, parent, row_idx: int, code: str, lang: str):
        """Render a styled code block with Copy button."""
        container = ctk.CTkFrame(parent, fg_color=C["code_bg"],
                                  corner_radius=2, border_width=1,
                                  border_color=C["border"])
        container.grid(row=row_idx, column=0, sticky="ew", padx=12, pady=4)
        container.grid_columnconfigure(0, weight=1)

        # Code header bar
        hdr = ctk.CTkFrame(container, fg_color=C["bg_card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text=f"  {lang.upper() or 'CODE'}",
                     font=(FONT_FAMILY, 10, "bold"),
                     text_color=C["text_dim"]).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        copy_btn = ctk.CTkButton(
            hdr, text="[COPY]", font=(FONT_FAMILY, 10),
            fg_color=C["bg_card"], hover_color=C["bg_hover"],
            text_color="white", corner_radius=2, height=22, width=60,
            command=lambda c=code: self._copy(c, copy_btn)
        )
        copy_btn.grid(row=0, column=1, sticky="e", padx=8, pady=4)

        # Code text box (read-only)
        txt = ctk.CTkTextbox(container, font=("Cascadia Code", 12),
                             fg_color=C["code_bg"], text_color="#D4D4FF",
                             corner_radius=0, wrap="none",
                             border_width=0, height=min(400, max(80, code.count("\n") * 20 + 60)))
        txt.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        txt.insert("1.0", code)
        txt.configure(state="disabled")

    @staticmethod
    def _copy(code: str, btn: ctk.CTkButton):
        import pyperclip
        try:
            pyperclip.copy(code)
            original = btn.cget("text")
            btn.configure(text="[OK]", fg_color=C["success"])
            btn.after(1800, lambda: btn.configure(text=original, fg_color=C["accent_dim"]))
        except Exception:
            pass

    def append_token(self, token: str):
        """Append a streamed token to the last prose block if possible."""
        self.full_text += token


# ── Streaming Message Bubble ──────────────────────────────────────────────────
class StreamingBubble(ctk.CTkFrame):
    """Lightweight bubble used during live streaming — replaced by MessageBubble on finish."""

    def __init__(self, master, model_label: str = "", **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._text_var = tk.StringVar(value="")
        self._full     = ""
        self._build(model_label)

    def _build(self, model_label: str):
        self.grid_columnconfigure(0, weight=1)
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(8, 2))

        icon = "[X]" if "qwen" in model_label.lower() else "✦"
        name = "QWEN_CORE" if "qwen" in model_label.lower() else "Amethyst"
        color = C["qwen_color"] if "qwen" in model_label.lower() else C["accent_glow"]

        ctk.CTkLabel(hdr, text=f"{icon} {name}",
                     font=(FONT_FAMILY, 12, "bold"),
                     text_color=color).pack(side="left", padx=14)

        ctk.CTkFrame(self, height=1, fg_color=C["border"]).grid(
            row=1, column=0, sticky="ew", padx=10)

        card = ctk.CTkFrame(self, fg_color=C["bg_panel"], corner_radius=2, border_width=1, border_color=C["border"])
        card.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        card.grid_columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(card, textvariable=self._text_var,
                                   font=(FONT_FAMILY, 13),
                                   text_color=C["text_primary"],
                                   wraplength=680, justify="left", anchor="w")
        self._label.grid(row=0, column=0, sticky="ew", padx=14, pady=10)

    def append(self, token: str):
        self._full += token
        # Show last 2000 chars to avoid label overload
        display = self._full[-2000:] if len(self._full) > 2000 else self._full
        self._text_var.set(display + " ▌")

    def finalize(self):
        self._text_var.set(self._full)
        return self._full


# ── Input Bar ─────────────────────────────────────────────────────────────────
class InputBar(ctk.CTkFrame):
    def __init__(self, master, on_send, on_voice, on_mute_toggle, on_attach=None, **kw):
        super().__init__(master, fg_color=C["bg_deep"], corner_radius=0,
                         border_width=1, border_color=C["border"], **kw)
        self.on_send        = on_send
        self.on_voice       = on_voice
        self.on_mute_toggle = on_mute_toggle
        self.on_attach      = on_attach
        self._muted         = False
        self._voice_active  = False
        self._build()

    def _build(self):
        # Top row for attachments
        self.attach_frame = ctk.CTkFrame(self, fg_color="transparent", height=0)
        self.attach_frame.grid(row=0, column=0, columnspan=5, sticky="ew", padx=12)
        
        self.grid_columnconfigure(2, weight=1)

        # Attach button
        self.attach_btn = ctk.CTkButton(
            self, text="[+]", width=42, height=42,
            font=(FONT_FAMILY, 18), fg_color="transparent",
            hover_color=C["bg_card"], corner_radius=2,
            command=self.on_attach if self.on_attach else lambda: None
        )
        self.attach_btn.grid(row=1, column=0, padx=(12, 4), pady=10)

        # Mic button
        self.mic_btn = ctk.CTkButton(
            self, text="[MIC]", width=42, height=42,
            font=(FONT_FAMILY, 18), fg_color="transparent",
            hover_color=C["bg_card"], corner_radius=2,
            command=self.on_voice
        )
        self.mic_btn.grid(row=1, column=1, padx=(2, 6), pady=10)

        # Text input
        self.entry = ctk.CTkTextbox(
            self, height=42, font=(FONT_FAMILY, 13),
            fg_color=C["bg_input"], text_color=C["text_primary"],
            corner_radius=2, border_width=1, border_color=C["border"],
            wrap="word"
        )
        self.entry.grid(row=1, column=2, padx=4, pady=10, sticky="ew")
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: None)

        # Mute button
        self.mute_btn = ctk.CTkButton(
            self, text="[SND_ON]", width=42, height=42,
            font=(FONT_FAMILY, 16), fg_color="transparent",
            hover_color=C["bg_card"], corner_radius=2,
            command=self._toggle_mute
        )
        self.mute_btn.grid(row=1, column=3, padx=4, pady=10)

        # Send button
        self.send_btn = ctk.CTkButton(
            self, text="EXEC //", width=90, height=42,
            font=(FONT_FAMILY, 12, "bold"),
            fg_color="transparent", hover_color=C["bg_card"],
            border_width=1, border_color=C["border"],
            text_color=C["text_primary"],
            corner_radius=2, command=self._send
        )
        self.send_btn.grid(row=1, column=4, padx=(4, 12), pady=10)


    def clear_attachments(self):
        for w in self.attach_frame.winfo_children():
            w.destroy()
            
    def render_attachments(self, docs):
        self.clear_attachments()
        if not docs:
            return
        
        lbl = ctk.CTkLabel(self.attach_frame, text="Attached:", font=(FONT_FAMILY, 10, "bold"), text_color=C["accent"])
        lbl.pack(side="left", pady=4, padx=(0, 6))
        
        for doc in docs:
            pill = ctk.CTkFrame(self.attach_frame, fg_color=C["bg_card"], corner_radius=10, height=20)
            pill.pack(side="left", padx=2, pady=4)
            ctk.CTkLabel(pill, text="[DOC] " + doc["name"], font=(FONT_FAMILY, 10), text_color=C["text_primary"]).pack(padx=8, pady=2)

    def _on_enter(self, event):
        if not event.state & 1:  # No shift key
            self._send()
            return "break"

    def _send(self):
        if self.send_btn.cget("text") == "STOP //":
            if getattr(self, "on_stop", None):
                self.on_stop()
            return

        text = self.entry.get("1.0", "end").strip()
        if text:
            self.entry.delete("1.0", "end")
            self.on_send(text)

    def _toggle_mute(self):
        self._muted = not self._muted
        self.mute_btn.configure(text="[SND_OFF]" if self._muted else "🔊")
        self.on_mute_toggle()

    def set_voice_active(self, active: bool):
        self._voice_active = active
        color = C["error"] if active else C["bg_card"]
        self.mic_btn.configure(fg_color=color)

    def set_sending(self, sending: bool):
        if sending:
            self.send_btn.configure(text="STOP //", fg_color=C["error"], hover_color="#800000")
        else:
            self.send_btn.configure(text="EXEC //", fg_color="transparent", hover_color=C["bg_card"])

    def get_text(self) -> str:
        return self.entry.get("1.0", "end").strip()

    def set_text(self, text: str):
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", text)


# ── Main Application Window ───────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, current_params, on_save, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Operational Parameters")
        self.geometry("380x400")
        self.resizable(False, False)
        self.configure(fg_color=C["bg_deep"])
        self.transient(master)
        self.grab_set()

        self._on_save = on_save
        self._params = current_params.copy()
        
        lbl = ctk.CTkLabel(self, text=":: SYSTEM PARAMETERS ::", font=(FONT_FAMILY, 14, "bold"), text_color=C["accent_glow"])
        lbl.pack(pady=(16, 8))

        self.sliders = {}
        
        self._add_slider("Temperature", "temperature", 0.0, 2.0, self._params.get("temperature", 0.7))
        self._add_slider("Top P", "top_p", 0.0, 1.0, self._params.get("top_p", 0.9))
        self._add_slider("Max Tokens", "num_predict", 128, 4096, self._params.get("num_predict", 1024), is_int=True)
        self._add_slider("Repeat Penalty", "repeat_penalty", 0.5, 2.5, self._params.get("repeat_penalty", 1.1))

        btn = ctk.CTkButton(self, text="Save Settings", fg_color=C["accent"], hover_color=C["accent_dim"], 
                            command=self._save_and_close)
        btn.pack(pady=20)

    def _add_slider(self, label, key, min_val, max_val, default, is_int=False):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=24, pady=8)
        
        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=label, font=(FONT_FAMILY, 11, "bold"), text_color=C["text_primary"]).pack(side="left")
        
        val_lbl = ctk.CTkLabel(hdr, text=str(default), font=(FONT_FAMILY, 11), text_color=C["text_dim"])
        val_lbl.pack(side="right")
        
        def _on_change(val, k=key, vlbl=val_lbl, integer=is_int):
            final_val = int(val) if integer else round(val, 2)
            vlbl.configure(text=str(final_val))
            self._params[k] = final_val

        sl = ctk.CTkSlider(frame, from_=min_val, to=max_val, number_of_steps=100 if not is_int else int(max_val-min_val), 
                           command=_on_change, button_color=C["accent"], progress_color=C["accent_dim"])
        sl.set(default)
        sl.pack(fill="x", pady=(4, 0))

    def _save_and_close(self):
        self._on_save(self._params)
        self.destroy()

class AmethystApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Amethyst - Local AI Assistant")
        self.geometry("1200x780")
        self.minsize(900, 600)
        self.configure(fg_color=C["bg_deep"])

        # ── Core engines ──────────────────────────────────────────────────
        self._async   = AsyncBridge()
        self._memory  = MemoryManager()           # persistent memory
        self._engine  = AmethystEngine()
        self._engine.apply_memory(self._memory)   # inject memory → system prompt
        self._voice   = VoiceManager()
        self._ide     = IDEBridge(on_code_captured=self._on_ide_code)

        # ── Tier 3 Power Engines ─────────────────────────────────────────
        from rag_engine import RAGEngine
        from system_monitor import SystemMonitor
        from vision_engine import VisionEngine
        
        try:
            from search_engine import WebSearchEngine
            self._search = WebSearchEngine()
        except ImportError:
            self._search = None

        self._rag      = RAGEngine()
        self._vision   = VisionEngine()
        self._sysmon   = SystemMonitor(
            interval=30.0,
            on_alert=lambda msg: self.after(0, lambda: self._on_system_alert(msg))
        )
        self._sysmon.start()
        
        from code_executor import CodeExecutor
        self._executor = CodeExecutor()

        # Session state
        self._stored_sessions: list[StoredSession] = []
        self._active_stored: Optional[StoredSession] = None
        self._sessions: list[ChatSession] = []
        self._active_session: Optional[ChatSession] = None
        self._streaming   = False
        self._stream_bubble: Optional[StreamingBubble] = None
        self._cancel_generation = False
        
        # Hardware Starvation Barriers: num_thread limits CPU usage so OS doesn't freeze
        self._op_params = {
            "temperature": 0.7, 
            "top_p": 0.9, 
            "num_predict": 1024, 
            "repeat_penalty": 1.1,
            "num_thread": 2  # Restrict to 2 cores maximum
        }

        # ── Build UI ──────────────────────────────────────────────────────
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._sidebar = Sidebar(
            self,
            on_new_chat=self._new_session,
            on_select_session=self._load_session,
            on_clear_all=self._clear_all_sessions,
            on_resume_session=self._resume_session,
            on_delete_session=self._delete_session,   # NEW
        )
        self._sidebar.grid(row=0, column=0, sticky="ns")

        main = ctk.CTkFrame(self, fg_color=C["bg_deep"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self._build_topbar(main)

        self._chat_scroll = ctk.CTkScrollableFrame(
            main, fg_color=C["bg_deep"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent_dim"]
        )
        self._chat_scroll.grid(row=1, column=0, sticky="nsew")
        self._chat_scroll.grid_columnconfigure(0, weight=1)
        self._chat_row = 0

        self._input_bar = InputBar(
            main,
            on_send=self._send_message,
            on_voice=self._start_voice_input,
            on_mute_toggle=self._toggle_mute,
            on_attach=self._attach_document,
        )
        self._input_bar.on_stop = lambda: setattr(self, "_cancel_generation", True)
        self._input_bar.grid(row=2, column=0, sticky="ew")

        self._status_var = tk.StringVar(value="[SYS.INIT] System nominal. Ready.")
        ctk.CTkLabel(main, textvariable=self._status_var,
                     font=(FONT_FAMILY, 10), text_color=C["text_dim"],
                     anchor="w").grid(row=3, column=0, sticky="ew", padx=14, pady=2)

        # ── Start background systems ───────────────────────────────────────
        self._load_persisted_sessions()
        self._new_session()
        self._async.submit(self._startup_checks())
        self._ide.start()
        self._sysmon.start()

    def _build_topbar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=C["bg_panel"], corner_radius=0,
                            height=52)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        self._session_title_var = tk.StringVar(value="New Chat")
        ctk.CTkLabel(bar, textvariable=self._session_title_var,
                     font=(FONT_FAMILY, 15, "bold"),
                     text_color=C["text_primary"]).grid(
            row=0, column=0, padx=16, pady=8, sticky="w")

        self._model_badge = ctk.CTkLabel(bar, text="",
                                          font=(FONT_FAMILY, 11),
                                          text_color=C["text_dim"],
                                          fg_color=C["bg_card"],
                                          corner_radius=6)
        self._model_badge.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkButton(bar, text="[WIPE]", font=(FONT_FAMILY, 11),
                      fg_color="transparent", hover_color=C["bg_hover"],
                      text_color=C["text_muted"], width=70, height=30,
                      command=self._clear_current_chat).grid(
            row=0, column=2, padx=4)

        ctk.CTkButton(bar, text="[IDE]", font=(FONT_FAMILY, 11),
                      fg_color=C["bg_card"], hover_color=C["bg_hover"],
                      text_color=C["text_muted"], width=70, height=30,
                      command=self._show_ide_info).grid(
            row=0, column=3, padx=(0, 8))

        ctk.CTkButton(bar, text="[CFG]", font=(FONT_FAMILY, 14),
                      fg_color="transparent", hover_color=C["bg_hover"],
                      text_color=C["text_muted"], width=30, height=30,
                      command=self._show_settings).grid(
            row=0, column=4, padx=(0, 4))

        ctk.CTkButton(bar, text="[VIS]", font=(FONT_FAMILY, 14),
                      fg_color="transparent", hover_color=C["bg_hover"],
                      text_color=C["text_muted"], width=30, height=30,
                      command=self._analyze_screen).grid(
            row=0, column=5, padx=(0, 4))

        ctk.CTkButton(bar, text="[SYS]", font=(FONT_FAMILY, 14),
                      fg_color="transparent", hover_color=C["bg_hover"],
                      text_color=C["text_muted"], width=30, height=30,
                      command=self._show_system_info).grid(
            row=0, column=6, padx=(0, 4))
            
        # Emergency Kill Switch
        ctk.CTkButton(bar, text="[KILL]", font=(FONT_FAMILY, 12, "bold"),
                      fg_color="#3A0A0A", hover_color=C["error"],
                      text_color="#FF4444", width=50, height=30,
                      command=self._emergency_kill).grid(
            row=0, column=7, padx=(0, 12))

    def _emergency_kill(self):
        """Instantly terminate the application without saving state."""
        import os
        log.critical("EMERGENCY KILL SWITCH ACTIVATED. Terminating immediately.")
        os._exit(1)



    # ── Session Management ─────────────────────────────────────────────────
    def _show_settings(self):
        def _on_save(params):
            self._op_params = params
            log.info(f"Updated parameters: {params}")
        SettingsDialog(self, self._op_params, _on_save)

    def _on_system_alert(self, alert_msg: str):
        """Called by SystemMonitor when a critical threshold is hit."""
        self._set_status(f"⚠️ SYSTEM: {alert_msg}")
        # Also speak the alert if voice is on
        if not self._voice.is_muted:
            self._async.submit(self._voice.speak(f"Warning: {alert_msg}"))

    def _show_system_info(self):
        """Show system stats as a chat message."""
        snapshot = self._sysmon.get_snapshot()
        if snapshot:
            info = f"**System Status:**\n```\n{snapshot.as_context_string()}\n```"
            self._add_bubble("assistant", info, "system-monitor")
        else:
            self._add_bubble("assistant", "⚠️ System monitor unavailable. Install psutil: `pip install psutil`", "")

    def _analyze_screen(self):
        """Capture screenshot and send to vision model for analysis."""
        if self._streaming:
            return
        self._set_status("[SYS.VIS] Capturing optic feed...")
        self._streaming = True
        self._input_bar.set_sending(True)

        streaming_bubble = self._add_streaming_bubble("analyzing screenshot...")

        async def _do_vision():
            # Detect vision model if not yet done
            if not self._vision.has_vision:
                models = self._engine.available_models
                await self._vision.detect_vision_model(models)

            if not self._vision.has_vision:
                self.after(0, lambda: streaming_bubble.append(
                    "⚠️ No vision model available. Pull one with: `ollama pull llava`"
                ))
            else:
                self.after(0, lambda: self._set_status(f"[SYS.VIS] Processing via {self._vision.model_name}..."))

                def on_token(t):
                    self.after(0, lambda tok=t: streaming_bubble.append(tok))

                await self._vision.analyze_screenshot(
                    user_prompt="Describe what you see on this screen. Identify any errors, important content, or notable UI elements.",
                    on_token=on_token
                )

            full_text = streaming_bubble.finalize()

            def _finish():
                streaming_bubble.destroy()
                self._add_bubble("assistant", full_text, self._vision.model_name or "vision")
                self._streaming = False
                self._stream_bubble = None
                self._input_bar.set_sending(False)
                self._set_status("[SYS.VIS] Optic analysis complete.")

            self.after(0, _finish)

        self._async.submit(_do_vision())

    def _load_persisted_sessions(self):
        """Load all past sessions from disk and populate the sidebar."""
        self._sidebar.clear_sessions()
        self._stored_sessions = self._memory.load_all_sessions()
        for idx, s in enumerate(self._stored_sessions):
            self._sidebar.add_session_button(s, idx)
        # Show memory panel
        facts = self._memory.profile_summary_lines()
        if facts:
            self._sidebar.show_memory_panel(facts)
        # Auto-select the most recent resumable session
        for s in self._stored_sessions:
            if s.is_resumable:
                log.info(f"Found resumable session: '{s.title}'")
                break

    def _new_session(self):
        import uuid
        # Create in-memory ChatSession for UI
        session = ChatSession()
        self._sessions.append(session)
        self._active_session = session

        # Create persistent StoredSession
        stored = StoredSession(
            id=str(uuid.uuid4()),
            title="New Chat",
            created=__import__("time").time(),
            updated=__import__("time").time(),
        )
        self._stored_sessions.append(stored)
        self._active_stored = stored

        self._engine.clear_history()
        self._engine._refresh_system_prompt()  # reload memory into new session
        self._clear_chat_panel()
        self._session_title_var.set("New Chat")
        self._sidebar.add_session_button(stored, len(self._stored_sessions) - 1)
        self._show_welcome()

    def _load_session(self, idx: int):
        # Save interruption state of outgoing session
        if self._active_stored:
            if self._streaming and self._stream_bubble:
                # Currently generating — save draft
                draft = self._stream_bubble._full if self._stream_bubble else ""
                last_user = next(
                    (m.content for m in reversed(self._active_stored.messages)
                     if m.role == "user"), ""
                )
                self._memory.mark_interrupted(self._active_stored, last_user, draft)
            elif self._active_stored.message_count >= 4:
                self._async.submit(
                    self._memory.process_session_memory(
                        self._active_stored,
                        on_done=lambda s: self.after(0, self._on_summary_done, s)
                    )
                )

        # Load selected stored session
        if idx < len(self._stored_sessions):
            stored = self._stored_sessions[idx]
            self._active_stored = stored
            self._active_session = self._stored_to_chat(stored)
        elif idx < len(self._sessions):
            self._active_session = self._sessions[idx]
            self._active_stored  = None
        else:
            return

        self._engine.clear_history()
        self._engine._refresh_system_prompt()
        self._clear_chat_panel()
        title = self._active_stored.title if self._active_stored else "Chat"
        self._session_title_var.set(title)
        for role, text, model_label in self._active_session.messages:
            self._add_bubble(role, text, model_label, save=False)

    def _resume_session(self, idx: int):
        """
        Resume an interrupted session:
        1. Load all previous messages (render them)
        2. Show the pending prompt as a user bubble
        3. Re-fire the AI response automatically
        4. If there was a partial draft, show it as context
        """
        if idx >= len(self._stored_sessions):
            return
        stored = self._stored_sessions[idx]
        if not stored.is_resumable:
            # Nothing to resume — just load normally
            self._load_session(idx)
            return

        # Load session into UI
        self._active_stored  = stored
        self._active_session = self._stored_to_chat(stored)
        self._engine.clear_history()
        self._engine._refresh_system_prompt()
        self._clear_chat_panel()
        self._session_title_var.set(stored.title)

        # Render all confirmed messages EXCEPT the dangling user prompt
        # (we'll re-add it fresh so the AI responds)
        messages_to_show = stored.messages
        if messages_to_show and messages_to_show[-1].role == "user":
            messages_to_show = messages_to_show[:-1]  # strip pending user msg

        for m in messages_to_show:
            self._add_bubble(m.role, m.content, m.model, save=False)

        # If there was a partial draft, show it as a grayed-out "incomplete" note
        if stored.draft_response:
            draft_note = (
                f"[Partial response before interruption]\n\n"
                f"{stored.draft_response}\n\n"
                f"_(Resuming — regenerating full response...)_"
            )
            self._add_bubble("assistant", draft_note, "[draft]", save=False)

        self._set_status(f"Resuming: '{stored.title}'...")

        # Clear interrupted state before re-firing
        self._memory.mark_resumed(stored)

        # Re-send the pending prompt → triggers full AI response
        pending = stored.pending_prompt
        self.after(300, lambda: self._send_message(pending))

    def _stored_to_chat(self, stored: StoredSession) -> ChatSession:
        """Convert a StoredSession to a ChatSession for UI rendering."""
        cs = ChatSession(title=stored.title)
        for m in stored.messages:
            cs.add(m.role, m.content, m.model)
        return cs

    def _on_summary_done(self, summary: str):
        """Called after background summarization finishes."""
        log.info("Session summarized in background.")
        # Refresh memory panel
        facts = self._memory.profile_summary_lines()
        self._sidebar.show_memory_panel(facts)

    def _clear_all_sessions(self):
        self._memory.clear_all_memory()
        self._stored_sessions.clear()
        self._sessions.clear()
        self._sidebar.clear_sessions()
        self._engine.clear_history()
        self._new_session()
        
    def _delete_session(self, idx: int):
        if idx >= len(self._stored_sessions):
            return
        
        session_to_delete = self._stored_sessions[idx]
        self._memory.delete_session(session_to_delete.id)
        
        # If the deleted session was the currently active one, start a new chat
        if self._active_stored and self._active_stored.id == session_to_delete.id:
            self._new_session()
            
        # Reload sidebar
        self._load_persisted_sessions()


    def _clear_current_chat(self):
        if self._active_session:
            self._active_session.messages.clear()
        if self._active_stored:
            self._active_stored.messages.clear()
            self._memory.save_session(self._active_stored)
        self._engine.clear_history()
        self._clear_chat_panel()
        self._show_welcome()

    def _clear_chat_panel(self):
        for widget in self._chat_scroll.winfo_children():
            widget.destroy()
        self._chat_row = 0

    # ── Chat Rendering ─────────────────────────────────────────────────────
    def _show_welcome(self):
        welcome = ctk.CTkFrame(self._chat_scroll,
                                fg_color=C["bg_card"], corner_radius=16)
        welcome.grid(row=self._chat_row, column=0,
                     padx=60, pady=60, sticky="ew")
        welcome.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(welcome, text=":: AMETHYST_OS ::",
                     font=(FONT_FAMILY, 28, "bold"),
                     text_color=C["accent_glow"]).grid(pady=(24, 4))
        ctk.CTkLabel(welcome, text="Your local dual-model AI assistant",
                     font=(FONT_FAMILY, 14),
                     text_color=C["text_muted"]).grid(pady=(0, 8))

        hints = [
            ("[X] CODE_EXEC", "Ask me to write, fix, or explain code"),
            ("[~] NLP_CHAT", "Summarise, answer, or brainstorm"),
            ("[MIC] AUDIO_IN", "Press the mic button and speak"),
            ("[IDE] SYS_BRIDGE", "Press Ctrl+Shift+A in your editor"),
            ("[DB] VECTOR_STORE", "Attach PDFs/docs — I'll learn from them"),
            ("[VIS] OPTIC_SENSOR", "Press 📸 in the toolbar to analyse your screen"),
            ("[SYS] DIAGNOSTICS", "Press 💻 in the toolbar for live system info"),
        ]
        for title, desc in hints:
            row = ctk.CTkFrame(welcome, fg_color=C["bg_panel"], corner_radius=10)
            row.grid(padx=24, pady=4, sticky="ew")
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=title, font=(FONT_FAMILY, 12, "bold"),
                         text_color=C["accent_glow"], width=130).grid(
                row=0, column=0, padx=12, pady=10, sticky="w")
            ctk.CTkLabel(row, text=desc, font=(FONT_FAMILY, 11),
                         text_color=C["text_muted"]).grid(
                row=0, column=1, padx=8, pady=10, sticky="w")

        ctk.CTkFrame(welcome, height=20, fg_color="transparent").grid()
        self._chat_row += 1

    def _add_bubble(self, role: str, text: str, model_label: str = "",
                    save: bool = True):
        bubble = MessageBubble(
            self._chat_scroll, role=role, text=text, model_label=model_label
        )
        bubble.grid(row=self._chat_row, column=0, sticky="ew",
                    padx=8, pady=2)
        self._chat_row += 1
        self._scroll_bottom()

        if save and self._active_session:
            self._active_session.add(role, text, model_label)
            # Update session title from first user message
            if not self._active_session.title or self._active_session.title == "New Chat":
                if role == "user":
                    self._active_session.title = text[:30]
                    self._session_title_var.set(self._active_session.title)

            # Persist to disk
            if self._active_stored:
                if self._active_stored.title == "New Chat" and role == "user":
                    self._active_stored.title = text[:30]
                    self._session_title_var.set(self._active_stored.title)
                self._active_stored.messages.append(
                    StoredMessage(role=role, content=text, model=model_label)
                )
                self._memory.save_session(self._active_stored)

    def _add_streaming_bubble(self, model_label: str) -> StreamingBubble:
        bubble = StreamingBubble(self._chat_scroll, model_label=model_label)
        bubble.grid(row=self._chat_row, column=0, sticky="ew",
                    padx=8, pady=2)
        self._chat_row += 1
        self._stream_bubble = bubble
        return bubble

    def _scroll_bottom(self):
        """Flush pending layout changes then scroll to the very bottom."""
        try:
            canvas = self._chat_scroll._parent_canvas
            canvas.update_idletasks()
            canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Send / Stream ──────────────────────────────────────────────────────
    def _attach_document(self):
        from tkinter import filedialog
        
        paths = filedialog.askopenfilenames(
            title="Select Documents for Vector Database",
            filetypes=[("All Supported", "*.pdf *.txt *.md *.py *.csv *.html *.js"),
                       ("PDF files", "*.pdf"),
                       ("Text files", "*.txt *.md *.py *.csv *.html *.js")]
        )
        if not paths:
            return
            
        self._set_status("[SYS.DB] Ingesting documents into vector space...")
        self.update()
        
        async def _ingest_task():
            import asyncio
            loop = asyncio.get_event_loop()
            total = 0
            for p in paths:
                t = await loop.run_in_executor(None, self._rag.ingest_document, p)
                total += t
            self.after(0, lambda: self._set_status(f"[SYS.DB] Vectorized {len(paths)} docs ({total} chunks) into Knowledge Base"))
            self.after(0, lambda: self._input_bar.clear_attachments())
            
        self._async.submit(_ingest_task())

    def _send_message(self, text: str, force_model=None):
        if self._streaming:
            return
        if not text.strip():
            return

        self._add_bubble("user", text)
        self._start_streaming(text, force_model)

    def _start_streaming(self, prompt: str, force_model=None):
        self._streaming = True
        self._input_bar.set_sending(True)
        self._set_status("[SYS.CORE] Computing response...")

        # Placeholder streaming bubble (replaced on finish)
        streaming_bubble = self._add_streaming_bubble("loading...")

        async def _do_stream():
            model_label = "loading..."
            first_token = True

            # ── RAG: Search knowledge base for relevant context ──
            actual_prompt = prompt
            try:
                loop = asyncio.get_event_loop()
                rag_context = await loop.run_in_executor(None, self._rag.query, prompt)
                if rag_context:
                    actual_prompt = (
                        "The following documents from the user's knowledge base are relevant to this query.\n"
                        "Use them to inform your answer, but don't mention 'chunks' or 'vector database' — "
                        "just answer naturally as if you know this information.\n\n"
                        f"--- RETRIEVED KNOWLEDGE ---\n{rag_context}\n--- END KNOWLEDGE ---\n\n"
                        f"User Query: {prompt}"
                    )
                    self.after(0, lambda: self._set_status("[SYS.DB] Retrieving vector data..."))
                    log.info(f"RAG injected {len(rag_context)} chars of context into prompt.")
            except Exception as e:
                log.error(f"RAG query failed (non-fatal): {e}")

            def on_model_selected(decision: RouterDecision):
                nonlocal model_label
                model_label = decision.model.value
                self.after(0, lambda: self._model_badge.configure(
                    text=f" {decision.model.value} | {decision.reason} ",
                    text_color=C["qwen_color"] if decision.model == ModelType.CODER
                    else C["gemma_color"]
                ))
                
            # ── Route manually first to check for search intent ──
            # (Only route if not forced)
            pre_routed = None
            if not force_model:
                pre_routed = self._engine.router.route(actual_prompt)
                
                # Check for autonomous web search
                if self._search and getattr(pre_routed, "requires_search", False):
                    if self._search.is_connected():
                        self.after(0, lambda: self._set_status("[SYS.NET] Querying external networks..."))
                        loop = asyncio.get_event_loop()
                        search_results = await loop.run_in_executor(None, self._search.search, prompt)
                        if search_results:
                            actual_prompt = (
                                f"--- LIVE WEB SEARCH RESULTS ---\n{search_results}\n--- END SEARCH ---\n\n{actual_prompt}"
                            )
                            log.info("Injected live web search results.")
                    else:
                        log.warning("Offline: skipped live web search.")

            self._cancel_generation = False
            async for token in self._engine.stream_response(
                actual_prompt,
                force_model=force_model,
                on_model_selected=on_model_selected,
                custom_options=self._op_params,
                pre_routed=pre_routed,
            ):
                if self._cancel_generation:
                    streaming_bubble.append(" [ABORTED]")
                    break
                    
                def _append_and_scroll(t=token):
                    streaming_bubble.append(t)
                    self._scroll_bottom()
                self.after(0, _append_and_scroll)

            full_text = streaming_bubble.finalize()

            # Check for Agentic Execution
            execute_match = re.search(r"\[EXECUTE:(.*?)\]\s*```[a-zA-Z]*\n(.*?)```", full_text, re.DOTALL)
            if execute_match:
                lang = execute_match.group(1).strip()
                code = execute_match.group(2).strip()
                self.after(0, lambda: self._set_status(f"[SYS.EXEC] Running {lang} code..."))
                try:
                    res = await self._executor.execute(code, language=lang, timeout=30)
                    out = (res.get('stdout', '') + '\n' + res.get('stderr', '')).strip()
                    if not out: out = "Success (No output)"
                    full_text += f"\n\n```text\n--- SYSTEM RESPONSE ---\n{out}\n```"
                except Exception as e:
                    full_text += f"\n\n```text\n--- SYSTEM ERROR ---\n{e}\n```"
            def _finish():
                streaming_bubble.destroy()
                
                # Check for Self-Upgrade syntax
                try:
                    from self_modifier import SelfModifier
                    upgrade_status = SelfModifier.scan_and_apply(full_text)
                    final_text = full_text + upgrade_status
                except Exception as e:
                    log.error(f"SelfModifier error: {e}")
                    final_text = full_text
                    
                self._add_bubble("assistant", final_text, model_label)
                self._streaming = False
                self._stream_bubble = None
                self._input_bar.set_sending(False)
                self._set_status(f"[SYS.CORE] Output via {model_label}")

                # TTS
                if not self._voice.is_muted:
                    self._async.submit(self._voice.speak(final_text))

            self.after(0, _finish)

        self._async.submit(_do_stream())

    # ── Voice ──────────────────────────────────────────────────────────────
    def _start_voice_input(self):
        if self._streaming:
            return
        self._input_bar.set_voice_active(True)
        self._set_status("[SYS.MIC] Awaiting audio input...")

        async def _listen():
            def on_state(state):
                labels = {
                    VoiceState.LISTENING:  "[SYS.MIC] Awaiting audio input...",
                    VoiceState.PROCESSING: "[SYS.MIC] Decoding waveform...",
                    VoiceState.ERROR:      "[SYS.ERR] Audio failure",
                    VoiceState.IDLE:       "[SYS.IDLE] Awaiting input.",
                }
                self.after(0, lambda: self._set_status(labels.get(state, "")))

            text = await self._voice.listen(on_state=on_state)

            def _done():
                self._input_bar.set_voice_active(False)
                if text:
                    self._send_message(text)
                else:
                    self._set_status("[SYS.MIC] Zero amplitude detected.")

            self.after(0, _done)

        self._async.submit(_listen())

    def _toggle_mute(self):
        muted = self._voice.toggle_mute()
        self._set_status("[SYS.SND] Output suppressed." if muted else "[SYS.SND] Output active.")

    # ── IDE Bridge ─────────────────────────────────────────────────────────
    def _on_ide_code(self, code: str):
        """Called when Ctrl+Shift+A captures code from editor."""
        self.after(0, self._handle_ide_code, code)

    def _handle_ide_code(self, code: str):
        self.lift()
        self.focus_force()
        prompt = f"Please analyze and explain this code:\n\n```\n{code}\n```"
        self._input_bar.set_text(prompt)
        self._send_message(prompt, force_model=ModelType.CODER)

    def _show_ide_info(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("IDE Bridge")
        dialog.geometry("420x220")
        dialog.configure(fg_color=C["bg_card"])
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="[SYS.IDE] Bridge Established",
                     font=(FONT_FAMILY, 16, "bold"),
                     text_color=C["accent_glow"]).pack(pady=(20, 8))
        ctk.CTkLabel(dialog,
                     text="Select code in any editor, then press:\n\n"
                          "Ctrl + Shift + A\n\n"
                          "Amethyst will analyze it automatically.",
                     font=(FONT_FAMILY, 13),
                     text_color=C["text_muted"],
                     justify="center").pack(pady=8)
        ctk.CTkButton(dialog, text="Got it!", fg_color=C["accent"],
                      command=dialog.destroy).pack(pady=12)

    # ── Startup ────────────────────────────────────────────────────────────
    async def _startup_checks(self):
        ram_gb = getattr(self._sysmon, "ram_total_gb", 8.0)
        
        # Wait up to 5 seconds for Ollama to boot up
        for _ in range(10):
            await asyncio.sleep(0.5)
            status = await self._engine.check_models(system_ram_gb=ram_gb)
            if self._engine.available_models:
                break
        
        # Populate dropdowns
        models = sorted(list(self._engine.available_models))
        if not models: models = ["none"]
        
        def _update_ui():
            if "coder" in self._sidebar._model_dropdowns:
                self._sidebar._model_dropdowns["coder"].configure(values=models)
                self._sidebar._model_dropdowns["coder"].set(self._engine.resolved_coder or "missing")
            if "chat" in self._sidebar._model_dropdowns:
                self._sidebar._model_dropdowns["chat"].configure(values=models)
                self._sidebar._model_dropdowns["chat"].set(self._engine.resolved_chat or "missing")
                
            coder_ok = bool(self._engine.resolved_coder)
            chat_ok = bool(self._engine.resolved_chat)
            # self._sidebar.update_model_status(coder_ok, chat_ok) # Removed static dots

        self.after(0, _update_ui)

        # Detect vision model from available models
        vision_model = await self._vision.detect_vision_model(self._engine.available_models)

        # Build status message
        if not self._engine.resolved_coder and not self._engine.resolved_chat:
            self.after(0, lambda: self._set_status(
                "[SYS.ERR] No models found! Please run `ollama run qwen2.5-coder:7b`"))
        else:
            vision_str = f" | 👁 Vision: {vision_model}" if vision_model else " | 👁 Vision: none"
            self.after(0, lambda: self._set_status(f"✅ Models online (RAM: {ram_gb:.1f}GB){vision_str}"))

        # Initialize RAG engine in background (lazy but early)
        await asyncio.get_event_loop().run_in_executor(None, self._rag.initialize)
        rag_count = self._rag.chunk_count
        if rag_count > 0:
            self.after(0, lambda: self._set_status(
                f"[SYS.DB] Vector store online ({rag_count} objects)"))

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def on_closing(self):
        """Save state before exit so sessions can be resumed."""
        if self._active_stored:
            if self._streaming and self._stream_bubble:
                # Mid-generation crash/close — save the draft
                draft = getattr(self._stream_bubble, "_full", "")
                last_user = next(
                    (m.content for m in reversed(self._active_stored.messages)
                     if m.role == "user"), ""
                )
                self._memory.mark_interrupted(self._active_stored, last_user, draft)
                log.info("Closed mid-stream — draft saved.")
            elif self._active_stored.message_count >= 4:
                # Background summarize on clean exit
                try:
                    import asyncio as _aio
                    loop = _aio.new_event_loop()
                    loop.run_until_complete(
                        self._memory.process_session_memory(self._active_stored)
                    )
                    loop.close()
                except Exception:
                    pass
        self._ide.stop()
        self._async.stop()
        self.destroy()


# ── Entrypoint ────────────────────────────────────────────────────────────────
def main():
    app = AmethystApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
