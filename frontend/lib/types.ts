export type Meeting = {
  id: string;
  title: string;
  platform: string;
  status: string;
  sentiment: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  join_url: string | null;
  organizer_email?: string | null;
  participants: string[];
  report_ready: boolean;
  report_stale: boolean;
  report_filename?: string | null;
  error_message?: string | null;
  duration_minutes?: number | null;
};

export type Segment = {
  id: string;
  speaker_name: string;
  timestamp_label: string;
  original_text: string;
  original_language: string;
  english_text: string;
  started_at: string;
  source: string;
};

export type ChatMessage = {
  id: string;
  sender_name: string;
  original_text: string;
  english_text: string;
  timestamp_label: string;
  sent_at: string;
};

export type ActionItem = {
  id: string;
  meeting_id: string;
  assignee_name: string;
  description: string;
  status: string;
  due_label: string | null;
  created_at: string;
};

export type MeetingDetail = {
  meeting: Meeting;
  participants: { id: string; name: string; email: string | null }[];
  segments: Segment[];
  chat: ChatMessage[];
  actions: ActionItem[];
  decisions: { id: string; text: string }[];
  risks: { id: string; text: string }[];
  summary: {
    executive_summary: string;
    detailed_summary: string;
    manager_summary: string;
    next_steps: string[];
    sentiment: string;
    model_name: string;
  } | null;
  email: {
    recipients: string[];
    status: string;
    error: string | null;
    sent_at: string | null;
  } | null;
};

export type Task = ActionItem & { meeting_title: string };

export type PublicBrand = {
  company_name: string;
  company_tagline: string;
  brand_color: string;
};
