import path from "path";
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
    
    // Grab the chosen persona key from the body, or use the default coach
    const personaKey = (body?.persona || DEFAULT_PROMPT_KEY) as PromptKey;

    if (!message) {
      return NextResponse.json(
        { error: "Please enter a message first." },
        { status: 400 }
      );
    }

    // Safely look up the prompt instruction, fallback to default if an invalid key is sent
    const systemInstruction = SYSTEM_PROMPTS[personaKey] || SYSTEM_PROMPTS[DEFAULT_PROMPT_KEY];

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
          contents: [
            {
              role: "user",
              parts: [{ text: message }],
            },
          ],
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