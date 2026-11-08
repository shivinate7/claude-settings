// A window.claude stand-in for page.html, for bin/shoot design checks: set it as a route's `stub` key and the shot of the
// waiting page shows two titled item cards, not "cannot reach the page's store". It answers use("db") with an `items`
// collection and no other.
// check_designs.mjs keeps its own stub, because it builds one for each item it checks; this file is one fixed pair of items.
(() => {
  const task = (id, n, title) => ({
    id, n, kind: "task", status: "open", added: "2026-11-01T00:00:00Z", ref: "shoot stub", title,
    owner: "shoot stub", home: "shoot stub", context: "A stand-in item.", steps: ["Open the page"], links: [], minutes: 1,
  });
  const docs = { items: {
    "shoot-stub-task": task("shoot-stub-task", 1, "Approve the shoot stub check"),
    "shoot-stub-task-2": task("shoot-stub-task-2", 2, "Check the second stub item"),
  } };
  const snap = (name) => ({ docs: Object.entries(docs[name] || {}).map(([id, v]) => ({ id, data: () => v })) });
  const one = (name, id) => ({ exists: !!(docs[name] || {})[id], data: () => (docs[name] || {})[id] || null });
  const collection = (name) => ({
    onSnapshot: (cb) => { setTimeout(() => cb(snap(name)), 0); return () => {}; },
    orderBy: () => collection(name),
    doc: (id) => ({ get: async () => one(name, id), onSnapshot: (cb) => { setTimeout(() => cb(one(name, id)), 0); return () => {}; } }),
  });
  window.claude = { use: async (cap) => (cap === "db" ? { collection } : null) };
})();
