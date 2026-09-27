import assert from "node:assert/strict";
import test from "node:test";
import { agentConfig, createAgentClient, resetConversation } from "./agent_client.js";

test("local default and HTTPS override resolve the matching reset URL", () => {
  const local = agentConfig({ NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret" });
  assert.equal(local.chatUrl.href, "http://127.0.0.1:8772/agent/chat");
  assert.equal(local.resetUrl.href, "http://127.0.0.1:8772/agent/imessage/reset");

  const remote = agentConfig({
    NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret",
    NIGHT_OWL_AGENT_URL: "https://example.org/api/agent/chat",
  });
  assert.equal(remote.resetUrl.href, "https://example.org/api/agent/imessage/reset");
  const legacy = agentConfig({
    NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret",
    BARN_OWL_AGENT_URL: "https://legacy.example.org/api/agent/chat",
  });
  assert.equal(legacy.chatUrl.href, "https://legacy.example.org/api/agent/chat");
  assert.equal(agentConfig({
    NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret",
    NIGHT_OWL_AGENT_URL: "https://example.org/api/agent/chat",
    BARN_OWL_AGENT_URL: "https://legacy.example.org/api/agent/chat",
  }).chatUrl.href, remote.chatUrl.href);
  assert.throws(
    () => agentConfig({ NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret", NIGHT_OWL_AGENT_URL: "http://example.org/api/agent/chat" }),
    /HTTPS/,
  );
  assert.throws(() => agentConfig({}), /NIGHT_OWL_CHAT_BOT_TOKEN/);
});

test("chat and durable reset send the same bot token and space", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const config = agentConfig({ NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret" });
  const agent = createAgentClient(config, async (input, init) => {
    calls.push({ url: String(input), init: init! });
    if (calls.length === 1) return new Response('{"id":"new-thread"}', { status: 200 });
    return new Response('data: {"type":"delta","text":"Rats nearby"}\n\n', {
      headers: { "content-type": "text/event-stream" },
    });
  });

  await agent.reset("space-1");
  assert.deepEqual(await agent.ask("space-1", "Where?"), { text: "Rats nearby", images: [] });
  assert.deepEqual(calls.map(({ url }) => url), [
    "http://127.0.0.1:8772/agent/imessage/reset",
    "http://127.0.0.1:8772/agent/chat",
  ]);
  for (const { init } of calls) {
    assert.equal(init.method, "POST");
    assert.equal(new Headers(init.headers).get("x-chat-bot-token"), "shared-secret");
  }
  assert.deepEqual(JSON.parse(String(calls[0]!.init.body)), { imessage_space: "space-1" });
  assert.deepEqual(JSON.parse(String(calls[1]!.init.body)), {
    channel: "imessage",
    imessage_space: "space-1",
    text: "Where?",
  });
});

test("reset acknowledgment waits for success and is absent on failure", async () => {
  const config = agentConfig({ NIGHT_OWL_CHAT_BOT_TOKEN: "shared-secret" });
  let resolveResponse!: (response: Response) => void;
  const agent = createAgentClient(config, () => new Promise<Response>((resolve) => { resolveResponse = resolve; }));
  const acknowledgments: string[] = [];
  const pending = resetConversation(agent, "space-1", async () => { acknowledgments.push("Fresh start"); });
  assert.equal(acknowledgments.length, 0);
  resolveResponse(new Response("unavailable", { status: 503 }));
  await assert.rejects(pending, /agent reset 503/);
  assert.equal(acknowledgments.length, 0);

  const malformedAgent = createAgentClient(config, async () => new Response("<html>proxy error</html>", { status: 200 }));
  await assert.rejects(
    resetConversation(malformedAgent, "space-1", async () => { acknowledgments.push("Fresh start"); }),
    /invalid thread/,
  );
  const noIdAgent = createAgentClient(config, async () => new Response("{}", { status: 200 }));
  await assert.rejects(
    resetConversation(noIdAgent, "space-1", async () => { acknowledgments.push("Fresh start"); }),
    /invalid thread/,
  );
  assert.equal(acknowledgments.length, 0);

  const successfulAgent = createAgentClient(config, async () => new Response('{"id":"new-thread"}', { status: 200 }));
  await resetConversation(successfulAgent, "space-1", async () => { acknowledgments.push("Fresh start"); });
  assert.deepEqual(acknowledgments, ["Fresh start"]);
});
