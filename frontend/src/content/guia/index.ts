import type { Chapter } from "./types";
import { chapter as ch1 } from "./ch1-que-es";
import { chapter as ch2 } from "./ch2-primeros-pasos";
import { chapter as ch3 } from "./ch3-analizar-un-run";
import { chapter as ch4 } from "./ch4-el-acta-firmada";
import { chapter as ch5 } from "./ch5-la-memoria-de-qa";
import { chapter as ch6 } from "./ch6-familias-y-calibracion";
import { chapter as ch7 } from "./ch7-preguntas-frecuentes";

export const CHAPTERS: Chapter[] = [ch1, ch2, ch3, ch4, ch5, ch6, ch7];

export const CHAPTER_SLUGS: string[] = CHAPTERS.map((c) => c.slug);
