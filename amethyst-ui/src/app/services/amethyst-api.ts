import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export const API_BASE = 'http://localhost:8000/api';

export interface ChatRequest {
  message: string;
  session_id?: string;
  force_model?: 'coder' | 'chat';
  options?: Record<string, number>;
}

export interface Session {
  id: string;
  title: string;
  created: number;
  updated: number;
  message_count: number;
  summarized: boolean;
  is_resumable: boolean;
}

export interface SessionDetail {
  id: string;
  title: string;
  messages: { role: string; content: string; model: string; timestamp: number }[];
  summary: string;
}

export interface SystemSnapshot {
  available: boolean;
  cpu_percent: number;
  ram_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  disk_percent: number;
  disk_free_gb: number;
  battery_percent: number | null;
  battery_plugged: boolean | null;
  os_name: string;
  hostname: string;
}

export interface ModelStatus {
  online: boolean;
  coder_model: string;
  chat_model: string;
  vision_model: string | null;
  models: Record<string, boolean>;
}

@Injectable({ providedIn: 'root' })
export class AmethystApiService {
  constructor(private http: HttpClient) {}

  getStatus(): Observable<ModelStatus> {
    return this.http.get<ModelStatus>(`${API_BASE}/status`);
  }

  getSessions(): Observable<{ sessions: Session[] }> {
    return this.http.get<{ sessions: Session[] }>(`${API_BASE}/sessions`);
  }

  getSession(id: string): Observable<SessionDetail> {
    return this.http.get<SessionDetail>(`${API_BASE}/sessions/${id}`);
  }

  deleteSession(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE}/sessions/${id}`);
  }

  clearSessions(): Observable<void> {
    return this.http.post<void>(`${API_BASE}/sessions/clear`, {});
  }

  getProfile(): Observable<any> {
    return this.http.get(`${API_BASE}/memory/profile`);
  }

  getSystem(): Observable<SystemSnapshot> {
    return this.http.get<SystemSnapshot>(`${API_BASE}/system`);
  }

  getRagStats(): Observable<any> {
    return this.http.get(`${API_BASE}/rag/stats`);
  }

  clearRag(): Observable<void> {
    return this.http.post<void>(`${API_BASE}/rag/clear`, {});
  }

  uploadDocument(file: File, sessionId?: string): Observable<any> {
    const form = new FormData();
    form.append('file', file);
    if (sessionId) {
      form.append('session_id', sessionId);
    }
    return this.http.post(`${API_BASE}/rag/ingest/upload`, form);
  }

  saveScript(code: string, language: string, filename?: string): Observable<any> {
    return this.http.post(`${API_BASE}/code/save`, { code, language, filename });
  }

  executeScript(code: string, language: string, timeout = 30): Observable<any> {
    return this.http.post(`${API_BASE}/code/execute`, { code, language, timeout });
  }

  analyzeVision(prompt = '', imageB64?: string): Observable<any> {
    return this.http.post(`${API_BASE}/vision/analyze`, { prompt, image_b64: imageB64 });
  }
}
