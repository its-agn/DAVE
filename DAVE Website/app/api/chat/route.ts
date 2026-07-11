import path from "path";
import fs from "fs/promises";
import { fileURLToPath } from "url";
import { config } from "dotenv";
import { GoogleGenAI } from "@google/genai";
import { NextResponse } from "next/server";
import { SYSTEM_PROMPTS, DEFAULT_PROMPT_KEY } from "./prompts";

for (const envPath of [
  path.resolve(process.cwd(), ".env"),
  path.resolve(process.cwd(), "..", ".env"),
]) {
  config({ path: envPath });
}

export const runtime = "nodejs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataRoot = path.join(__dirname, "..", "..", "..", "data");
console.log("[chat route] dataRoot=", dataRoot);

/**
 * Reads data/latest.json and, if a swing is complete, returns the raw text
 * of its reduced gemini_file (never the full swing_file — that has raw IMU
 * arrays and is too large / unnecessary to send to the model).
 */
async function getLatestGeminiPayload(): Promise<string | null> {
  try {
    const latestRaw = await fs.readFile(path.join(dataRoot, "latest.json"), "utf8");
    const latest = JSON.parse(latestRaw);

    if (latest.status !== "complete" || !latest.gemini_file) {
      return null;
    }

    const geminiPath = path.join(dataRoot, latest.gemini_file);
    return await fs.readFile(geminiPath, "utf8");
  } catch (e) {
    console.error("Failed to load latest gemini payload", e);
    return null;
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const message = typeof body?.message === "string" ? body.message.trim() : "";

    let systemInstruction: string;
    let contents: any[];

    if (!message) {
      // "Coach" button flow: evaluate the latest completed swing.
      systemInstruction =
        SYSTEM_PROMPTS["volleyball_coach"] || SYSTEM_PROMPTS[DEFAULT_PROMPT_KEY];

      const payload = await getLatestGeminiPayload();

      if (!payload) {
        return NextResponse.json(
          { error: "No completed swing data available yet." },
          { status: 404 }
        );
      }

      contents = [{ role: "user", parts: [{ text: payload }] }];
    } else {
      // Free-text follow-up questions.
      systemInstruction =
        SYSTEM_PROMPTS["volleyball_help"] || SYSTEM_PROMPTS[DEFAULT_PROMPT_KEY];
      contents = [{ role: "user", parts: [{ text: message }] }];
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        { error: "GEMINI_API_KEY is not set. Add it to your environment before using Gemini." },
        { status: 500 }
      );
    }

    const ai = new GoogleGenAI({ apiKey });
    const modelsToTry = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"];

    let reply: string | null = null;
    let lastError: unknown = null;

    for (const model of modelsToTry) {
      try {
        const response = await ai.models.generateContent({
          model,
          config: { systemInstruction },
          contents,
        });
        reply = response.text || null;
        lastError = null;
        if (reply) break;
      } catch (modelError) {
        console.warn(`Gemini model ${model} failed`, modelError);
        lastError = modelError;
      }
    }

    if (!reply) {
      const errMsg =
        lastError instanceof Error ? lastError.message : "All Gemini models failed.";
      console.error("All Gemini models failed:", errMsg);
      return NextResponse.json({ error: `Gemini error: ${errMsg}` }, { status: 502 });
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

    return NextResponse.json({ error: message }, { status: 500 });
  }
}