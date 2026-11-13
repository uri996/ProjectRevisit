export interface Project {
  id: string;
  name: string;
  created_at: string;
  document_count: number;
  indexed_count: number;
}
export interface Document {
  id: string;
  project_id: string;
  name: string;
  status: string;
  error: string;
  chunk_count: number;
  index_config: string | null;
  created_at: string;
}
export interface Citation {
  source: string;
  heading: string;
  chunk_id: string;
  document_id: string;
  text: string;
  distance: number;
  cited: boolean;
}
export interface Message {
  id: string;
  role: string;
  content: string;
  created_at: string;
  status: string;
  citations: Citation[];
}
export interface Recommended {
  question: string;
  direction: string;
  reason: string;
}
export interface Recommendations {
  project_id: string;
  description: string;
  target_role: string;
  questions: Recommended[];
  updated_at: string;
}
export interface Settings {
  provider: string;
  base_url: string;
  llm_model: string;
  embedding_model: string;
  dimensions: number;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  history_messages: number;
  history_chars: number;
  max_distance: number;
}
export interface SettingsView {
  settings: Settings;
  key_status: string;
  warning?: string | null;
}
