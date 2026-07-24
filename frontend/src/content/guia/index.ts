import type { Chapter } from "./types";
import { chapter as ch1 } from "./ch1-que-es";

export const CHAPTERS: Chapter[] = [ch1];

export const CHAPTER_SLUGS: string[] = CHAPTERS.map((c) => c.slug);
