import { attachment, markdown, Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

// NightOwl over iMessage (Photon Spectrum): every text goes to the same Grok assistant as the web app's chat
// (POST /api/agent/chat on barn-owl.tech, api/agent.py) with channel "imessage", so it gets the server tools
// (model, hexagons, owl sites, the Pi, its camera) but not the map ones. Pictures come back as attachments.
// The server keeps each conversation as a thread in its SQLite chat store (api/chat_store.py), keyed by the Spectrum
// space id, so history survives restarts of this bot. That only works from the same machine as the API (it refuses
// imessage threads that came through the proxy), so on the droplet this points at http://127.0.0.1:8772/agent/chat.
// Docs: https://photon.codes/docs/spectrum-ts
const AGENT_URL = (process.env.NIGHT_OWL_AGENT_URL ?? process.env.BARN_OWL_AGENT_URL ?? "https://barn-owl.tech/api/agent/chat").replace(/\/$/, "");
// conversations that texted "reset": their next question starts a new thread
const fresh = new Set<string>();

/** One question through the agent: the answer text and any pictures. The server loads and saves the history. */
async function ask(space: string, text: string): Promise<{ text: string; images: string[] }> {
  const newThread = fresh.delete(space);
  const res = await fetch(AGENT_URL, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ channel: "imessage", imessage_space: space, text, ...(newThread && { new_thread: true }) }),
  });
  if (!res.ok || !res.body) throw new Error(`agent ${res.status}: ${await res.text().catch(() => "")}`);
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
}

const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [imessage.config()],
});
console.log(`NightOwl iMessage agent up -> ${AGENT_URL}`);

for await (const [space, message] of app.messages) {
  if (message.content.type !== "text") continue;
  const q = message.content.text.trim();
  if (!q) continue;
  if (/^(reset|new chat|start over)$/i.test(q)) {
    fresh.add(space.id);
    await space.send("Fresh start. Ask me about rats, blocks, owls or the Pi.");
    continue;
  }
  // one conversation's questions run in order; different conversations don't wait on each other
  void space
    .responding(async () => {
      const { text, images } = await ask(space.id, q);
      if (text) await space.send(markdown(text));
      for (const src of images.slice(0, 3)) {
        const [, mime = "image/jpeg", b64 = ""] = /^data:([^;]+);base64,(.*)$/s.exec(src) ?? [];
        if (b64) await space.send(attachment(Buffer.from(b64, "base64"), { name: "nightowl.jpg", mimeType: mime }));
      }
    })
    .catch(async (err: unknown) => {
      console.error("agent failed:", err);
      await space.send("Sorry, I couldn't reach the NightOwl assistant just now. Try again in a minute.").catch(() => {});
    });
}
