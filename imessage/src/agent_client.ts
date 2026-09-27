const DEFAULT_AGENT_URL = "http://127.0.0.1:8772/agent/chat";

type HttpFetch = (input: string | URL, init?: RequestInit) => Promise<Response>;

export function agentConfig(env: NodeJS.ProcessEnv): { chatUrl: URL; resetUrl: URL; token: string } {
  const token = env.NIGHT_OWL_CHAT_BOT_TOKEN;
  if (!token?.trim()) throw new Error("NIGHT_OWL_CHAT_BOT_TOKEN is required for iMessage chat");

  const rawUrl = env.NIGHT_OWL_AGENT_URL || env.BARN_OWL_AGENT_URL || DEFAULT_AGENT_URL;
  let chatUrl: URL;
  try {
    chatUrl = new URL(rawUrl);
  } catch {
    throw new Error("NIGHT_OWL_AGENT_URL must be a full URL ending in /agent/chat");
  }
  if (!/\/agent\/chat\/?$/.test(chatUrl.pathname) || chatUrl.search || chatUrl.hash || chatUrl.username || chatUrl.password) {
    throw new Error("NIGHT_OWL_AGENT_URL must be a full URL ending in /agent/chat without credentials or query parameters");
  }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(chatUrl.hostname);
  if (chatUrl.protocol !== "https:" && !(loopback && chatUrl.protocol === "http:")) {
    throw new Error("NIGHT_OWL_AGENT_URL must use HTTPS unless it points to loopback");
  }
  chatUrl.pathname = chatUrl.pathname.replace(/\/$/, "");
  const resetUrl = new URL(chatUrl);
  resetUrl.pathname = resetUrl.pathname.replace(/\/agent\/chat$/, "/agent/imessage/reset");
  return { chatUrl, resetUrl, token };
}

export function createAgentClient(config: ReturnType<typeof agentConfig>, httpFetch: HttpFetch = fetch) {
  const headers = { "content-type": "application/json", "x-chat-bot-token": config.token };

  return {
    async reset(space: string): Promise<void> {
      const res = await httpFetch(config.resetUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({ imessage_space: space }),
      });
      if (!res.ok) throw new Error(`agent reset ${res.status}`);
      let thread: unknown;
      try {
        thread = await res.json();
      } catch {
        throw new Error("agent reset returned an invalid thread");
      }
      if (!thread || typeof thread !== "object" || !("id" in thread) ||
          typeof thread.id !== "string" || !thread.id.trim()) {
        throw new Error("agent reset returned an invalid thread");
      }
    },

    async ask(space: string, text: string): Promise<{ text: string; images: string[] }> {
      const res = await httpFetch(config.chatUrl, {
        method: "POST",
        headers: { ...headers, accept: "text/event-stream" },
        body: JSON.stringify({ channel: "imessage", imessage_space: space, text }),
      });
      if (!res.ok || !res.body) throw new Error(`agent chat ${res.status}`);
      let answer = "";
      const images: string[] = [];
      let error = "";
      const dec = new TextDecoder();
      let buf = "";
      for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
        buf += dec.decode(chunk, { stream: true });
        let cut;
        while ((cut = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, cut).trim();
          buf = buf.slice(cut + 2);
          if (!line.startsWith("data:")) continue;
          const e = JSON.parse(line.slice(5));
          if (e.type === "delta") answer += e.text;
          else if (e.type === "tool" && e.state === "start" && answer && !answer.endsWith("\n\n")) answer += "\n\n";
          else if (e.type === "image" && typeof e.src === "string") images.push(e.src);
          else if (e.type === "error") error = e.text;
        }
      }
      if (!answer && error) answer = `Sorry, something went wrong: ${error}`;
      return { text: answer.trim(), images };
    },
  };
}

export async function resetConversation(
  agent: Pick<ReturnType<typeof createAgentClient>, "reset">,
  space: string,
  acknowledge: () => Promise<unknown>,
): Promise<void> {
  await agent.reset(space);
  await acknowledge();
}
