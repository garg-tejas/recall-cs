/**
 * TypeScript types matching backend Pydantic schemas.
 */

// Auth types
export interface SignupRequest {
  email: string
  username: string
  password: string
}

export interface LoginRequest {
  email_or_username: string
  password: string
}

export interface RefreshRequest {
  refresh_token: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserOut {
  id: number
  email: string
  username: string
  is_active: boolean
}

// Quiz types
export interface QuizCard {
  card_id: number
  canonical_card_id?: number | null
  is_variant?: boolean
  topic: string
  question: string
  difficulty?: string | null
  question_type?: string | null
}

export interface LearningPathNode {
  subject: string
  topic_key: string
  display_name: string
  mastery_score: number
  swot_bucket: string
  priority_score: number
  prerequisite_topic_keys: string[]
}

export interface SessionProgress {
  current_index: number
  total: number
  completed: boolean
}

export interface QuizSessionStartRequest {
  topics?: string[] | null
  subject?: string | null
  limit?: number
  path_topics_ordered?: string[] | null
}

export interface QuizSessionStartResponse {
  session_id: string
  current_card?: QuizCard | null
  progress: SessionProgress
  path: LearningPathNode[]
}

export interface QuizSessionAnswerRequest {
  card_id: number
  user_answer: string
  response_time_ms?: number | null
  action?: string | null
}

export interface QuizSessionAnswerResponse {
  answer: string
  explanation?: string | null
  source_chunk_id?: string | null
  show_source_context?: boolean
  model_score?: number | null
  verdict?: string | null
  should_remediate?: boolean
  concept_summary?: string | null
  where_you_missed?: string[]
  next_due_at?: string | null
  interval_days?: number | null
  next_card?: QuizCard | null
  progress: SessionProgress
}

export interface QuizSessionFinishResponse {
  status: string
  session_id: string
}

export interface QuizSessionSkipResponse {
  next_card?: QuizCard | null
  progress: SessionProgress
}

export interface TopicStats {
  topic: string
  total: number
  learned: number
  due_today: number
  overdue: number
}

export interface QuizStatsResponse {
  topics: TopicStats[]
}

// Tutor types
export interface CitationOut {
  index: number
  chunk_id: string
  snippet: string
}

export interface ChunkSummary {
  id: string
  header_path: string
  snippet: string
}

export interface TutorChatRequest {
  query: string
  conversation_id?: number | null
  subject?: string | null
}

export interface TutorChatResponse {
  answer: string
  citations: CitationOut[]
  chunks_used: ChunkSummary[]
  conversation_id: number
}

export interface ChatMessageOut {
  id: number
  role: string
  content: string
  citations: CitationOut[]
  chunks: ChunkSummary[]
  created_at: string
}

export interface ConversationOut {
  id: number
  title: string | null
  subject: string | null
  topic_key: string | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetailOut extends ConversationOut {
  messages: ChatMessageOut[]
}

export interface ConversationListResponse {
  conversations: ConversationOut[]
}

export interface CreateConversationRequest {
  title?: string | null
  subject?: string | null
  topic_key?: string | null
}
