export interface CoursewareItem {
  id: number;
  title: string;
  status: "uploaded" | "translating" | "translated" | "failed";
  last_error?: string;
  created_at: string;
  total_slides?: number;
  translated_slides?: number;
  rendered_slides?: number;
  translation_duration_seconds?: number | null;
}

export interface SlideItem {
  slide_no: number;
  title: string;
  source_image_url: string;
  processed_image_url: string;
  translation_done: boolean;
  preview_done: boolean;
  source_text: string;
  translated_text: string;
  notes: string;
  translated_notes: string;
  source_layout: SlideLayout;
  translated_layout: SlideLayout;
}

export interface SlideLayoutBlock {
  block_id: number;
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  is_title?: boolean;
  kind?: string;
}

export interface SlideLayout {
  page_width?: number;
  page_height?: number;
  blocks: SlideLayoutBlock[];
}
