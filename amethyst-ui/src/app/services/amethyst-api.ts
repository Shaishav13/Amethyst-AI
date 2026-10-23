import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export const API_BASE = 'http://localhost:8001/api';

export interface ChatRequest {
  message: string;
  session_id?: string;
  force_model?: 'coder' | 'chat' | 'image';
  image_engine?: 'flux' | 'sdxl';
  options?: Record<string, any>;
  image_b64?: string;
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
  comfy_online?: boolean;
}

export interface ComfyStatus {
  online: boolean;
  devices?: any[];
  checkpoints?: string[];
  default_checkpoint?: string;
  error?: string;
}


export interface OKFTopic {
  id: string;
  title: string;
  type: string;
  tags: string[];
  summary: string;
  related: string[];
  inline_links: string[];
  file_name: string;
  content_preview: string;
  updated: number;
}

export interface KnowledgeResponse {
  topics: OKFTopic[];
  count: number;
}

export interface ImageResult {
  success: boolean;
  prompt_id: string;
  filename: string;
  local_path: string;
  url: string;
  seed: number;
  checkpoint: string;
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

  // ── ComfyUI Image Generation & Editing ──────────────────────────────────

  getComfyStatus(): Observable<ComfyStatus> {
    return this.http.get<ComfyStatus>(`${API_BASE}/image/status`);
  }

  generateImage(prompt: string, negativePrompt?: string, checkpoint?: string): Observable<ImageResult> {
    return this.http.post<ImageResult>(`${API_BASE}/image/generate`, {
      prompt,
      negative_prompt: negativePrompt,
      checkpoint,
    });
  }

  editOutfit(file: File, prompt: string, negativePrompt?: string, checkpoint?: string): Observable<ImageResult> {
    const form = new FormData();
    form.append('file', file);
    form.append('prompt', prompt);
    if (negativePrompt) form.append('negative_prompt', negativePrompt);
    if (checkpoint) form.append('checkpoint', checkpoint);
    return this.http.post<ImageResult>(`${API_BASE}/image/edit/outfit`, form);
  }

  editScenario(file: File, prompt: string, negativePrompt?: string, checkpoint?: string): Observable<ImageResult> {
    const form = new FormData();
    form.append('file', file);
    form.append('prompt', prompt);
    if (negativePrompt) form.append('negative_prompt', negativePrompt);
    if (checkpoint) form.append('checkpoint', checkpoint);
    return this.http.post<ImageResult>(`${API_BASE}/image/edit/scenario`, form);
  }

  // ── Google Open Knowledge Format (OKF) ──────────────────────────────────

  getKnowledgeTopics(): Observable<KnowledgeResponse> {
    return this.http.get<KnowledgeResponse>(`${API_BASE}/knowledge/topics`);
  }

  getKnowledgeTopic(id: string): Observable<OKFTopic & { content: string; connected_nodes: OKFTopic[] }> {
    return this.http.get<OKFTopic & { content: string; connected_nodes: OKFTopic[] }>(`${API_BASE}/knowledge/topic/${id}`);
  }

  compileKnowledge(): Observable<{ success: boolean; compiled_count: number; total_nodes: number }> {
    return this.http.post<{ success: boolean; compiled_count: number; total_nodes: number }>(`${API_BASE}/knowledge/compile`, {});
  }

  uploadKnowledgeFile(file: File): Observable<any> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post(`${API_BASE}/knowledge/upload`, form);
  }

}
