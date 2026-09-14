import { Injectable, signal, computed } from '@angular/core';
import { API_BASE } from './amethyst-api';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  timestamp: number;
  streaming?: boolean;
  image_b64?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  // ── Signals ────────────────────────────────────────────────────────────
  readonly sessions   = signal<ChatSession[]>([]);
  readonly activeId   = signal<string | null>(null);
  readonly streaming  = signal(false);
  readonly coderModel = signal('');
  readonly chatModel  = signal('');

  readonly activeSession = computed(() =>
    this.sessions().find(s => s.id === this.activeId()) ?? null
  );

  private _es: EventSource | null = null;
  private _abortCtrl: AbortController | null = null;

  // ── Session Management ─────────────────────────────────────────────────
  newSession(): string {
    const id = crypto.randomUUID();
    const session: ChatSession = { id, title: 'New Chat', messages: [] };
    this.sessions.update(s => [session, ...s]);
    this.activeId.set(id);
    return id;
  }

  loadSession(session: ChatSession) {
    const exists = this.sessions().some(s => s.id === session.id);
    if (!exists) {
      this.sessions.update(s => [session, ...s]);
    }
    this.activeId.set(session.id);
  }

  deleteSession(id: string) {
    this.sessions.update(s => s.filter(x => x.id !== id));
    if (this.activeId() === id) {
      const remaining = this.sessions();
      this.activeId.set(remaining.length > 0 ? remaining[0].id : null);
    }
  }

  clearAll() {
    this.sessions.set([]);
    this.activeId.set(null);
  }

  renameSession(id: string, title: string) {
    this.sessions.update(sessions =>
      sessions.map(s => s.id === id ? { ...s, title } : s)
    );
  }

  // ── Messaging ──────────────────────────────────────────────────────────
  sendMessage(
    text: string,
    forceModel?: 'coder' | 'chat',
    options?: Record<string, number>,
    imageB64?: string
  ): void {
    const sessionId = this.activeId();
    if (!sessionId || this.streaming()) return;

    // Add user message immediately
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
      image_b64: imageB64,
    };
    this._addMessage(sessionId, userMsg);

    // Rename session from first message
    const session = this.sessions().find(s => s.id === sessionId);
    if (session && session.messages.filter(m => m.role === 'user').length === 1) {
      this.renameSession(sessionId, text.slice(0, 40));
    }

    // Placeholder assistant message for streaming
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      streaming: true,
    };
    this._addMessage(sessionId, assistantMsg);

    this.streaming.set(true);
    this._stream(text, sessionId, assistantMsg.id, forceModel, options, imageB64);
  }

  private _stream(
    text: string,
    sessionId: string,
    assistantMsgId: string,
    forceModel?: 'coder' | 'chat',
    options?: Record<string, number>,
    imageB64?: string
  ) {
    // Abort any in-flight stream
    if (this._abortCtrl) { this._abortCtrl.abort(); this._abortCtrl = null; }
    this._abortCtrl = new AbortController();

    const body = JSON.stringify({
      message: text,
      session_id: sessionId,
      force_model: forceModel ?? null,
      options: options ?? null,
      image_b64: imageB64 ?? null,
    });

    // Use fetch + ReadableStream for POST SSE (EventSource only supports GET)
    fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal: this._abortCtrl.signal,
    }).then(async res => {
      if (!res.body) throw new Error('No response body');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const evt = JSON.parse(raw);
            if (evt.type === 'meta') {
              this._updateMessage(sessionId, assistantMsgId, { model: evt.model });
            } else if (evt.type === 'token') {
              this._appendToken(sessionId, assistantMsgId, evt.text);
            } else if (evt.type === 'done') {
              this._updateMessage(sessionId, assistantMsgId, { streaming: false });
              this.streaming.set(false);
            } else if (evt.type === 'error') {
              this._updateMessage(sessionId, assistantMsgId, {
                content: `⚠️ ${evt.message}`,
                streaming: false,
              });
              this.streaming.set(false);
            }
          } catch { /* ignore parse errors */ }
        }
      }
      this.streaming.set(false);
      this._updateMessage(sessionId, assistantMsgId, { streaming: false });
    }).catch(err => {
      // Don't show error for user-initiated abort
      if (err.name === 'AbortError') {
        this._updateMessage(sessionId, assistantMsgId, { streaming: false });
        this.streaming.set(false);
        return;
      }
      this._updateMessage(sessionId, assistantMsgId, {
        content: `⚠️ Connection error: ${err.message}`,
        streaming: false,
      });
      this.streaming.set(false);
    });
  }

  stopGeneration() {
    if (this._abortCtrl) {
      this._abortCtrl.abort();
      this._abortCtrl = null;
    }
    this.streaming.set(false);
  }

  addAttachmentMessage(fileName: string) {
    const sessionId = this.activeId();
    if (!sessionId) return;
    
    const msg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: `📎 [Attached: ${fileName}]`,
      timestamp: Date.now(),
    };
    this._addMessage(sessionId, msg);
  }

  // ── Helpers ────────────────────────────────────────────────────────────
  private _addMessage(sessionId: string, msg: ChatMessage) {
    this.sessions.update(sessions =>
      sessions.map(s =>
        s.id === sessionId ? { ...s, messages: [...s.messages, msg] } : s
      )
    );
  }

  private _updateMessage(sessionId: string, msgId: string, patch: Partial<ChatMessage>) {
    this.sessions.update(sessions =>
      sessions.map(s => {
        if (s.id !== sessionId) return s;
        return {
          ...s,
          messages: s.messages.map(m =>
            m.id === msgId ? { ...m, ...patch } : m
          ),
        };
      })
    );
  }

  private _appendToken(sessionId: string, msgId: string, token: string) {
    this.sessions.update(sessions =>
      sessions.map(s => {
        if (s.id !== sessionId) return s;
        return {
          ...s,
          messages: s.messages.map(m =>
            m.id === msgId ? { ...m, content: m.content + token } : m
          ),
        };
      })
    );
  }
}
