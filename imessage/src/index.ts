import { attachment, markdown, Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers";
import { agentConfig, createAgentClient, resetConversation } from "./agent_client.js";

// The API stores each Spectrum space's history in SQLite. Reset creates a new stored thread.
const config = agentConfig(process.env);
const agent = createAgentClient(config);

function requireEnv(name: "PROJECT_ID" | "PROJECT_SECRET"): string {
  const value = process.env[name];
  if (!value?.trim()) throw new Error(`${name} is required for the Spectrum iMessage provider`);
  return value;
}

const app = await Spectrum({
  projectId: requireEnv("PROJECT_ID"),
  projectSecret: requireEnv("PROJECT_SECRET"),
  providers: [imessage.config()],
});
console.log(`NightOwl iMessage agent up -> ${config.chatUrl}`);

const pending = new Map<string, Promise<void>>();

for await (const [space, message] of app.messages) {
  if (message.content.type !== "text") continue;
  const q = message.content.text.trim();
  if (!q) continue;
  const reset = /^(reset|new chat|start over)$/i.test(q);
  // Keep each space's requests in message order, including reset. Other spaces can run concurrently.
  const task = (pending.get(space.id) ?? Promise.resolve())
    .then(async () => {
      if (reset) {
        await resetConversation(agent, space.id, () =>
          space.send("Fresh start. Ask me about rats, blocks, owls or the Pi."),
        );
        return;
      }
      await space.responding(async () => {
        const { text, images } = await agent.ask(space.id, q);
        if (text) await space.send(markdown(text));
        for (const src of images.slice(0, 3)) {
          const [, mime = "image/jpeg", b64 = ""] = /^data:([^;]+);base64,(.*)$/s.exec(src) ?? [];
          if (b64) await space.send(attachment(Buffer.from(b64, "base64"), { name: "nightowl.jpg", mimeType: mime }));
        }
      });
    })
    .catch(async (err: unknown) => {
      console.error("agent failed:", err);
      const message = reset
        ? "I couldn't confirm a fresh chat. Try reset again before continuing."
        : "Sorry, I couldn't reach the NightOwl assistant just now. Try again in a minute.";
      await space.send(message).catch(() => {});
    });
  pending.set(space.id, task);
  void task.then(() => {
    if (pending.get(space.id) === task) pending.delete(space.id);
  });
}
