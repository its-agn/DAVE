"use client";

import { FormEvent, useEffect, useState } from "react";

type Message = {
  id: number;
  sender: "assistant" | "user";
  text: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      sender: "assistant",
      text: "Hello, I am your virtual volleyball coach. Tell me what run you want me to evaluate, and we will get started!",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [latestSwing, setLatestSwing] = useState<any | null>(null);
  const [latestError, setLatestError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchLatestSwing = async () => {
      try {
        const response = await fetch("/api/chat/swings/latest");
        const text = await response.text();
        if (cancelled) return;

        let data: any;
        try {
          data = JSON.parse(text);
        } catch (e) {
          throw new Error(
            text && text.length > 0
              ? `Invalid JSON from latest swing endpoint: ${text}`
              : "Failed to parse latest swing response"
          );
        }

        if (!response.ok) {
          const message = data?.error ?? "Failed to fetch latest swing.";
          throw new Error(message);
        }

        setLatestError(null);
        setLatestSwing(data);
      } catch (error) {
        if (cancelled) return;
        setLatestSwing(null);
        setLatestError(
          error instanceof Error
            ? error.message
            : "Failed to fetch latest swing."
        );
      }
    };

    fetchLatestSwing();
    const interval = setInterval(fetchLatestSwing, 750);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMessage = { id: Date.now(), sender: "user" as const, text: trimmed };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });

      const text = await response.text();
      let data: any;
      try {
        data = JSON.parse(text);
      } catch (e) {
        console.error("Non-JSON response from /api/chat:", response.status, text);
        throw new Error(
          text && text.length > 0
            ? `Server returned non-JSON response (status ${response.status}). See console for details.`
            : "Failed to parse JSON response from server"
        );
      }
      if (!response.ok) {
        throw new Error(data.error || "Failed to get a response");
      }

      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          sender: "assistant" as const,
          text: data.reply,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 2,
          sender: "assistant" as const,
          text:
            error instanceof Error
              ? error.message
              : "Sorry, I could not reach Gemini right now.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCoachClick = async () => {
    if (isLoading) return;

    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      const text = await response.text();
      let data: any;
      try {
        data = JSON.parse(text);
      } catch (e) {
        console.error("Non-JSON response from /api/chat:", response.status, text);
        throw new Error(
          text && text.length > 0
            ? `Server returned non-JSON response (status ${response.status}). See console for details.`
            : "Failed to parse JSON response from server"
        );
      }
      if (!response.ok) {
        throw new Error(data.error || "Failed to get a response");
      }

      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          sender: "assistant" as const,
          text: data.reply,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 2,
          sender: "assistant" as const,
          text:
            error instanceof Error
              ? error.message
              : "Sorry, I could not reach Gemini right now.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-linear-to-br from-fuchsia-950 via-purple-950 to-slate-900 px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-slate-900/80 shadow-2xl shadow-black/30 backdrop-blur">
        <header className="border-b border-white/10 px-6 py-5 sm:px-8">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-fuchsia-300">
            D.A.V.E Assistant
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-white">
            Smart support chat
          </h1>
        </header>

        <section className="flex min-h-120 flex-col justify-between p-4 sm:p-6">
          <div className="mb-4 rounded-2xl border border-white/10 bg-slate-800/70 p-4 text-sm text-slate-200">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold text-white">Latest swing status</span>
              <span className="text-xs uppercase tracking-[0.25em] text-slate-400">polling every 0.75s</span>
            </div>
            {latestError ? (
              <p className="text-rose-300">{latestError}</p>
            ) : latestSwing ? (
              <div className="space-y-1">
                <p>
                  Status: <span className="font-semibold text-white">{latestSwing.status ?? "unknown"}</span>
                </p>
                {(latestSwing.swing_id || latestSwing.id) && (
                  <p>
                    ID: <span className="font-semibold text-white">{latestSwing.swing_id ?? latestSwing.id}</span>
                  </p>
                )}
                {latestSwing.status === "complete" ? (
                  <p className="text-slate-300">A completed swing is ready for review.</p>
                ) : (
                  <p className="text-slate-400">Waiting for a completed swing...</p>
                )}
              </div>
            ) : (
              <p className="text-slate-400">Loading latest swing status...</p>
            )}
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto rounded-2xl border border-white/10 bg-slate-950/50 p-3 sm:p-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.sender === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-md sm:max-w-[70%] ${
                    message.sender === "user"
                      ? "bg-fuchsia-600 text-white"
                      : "bg-slate-800 text-slate-200"
                  }`}
                >
                  {message.text}
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row items-center">
            <button
              type="button"
              onClick={handleCoachClick}
              disabled={isLoading}
              className="order-1 rounded-2xl bg-slate-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-60 sm:order-1"
            >
              {isLoading ? "Thinking..." : "Coach"}
            </button>

            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Type your message..."
              disabled={isLoading}
              className="flex-1 rounded-2xl border border-white/10 bg-slate-800/80 px-4 py-3 text-sm text-white outline-none ring-0 placeholder:text-slate-400 focus:border-fuchsia-400 disabled:cursor-not-allowed disabled:opacity-60"
            />

            <button
              type="submit"
              disabled={isLoading}
              className="rounded-2xl bg-fuchsia-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? "Thinking..." : "Send"}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
