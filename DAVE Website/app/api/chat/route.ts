import path from "path";
import fs from "fs/promises";
import { config } from "dotenv";
import { GoogleGenAI } from "@google/genai";
import { NextResponse } from "next/server";
import { SYSTEM_PROMPTS, type PromptKey, DEFAULT_PROMPT_KEY } from "./prompts";

for (const envPath of [
  path.resolve(process.cwd(), ".env"),
  path.resolve(process.cwd(), "..", ".env"),
]) {
  config({ path: envPath });
}

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const message = typeof body?.message === "string" ? body.message.trim() : "";

    // If no user message is provided, this is the initial request: send the
    // `volleyball_coach` system prompt along with the sample JSON from
    // CommonUtils/message (2).txt as the user content so Gemini's first reply
    // is generated from the prompt + file (no manual user input required).
    // Any subsequent request that contains a `message` will use the
    // `volleyball_help` system prompt.

    // Helper: try several likely locations for the sample file.
    async function readSampleFile(): Promise<string | null> {
      const candidates = [
        path.resolve(process.cwd(), "CommonUtils", "message (2).txt"),
        path.resolve(process.cwd(), "..", "CommonUtils", "message (2).txt"),
        path.resolve(process.cwd(), "..", "..", "CommonUtils", "message (2).txt"),
      ];
      for (const p of candidates) {
        try {
          const txt = await fs.readFile(p, "utf8");
          return txt;
        } catch (e) {
          // ignore and try next
        }
      }
      return null;
    }

    let systemInstruction: string;
    let contents: any[];

    if (!message) {
      // initial flow
      systemInstruction = SYSTEM_PROMPTS["volleyball_coach"] || SYSTEM_PROMPTS[DEFAULT_PROMPT_KEY];
      const sample = (await readSampleFile()) || "";
      contents = [
        { role: "user", parts: [{ text: sample }] },
      ];
    } else {
      // subsequent messages use the help persona
      systemInstruction = SYSTEM_PROMPTS["volleyball_help"] || SYSTEM_PROMPTS[DEFAULT_PROMPT_KEY];
      contents = [
        { role: "user", parts: [{ text: message }] },
      ];
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        { error: "GEMINI_API_KEY is not set. Add it to your environment before using Gemini." },
        { status: 500 }
      );
    }

    const ai = new GoogleGenAI({ apiKey });
    const modelsToTry = ["gemini-3.5-flash"];

    let reply = "I’m having trouble reaching Gemini right now. Please try again in a moment.";

    for (const model of modelsToTry) {
      try {
        const response = await ai.models.generateContent({
          model,
          config: {
            systemInstruction: systemInstruction,
          },
          contents,
        });

        reply = response.text || reply;
        break;
      } catch (modelError) {
        console.warn(`Gemini model ${model} failed`, modelError);
      }
    }

    return NextResponse.json({ reply });
  } catch (error) {
    console.error("Gemini chat error", error);

    const message =
      error instanceof Error && "status" in error && typeof error.status === "number"
        ? `Gemini API error (${error.status}): ${error.message}`
        : error instanceof Error
          ? error.message
          : "Failed to get a response from Gemini.";

    return NextResponse.json(
      { error: message },
      { status: 500 }
    );
  }
}