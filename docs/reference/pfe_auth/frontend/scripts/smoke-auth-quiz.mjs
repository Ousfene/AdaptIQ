const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    throw new Error(`${path} failed (${res.status}): ${JSON.stringify(body)}`);
  }
  return body;
}

async function main() {
  const runId = Date.now();
  const email = `smoke_${runId}@example.com`;
  const username = `smoke_${runId}`;
  const password = "SmokeTest1!";

  console.log("1) health");
  try {
    await request("/api/system/health");
  } catch {
    await request("/health");
  }

  console.log("2) register");
  let register;
  try {
    register = await request("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, username, password }),
    });
  } catch {
    register = await request("/api/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, username, password }),
    });
  }

  const token = register?.access_token;
  const userId = register?.user?.id;
  if (!token || !userId) {
    throw new Error("Register response missing token/user id");
  }

  const authHeaders = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  console.log("3) me");
  await request("/api/auth/me", { headers: authHeaders });

  console.log("4) start quiz (question)");
  const question = await request("/api/rooms/classic/questions", {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      topic: "history",
    }),
  });

  const sessionId = question?.session_id;
  if (!question?.id || !sessionId || !Array.isArray(question.options) || question.options.length === 0) {
    throw new Error("Question payload missing expected fields");
  }

  console.log("5) submit first option");
  await request("/api/rooms/classic/answers", {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({
      user_id: userId,
      session_id: sessionId,
      question_id: question.id,
      selected_index: 0,
      time_taken: 3,
      used_hint: false,
    }),
  });

  console.log("Smoke auth->quiz flow passed");
}

main().catch((err) => {
  console.error("Smoke auth->quiz flow failed:", err.message || err);
  process.exit(1);
});
