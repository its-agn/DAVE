"use client";

import { FormEvent, useState } from "react";

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
      text: "Hi! I’m D.A.V.E. Tell me what you need help with.",
    },
  ]);
  const [input, setInput] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    setMessages((current) => [
      ...current,
      { id: Date.now(), sender: "user", text: trimmed },
    ]);
    setInput("");

    window.setTimeout(() => {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          sender: "assistant",
          text: "Thanks for the message. I’m ready to help you build something great.",
        },
      ]);
    }, 400);
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-fuchsia-950 via-purple-950 to-slate-900 px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-slate-900/80 shadow-2xl shadow-black/30 backdrop-blur">
        <header className="border-b border-white/10 px-6 py-5 sm:px-8">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-fuchsia-300">
            D.A.V.E Assistant
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-white">
            Smart support chat
          </h1>
        </header>

        <section className="flex min-h-[480px] flex-col justify-between p-4 sm:p-6">
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

          <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Type your message..."
              className="flex-1 rounded-2xl border border-white/10 bg-slate-800/80 px-4 py-3 text-sm text-white outline-none ring-0 placeholder:text-slate-400 focus:border-fuchsia-400"
            />
            <button
              type="submit"
              className="rounded-2xl bg-fuchsia-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-500"
            >
              Send
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
